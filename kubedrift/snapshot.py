"""
Snapshot capture, parsing, and (de)serialization.

take_snapshot() talks to the cluster via kubectl; every parse_* function is
pure (raw kubectl JSON in, dataclass out) so the whole pipeline is testable
from fixture files without a cluster.

Secret values and inline env values are stored as truncated SHA-256 digests —
snapshots stay safe to commit while still detecting that a value changed.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from typing import Any

from kubedrift import kubectl
from kubedrift.models import (
    FORMAT_VERSION,
    ConfigMapSchema,
    ContainerSpec,
    EnvVar,
    IngressRule,
    IngressSchema,
    SecretSchema,
    ServicePort,
    ServiceSchema,
    SnapshotModel,
    WorkloadSchema,
)

WORKLOAD_KINDS = ["deployments", "statefulsets", "daemonsets"]


def hash_value(value: str) -> str:
    """Truncated SHA-256 — enough to detect change, useless for recovery."""
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()[:12]


def _parse_env(env_list: list[dict[str, Any]]) -> list[EnvVar]:
    out: list[EnvVar] = []
    for e in env_list:
        name = e["name"]
        if "value" in e:
            out.append(EnvVar(name=name, value=hash_value(e["value"])))
        elif "valueFrom" in e:
            vf = e["valueFrom"]
            if "secretKeyRef" in vf:
                ref = vf["secretKeyRef"]
                out.append(EnvVar(name=name, value=f"from:secret/{ref['name']}/{ref['key']}"))
            elif "configMapKeyRef" in vf:
                ref = vf["configMapKeyRef"]
                out.append(EnvVar(name=name, value=f"from:configmap/{ref['name']}/{ref['key']}"))
            elif "fieldRef" in vf:
                out.append(EnvVar(name=name, value=f"from:field/{vf['fieldRef']['fieldPath']}"))
            else:
                out.append(EnvVar(name=name, value="from:other"))
        else:
            out.append(EnvVar(name=name, value=hash_value("")))
    return out


def _parse_container(c: dict[str, Any]) -> ContainerSpec:
    resources = c.get("resources", {})
    return ContainerSpec(
        name=c["name"],
        image=c["image"],
        requests=dict(resources.get("requests", {})),
        limits=dict(resources.get("limits", {})),
        env=_parse_env(c.get("env", [])),
    )


def parse_workload(item: dict[str, Any]) -> WorkloadSchema:
    kind = item["kind"]
    meta = item["metadata"]
    spec = item.get("spec", {})
    containers = spec.get("template", {}).get("spec", {}).get("containers", [])
    return WorkloadSchema(
        kind=kind,
        namespace=meta["namespace"],
        name=meta["name"],
        replicas=None if kind == "DaemonSet" else spec.get("replicas", 1),
        containers=[_parse_container(c) for c in containers],
    )


def parse_configmap(item: dict[str, Any]) -> ConfigMapSchema:
    meta = item["metadata"]
    data = item.get("data", {}) or {}
    return ConfigMapSchema(
        namespace=meta["namespace"],
        name=meta["name"],
        keys={k: hash_value(v) for k, v in sorted(data.items())},
    )


def parse_secret(item: dict[str, Any]) -> SecretSchema:
    meta = item["metadata"]
    data = item.get("data", {}) or {}
    return SecretSchema(
        namespace=meta["namespace"],
        name=meta["name"],
        type=item.get("type", "Opaque"),
        # data values are already base64; hash them as-is — we never decode.
        keys={k: hash_value(v) for k, v in sorted(data.items())},
    )


def parse_service(item: dict[str, Any]) -> ServiceSchema:
    meta = item["metadata"]
    spec = item.get("spec", {})
    ports = [
        ServicePort(
            name=p.get("name", ""),
            port=p["port"],
            target_port=str(p.get("targetPort", p["port"])),
            protocol=p.get("protocol", "TCP"),
        )
        for p in spec.get("ports", [])
    ]
    return ServiceSchema(
        namespace=meta["namespace"],
        name=meta["name"],
        type=spec.get("type", "ClusterIP"),
        selector=dict(spec.get("selector", {}) or {}),
        ports=ports,
    )


def parse_ingress(item: dict[str, Any]) -> IngressSchema:
    meta = item["metadata"]
    rules: list[IngressRule] = []
    for rule in item.get("spec", {}).get("rules", []):
        host = rule.get("host", "*")
        for path in rule.get("http", {}).get("paths", []):
            backend = path.get("backend", {}).get("service", {})
            port = backend.get("port", {})
            rules.append(
                IngressRule(
                    host=host,
                    path=path.get("path", "/"),
                    backend_service=backend.get("name", ""),
                    backend_port=str(port.get("number", port.get("name", ""))),
                )
            )
    return IngressSchema(namespace=meta["namespace"], name=meta["name"], rules=rules)


def _wkey(w: WorkloadSchema) -> str:
    return f"{w.namespace}/{w.kind}/{w.name}"


def _nskey(obj: Any) -> str:
    return f"{obj.namespace}/{obj.name}"


def build_snapshot(
    context: str,
    server_version: str,
    workload_items: list[dict[str, Any]],
    configmap_items: list[dict[str, Any]],
    secret_items: list[dict[str, Any]],
    service_items: list[dict[str, Any]],
    ingress_items: list[dict[str, Any]],
) -> SnapshotModel:
    """Assemble a SnapshotModel from raw kubectl JSON items. Pure — no I/O."""
    workloads = {_wkey(w): w for w in (parse_workload(i) for i in workload_items)}
    configmaps = {_nskey(c): c for c in (parse_configmap(i) for i in configmap_items)}
    secrets = {_nskey(s): s for s in (parse_secret(i) for i in secret_items)}
    services = {_nskey(s): s for s in (parse_service(i) for i in service_items)}
    ingresses = {_nskey(i): i for i in (parse_ingress(x) for x in ingress_items)}

    namespaces = sorted(
        {
            v.namespace
            for group in (workloads, configmaps, secrets, services)
            for v in group.values()
        }
    )
    return SnapshotModel(
        format_version=FORMAT_VERSION,
        captured_at=datetime.now(UTC).isoformat(timespec="seconds"),
        context=context,
        server_version=server_version,
        namespaces=namespaces,
        workloads=workloads,
        configmaps=configmaps,
        secrets=secrets,
        services=services,
        ingresses=ingresses,
    )


# System configmaps/secrets present in every namespace — noise, not drift.
_SKIP_CONFIGMAPS = {"kube-root-ca.crt"}
_SKIP_SECRET_TYPES = {"kubernetes.io/service-account-token"}
_SYSTEM_NAMESPACES = {"kube-system", "kube-public", "kube-node-lease", "local-path-storage"}


def take_snapshot(
    namespace: str | None = None,
    context: str | None = None,
    include_system: bool = False,
) -> SnapshotModel:
    """Capture live cluster state via kubectl.

    namespace=None captures all namespaces (minus system ones unless
    include_system is set).
    """

    def _filtered(kind: str) -> list[dict[str, Any]]:
        items = kubectl.get_items(kind, namespace=namespace, context=context)
        if namespace is None and not include_system:
            items = [i for i in items if i["metadata"]["namespace"] not in _SYSTEM_NAMESPACES]
        return items

    workload_items = []
    for kind in WORKLOAD_KINDS:
        workload_items.extend(_filtered(kind))

    configmap_items = [
        i for i in _filtered("configmaps") if i["metadata"]["name"] not in _SKIP_CONFIGMAPS
    ]
    secret_items = [i for i in _filtered("secrets") if i.get("type") not in _SKIP_SECRET_TYPES]
    service_items = _filtered("services")
    ingress_items = _filtered("ingresses")

    return build_snapshot(
        context=context or kubectl.current_context(),
        server_version=kubectl.server_version(context),
        workload_items=workload_items,
        configmap_items=configmap_items,
        secret_items=secret_items,
        service_items=service_items,
        ingress_items=ingress_items,
    )


def save_snapshot(snap: SnapshotModel, path: str) -> None:
    """Write snapshot as deterministic JSON — sorted keys, stable formatting."""
    with open(path, "w") as f:
        json.dump(snap.to_dict(), f, indent=2, sort_keys=True)
        f.write("\n")


def load_snapshot(path: str) -> SnapshotModel:
    if not os.path.exists(path):
        raise FileNotFoundError(f"snapshot file not found: {path}")
    with open(path) as f:
        raw = json.load(f)

    version = raw.get("format_version")
    if version != FORMAT_VERSION:
        raise ValueError(
            f"unsupported snapshot format_version {version} (expected {FORMAT_VERSION})"
        )

    return SnapshotModel(
        format_version=raw["format_version"],
        captured_at=raw["captured_at"],
        context=raw["context"],
        server_version=raw["server_version"],
        namespaces=raw["namespaces"],
        workloads={
            k: WorkloadSchema(
                kind=w["kind"],
                namespace=w["namespace"],
                name=w["name"],
                replicas=w["replicas"],
                containers=[
                    ContainerSpec(
                        name=c["name"],
                        image=c["image"],
                        requests=c["requests"],
                        limits=c["limits"],
                        env=[EnvVar(**e) for e in c["env"]],
                    )
                    for c in w["containers"]
                ],
            )
            for k, w in raw["workloads"].items()
        },
        configmaps={k: ConfigMapSchema(**c) for k, c in raw["configmaps"].items()},
        secrets={k: SecretSchema(**s) for k, s in raw["secrets"].items()},
        services={
            k: ServiceSchema(
                namespace=s["namespace"],
                name=s["name"],
                type=s["type"],
                selector=s["selector"],
                ports=[ServicePort(**p) for p in s["ports"]],
            )
            for k, s in raw["services"].items()
        },
        ingresses={
            k: IngressSchema(
                namespace=i["namespace"],
                name=i["name"],
                rules=[IngressRule(**r) for r in i["rules"]],
            )
            for k, i in raw["ingresses"].items()
        },
    )
