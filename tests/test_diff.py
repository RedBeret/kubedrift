"""Tests for the drift classification engine.

One test per change category and change type. Hand-crafted minimal models
keep failures easy to diagnose.
"""

from kubedrift.diff import compute_diff
from kubedrift.models import ContainerSpec, EnvVar
from tests.helpers import configmap, deployment, secret, snap


def test_no_changes_yields_empty_diff():
    a = snap(workloads=deployment(), configmaps=configmap())
    b = snap(workloads=deployment(), configmaps=configmap())
    diff = compute_diff(a, b)
    assert diff.entries == []
    assert not diff.has_breaking


def test_deleted_workload_is_breaking():
    diff = compute_diff(snap(workloads=deployment()), snap())
    assert diff.has_breaking
    assert diff.entries[0].detail == "deployment deleted"


def test_new_workload_is_additive():
    diff = compute_diff(snap(), snap(workloads=deployment()))
    assert [e.category for e in diff.entries] == ["ADDITIVE"]


def test_image_change_gets_its_own_category():
    diff = compute_diff(
        snap(workloads=deployment(image="nginx:1.25")),
        snap(workloads=deployment(image="nginx:1.27")),
    )
    assert [e.category for e in diff.entries] == ["IMAGE"]
    assert "nginx:1.25 -> nginx:1.27" in diff.entries[0].detail
    assert not diff.has_breaking


def test_scale_to_zero_is_breaking():
    diff = compute_diff(
        snap(workloads=deployment(replicas=2)), snap(workloads=deployment(replicas=0))
    )
    assert diff.has_breaking
    assert "scaled to zero" in diff.entries[0].detail


def test_scale_down_is_informational_scale_up_is_additive():
    down = compute_diff(
        snap(workloads=deployment(replicas=5)), snap(workloads=deployment(replicas=2))
    )
    up = compute_diff(
        snap(workloads=deployment(replicas=2)), snap(workloads=deployment(replicas=5))
    )
    assert [e.category for e in down.entries] == ["INFORMATIONAL"]
    assert [e.category for e in up.entries] == ["ADDITIVE"]


def test_removed_env_var_is_breaking_added_is_additive():
    before = [ContainerSpec(name="app", image="i", env=[EnvVar("A", "sha256:1")])]
    after = [ContainerSpec(name="app", image="i", env=[EnvVar("B", "sha256:2")])]
    diff = compute_diff(
        snap(workloads=deployment(containers=before)),
        snap(workloads=deployment(containers=after)),
    )
    cats = {e.name: e.category for e in diff.entries}
    assert cats == {"A": "BREAKING", "B": "ADDITIVE"}


def test_env_value_change_is_informational():
    before = [ContainerSpec(name="app", image="i", env=[EnvVar("A", "sha256:1")])]
    after = [ContainerSpec(name="app", image="i", env=[EnvVar("A", "sha256:2")])]
    diff = compute_diff(
        snap(workloads=deployment(containers=before)),
        snap(workloads=deployment(containers=after)),
    )
    assert [e.category for e in diff.entries] == ["INFORMATIONAL"]


def test_removed_container_is_breaking():
    before = [ContainerSpec(name="app", image="i"), ContainerSpec(name="sidecar", image="s")]
    after = [ContainerSpec(name="app", image="i")]
    diff = compute_diff(
        snap(workloads=deployment(containers=before)),
        snap(workloads=deployment(containers=after)),
    )
    assert [(e.category, e.name) for e in diff.entries] == [("BREAKING", "sidecar")]


def test_resource_limit_change_is_informational():
    before = [ContainerSpec(name="app", image="i", limits={"memory": "128Mi"})]
    after = [ContainerSpec(name="app", image="i", limits={"memory": "256Mi"})]
    diff = compute_diff(
        snap(workloads=deployment(containers=before)),
        snap(workloads=deployment(containers=after)),
    )
    assert [e.category for e in diff.entries] == ["INFORMATIONAL"]


def test_configmap_key_removed_is_breaking_value_change_informational():
    before = configmap(keys={"A": "sha256:1", "B": "sha256:2"})
    after = configmap(keys={"B": "sha256:changed"})
    diff = compute_diff(snap(configmaps=before), snap(configmaps=after))
    cats = {e.name: e.category for e in diff.entries}
    assert cats == {"A": "BREAKING", "B": "INFORMATIONAL"}


def test_deleted_secret_is_breaking():
    diff = compute_diff(snap(secrets=secret()), snap())
    assert diff.has_breaking
    assert diff.entries[0].object_type == "secret"
