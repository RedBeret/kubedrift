"""Shared builders for hand-crafted snapshot models in tests."""

from __future__ import annotations

from kubedrift.models import (
    ConfigMapSchema,
    ContainerSpec,
    SecretSchema,
    ServicePort,
    ServiceSchema,
    SnapshotModel,
    WorkloadSchema,
)


def snap(**groups) -> SnapshotModel:
    """Build a minimal SnapshotModel from keyed resource dicts."""
    return SnapshotModel(
        format_version=1,
        captured_at="2026-01-01T00:00:00+00:00",
        context="test",
        server_version="v1.30.0",
        namespaces=["prod"],
        workloads=groups.get("workloads", {}),
        configmaps=groups.get("configmaps", {}),
        secrets=groups.get("secrets", {}),
        services=groups.get("services", {}),
        ingresses=groups.get("ingresses", {}),
    )


def deployment(
    name: str = "parts-api",
    replicas: int = 2,
    image: str = "nginx:1.25",
    containers: list[ContainerSpec] | None = None,
) -> dict[str, WorkloadSchema]:
    w = WorkloadSchema(
        kind="Deployment",
        namespace="prod",
        name=name,
        replicas=replicas,
        containers=containers
        if containers is not None
        else [ContainerSpec(name="app", image=image)],
    )
    return {f"prod/Deployment/{name}": w}


def configmap(name: str = "app-config", keys: dict[str, str] | None = None):
    cm = ConfigMapSchema(namespace="prod", name=name, keys=keys or {"LOG_LEVEL": "sha256:aaa"})
    return {f"prod/{name}": cm}


def secret(name: str = "db-credentials", keys: dict[str, str] | None = None):
    s = SecretSchema(
        namespace="prod", name=name, type="Opaque", keys=keys or {"password": "sha256:bbb"}
    )
    return {f"prod/{name}": s}


def service(
    name: str = "parts-api",
    selector: dict[str, str] | None = None,
    ports: list[ServicePort] | None = None,
    svc_type: str = "ClusterIP",
):
    s = ServiceSchema(
        namespace="prod",
        name=name,
        type=svc_type,
        selector=selector if selector is not None else {"app": name},
        ports=ports
        if ports is not None
        else [ServicePort(name="http", port=80, target_port="8080", protocol="TCP")],
    )
    return {f"prod/{name}": s}
