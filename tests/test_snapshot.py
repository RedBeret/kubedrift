"""Tests for parsing raw kubectl JSON into snapshot models, and (de)serialization.

Fixtures are shaped exactly like `kubectl get <kind> -o json` items so the
parse layer is exercised the same way it is against a real cluster.
"""

import json
import os

from kubedrift.snapshot import (
    build_snapshot,
    hash_value,
    parse_ingress,
    parse_service,
    parse_workload,
)

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name: str) -> dict:
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def test_hash_value_is_deterministic_and_not_plaintext():
    assert hash_value("hunter2") == hash_value("hunter2")
    assert hash_value("hunter2") != hash_value("hunter3")
    assert "hunter2" not in hash_value("hunter2")
    assert hash_value("hunter2").startswith("sha256:")


def test_parse_workload_from_fixture():
    w = parse_workload(_load("deployment.json"))
    assert w.kind == "Deployment"
    assert w.namespace == "prod"
    assert w.replicas == 3
    assert [c.name for c in w.containers] == ["api", "sidecar"]

    api = w.container_map()["api"]
    assert api.image == "ghcr.io/acme/parts-api:2.4.1"
    assert api.requests == {"cpu": "100m", "memory": "128Mi"}
    assert api.limits == {"memory": "256Mi"}

    env = api.env_map()
    # Inline values are hashed, never stored raw.
    assert env["LOG_LEVEL"].startswith("sha256:")
    assert "info" not in env["LOG_LEVEL"]
    # References are stored as readable refs.
    assert env["DB_PASSWORD"] == "from:secret/db-credentials/password"
    assert env["CACHE_TTL"] == "from:configmap/app-config/CACHE_TTL"
    assert env["POD_NAME"] == "from:field/metadata.name"


def test_parse_service_from_fixture():
    s = parse_service(_load("service.json"))
    assert s.type == "ClusterIP"
    assert s.selector == {"app": "parts-api"}
    ports = s.port_map()
    assert ports["TCP/80"].target_port == "8080"
    # Named targetPort and defaulted protocol both survive parsing.
    assert ports["TCP/9090"].target_port == "metrics"


def test_parse_ingress_from_fixture():
    ing = parse_ingress(_load("ingress.json"))
    rules = ing.rule_map()
    assert rules["parts.acme.example/api"].backend_service == "parts-api"
    assert rules["parts.acme.example/api"].backend_port == "80"
    assert rules["parts.acme.example/metrics"].backend_port == "metrics"


def test_build_snapshot_keys_and_namespaces():
    snap = build_snapshot(
        context="test",
        server_version="v1.30.0",
        workload_items=[_load("deployment.json")],
        configmap_items=[],
        secret_items=[],
        service_items=[_load("service.json")],
        ingress_items=[_load("ingress.json")],
    )
    assert "prod/Deployment/parts-api" in snap.workloads
    assert "prod/parts-api" in snap.services
    assert snap.namespaces == ["prod"]
