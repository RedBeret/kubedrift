"""Tests for the model helper methods used throughout diffing."""

from kubedrift.models import (
    ContainerSpec,
    DiffEntry,
    DiffResult,
    EnvVar,
    IngressRule,
    IngressSchema,
    ServicePort,
    ServiceSchema,
    WorkloadSchema,
)


def test_container_env_map():
    c = ContainerSpec(name="app", image="i", env=[EnvVar("A", "sha256:1"), EnvVar("B", "sha256:2")])
    assert c.env_map() == {"A": "sha256:1", "B": "sha256:2"}


def test_workload_container_map():
    w = WorkloadSchema(
        kind="Deployment",
        namespace="prod",
        name="api",
        replicas=1,
        containers=[ContainerSpec(name="app", image="i")],
    )
    assert set(w.container_map()) == {"app"}


def test_service_port_map_keys_by_protocol_and_port():
    s = ServiceSchema(
        namespace="prod",
        name="api",
        type="ClusterIP",
        ports=[ServicePort(name="http", port=80, target_port="8080", protocol="TCP")],
    )
    assert set(s.port_map()) == {"TCP/80"}


def test_ingress_rule_map_keys_by_host_and_path():
    ing = IngressSchema(
        namespace="prod",
        name="api",
        rules=[
            IngressRule(host="a.example", path="/api", backend_service="api", backend_port="80")
        ],
    )
    assert set(ing.rule_map()) == {"a.example/api"}


def test_diff_result_has_breaking_and_by_category():
    result = DiffResult(
        baseline_captured_at="t0",
        current_captured_at="t1",
        entries=[
            DiffEntry("BREAKING", "workload", "prod/Deployment/api", "api", "deleted"),
            DiffEntry("ADDITIVE", "workload", "prod/Deployment/new", "new", "new deployment"),
        ],
    )
    assert result.has_breaking
    assert len(result.by_category("ADDITIVE")) == 1
    assert result.by_category("IMAGE") == []
