"""
Core data models for kubedrift snapshots and diffs.

All models use plain dataclasses — no ORM, no external schema library.
Keeping it simple so the code is easy to audit.

Sensitive material is never stored in plaintext: Secret values and inline
env var values are truncated SHA-256 digests (see snapshot.hash_value).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

FORMAT_VERSION = 1


@dataclass
class EnvVar:
    name: str
    # Either "sha256:<12 hex chars>" for an inline value, or a reference like
    # "from:secret/db-credentials/password" or "from:configmap/app-config/LOG_LEVEL".
    value: str


@dataclass
class ContainerSpec:
    name: str
    image: str
    requests: dict[str, str] = field(default_factory=dict)
    limits: dict[str, str] = field(default_factory=dict)
    env: list[EnvVar] = field(default_factory=list)

    def env_map(self) -> dict[str, str]:
        return {e.name: e.value for e in self.env}


@dataclass
class WorkloadSchema:
    kind: str  # Deployment, StatefulSet, DaemonSet
    namespace: str
    name: str
    replicas: int | None  # None for DaemonSets (replica count is node-driven)
    containers: list[ContainerSpec] = field(default_factory=list)

    def container_map(self) -> dict[str, ContainerSpec]:
        return {c.name: c for c in self.containers}


@dataclass
class ConfigMapSchema:
    namespace: str
    name: str
    keys: dict[str, str] = field(default_factory=dict)  # key -> sha256:<12>


@dataclass
class SecretSchema:
    namespace: str
    name: str
    type: str
    keys: dict[str, str] = field(default_factory=dict)  # key -> sha256:<12>


@dataclass
class ServicePort:
    name: str
    port: int
    target_port: str
    protocol: str


@dataclass
class ServiceSchema:
    namespace: str
    name: str
    type: str
    selector: dict[str, str] = field(default_factory=dict)
    ports: list[ServicePort] = field(default_factory=list)

    def port_map(self) -> dict[str, ServicePort]:
        return {f"{p.protocol}/{p.port}": p for p in self.ports}


@dataclass
class IngressRule:
    host: str
    path: str
    backend_service: str
    backend_port: str


@dataclass
class IngressSchema:
    namespace: str
    name: str
    rules: list[IngressRule] = field(default_factory=list)

    def rule_map(self) -> dict[str, IngressRule]:
        return {f"{r.host}{r.path}": r for r in self.rules}


@dataclass
class SnapshotModel:
    format_version: int
    captured_at: str
    context: str
    server_version: str
    namespaces: list[str]
    workloads: dict[str, WorkloadSchema] = field(default_factory=dict)  # "ns/Kind/name"
    configmaps: dict[str, ConfigMapSchema] = field(default_factory=dict)  # "ns/name"
    secrets: dict[str, SecretSchema] = field(default_factory=dict)  # "ns/name"
    services: dict[str, ServiceSchema] = field(default_factory=dict)  # "ns/name"
    ingresses: dict[str, IngressSchema] = field(default_factory=dict)  # "ns/name"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DiffEntry:
    category: str  # BREAKING, IMAGE, ADDITIVE, INFORMATIONAL
    object_type: str  # workload, container, env, configmap, secret, service, ingress
    resource: str  # qualified resource key, e.g. "prod/Deployment/parts-api"
    name: str  # the changed thing within the resource (container name, key, port...)
    detail: str


@dataclass
class DiffResult:
    baseline_captured_at: str
    current_captured_at: str
    entries: list[DiffEntry] = field(default_factory=list)

    def by_category(self, category: str) -> list[DiffEntry]:
        return [e for e in self.entries if e.category == category]

    @property
    def has_breaking(self) -> bool:
        return any(e.category == "BREAKING" for e in self.entries)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
