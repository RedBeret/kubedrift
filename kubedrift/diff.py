"""
Drift classification engine.

Compares two SnapshotModels and returns a DiffResult with every change
categorized as BREAKING, IMAGE, ADDITIVE, or INFORMATIONAL.

The category judgment is opinionated:
  BREAKING      — deletions and changes likely to take traffic down or break
                  consumers: removed workloads/services/keys, scale-to-zero,
                  selector changes, removed ports or ingress routes
  IMAGE         — container image changes; separated out because they are the
                  most common intentional change and would otherwise drown out
                  everything else
  ADDITIVE      — new resources, new keys, scale-ups, new ports
  INFORMATIONAL — usually harmless but worth knowing: value changes behind an
                  unchanged key, resource request tweaks, type changes
"""

from __future__ import annotations

from kubedrift.models import (
    ContainerSpec,
    DiffEntry,
    DiffResult,
    SnapshotModel,
    WorkloadSchema,
)


def _entry(category: str, object_type: str, resource: str, name: str, detail: str) -> DiffEntry:
    return DiffEntry(
        category=category, object_type=object_type, resource=resource, name=name, detail=detail
    )


def _diff_container(b: ContainerSpec, c: ContainerSpec, resource: str) -> list[DiffEntry]:
    entries: list[DiffEntry] = []

    if b.image != c.image:
        entries.append(
            _entry("IMAGE", "container", resource, c.name, f"image {b.image} -> {c.image}")
        )

    b_env, c_env = b.env_map(), c.env_map()
    for name in sorted(set(b_env) - set(c_env)):
        entries.append(_entry("BREAKING", "env", resource, name, f"env var removed from {c.name}"))
    for name in sorted(set(c_env) - set(b_env)):
        entries.append(_entry("ADDITIVE", "env", resource, name, f"new env var on {c.name}"))
    for name in sorted(set(b_env) & set(c_env)):
        if b_env[name] != c_env[name]:
            entries.append(
                _entry(
                    "INFORMATIONAL",
                    "env",
                    resource,
                    name,
                    f"env var value or source changed on {c.name}",
                )
            )

    for kind, b_res, c_res in (
        ("requests", b.requests, c.requests),
        ("limits", b.limits, c.limits),
    ):
        if b_res != c_res:
            entries.append(
                _entry(
                    "INFORMATIONAL",
                    "container",
                    resource,
                    c.name,
                    f"resource {kind} {b_res or '{}'} -> {c_res or '{}'}",
                )
            )
    return entries


def _diff_workload(b: WorkloadSchema, c: WorkloadSchema, resource: str) -> list[DiffEntry]:
    entries: list[DiffEntry] = []

    if b.replicas != c.replicas:
        detail = f"replicas {b.replicas} -> {c.replicas}"
        if c.replicas == 0:
            entries.append(
                _entry("BREAKING", "workload", resource, c.name, detail + " (scaled to zero)")
            )
        elif b.replicas is not None and c.replicas is not None and c.replicas < b.replicas:
            entries.append(_entry("INFORMATIONAL", "workload", resource, c.name, detail))
        else:
            entries.append(_entry("ADDITIVE", "workload", resource, c.name, detail))

    b_cons, c_cons = b.container_map(), c.container_map()
    for name in sorted(set(b_cons) - set(c_cons)):
        entries.append(_entry("BREAKING", "container", resource, name, "container removed"))
    for name in sorted(set(c_cons) - set(b_cons)):
        entries.append(
            _entry("ADDITIVE", "container", resource, name, f"new container ({c_cons[name].image})")
        )
    for name in sorted(set(b_cons) & set(c_cons)):
        entries.extend(_diff_container(b_cons[name], c_cons[name], resource))
    return entries


def _diff_keyed(
    baseline_keys: dict[str, str],
    current_keys: dict[str, str],
    resource: str,
    object_type: str,
) -> list[DiffEntry]:
    """Shared logic for configmap/secret data keys (values are hashes)."""
    entries: list[DiffEntry] = []
    for key in sorted(set(baseline_keys) - set(current_keys)):
        entries.append(
            _entry(
                "BREAKING",
                object_type,
                resource,
                key,
                "key removed — anything mounting or referencing it will fail",
            )
        )
    for key in sorted(set(current_keys) - set(baseline_keys)):
        entries.append(_entry("ADDITIVE", object_type, resource, key, "new key"))
    for key in sorted(set(baseline_keys) & set(current_keys)):
        if baseline_keys[key] != current_keys[key]:
            entries.append(
                _entry("INFORMATIONAL", object_type, resource, key, "value changed (hash differs)")
            )
    return entries


def compute_diff(baseline: SnapshotModel, current: SnapshotModel) -> DiffResult:
    entries: list[DiffEntry] = []

    # --- workloads -------------------------------------------------------
    for key in sorted(set(baseline.workloads) - set(current.workloads)):
        w = baseline.workloads[key]
        entries.append(_entry("BREAKING", "workload", key, w.name, f"{w.kind.lower()} deleted"))
    for key in sorted(set(current.workloads) - set(baseline.workloads)):
        w = current.workloads[key]
        entries.append(_entry("ADDITIVE", "workload", key, w.name, f"new {w.kind.lower()}"))
    for key in sorted(set(baseline.workloads) & set(current.workloads)):
        entries.extend(_diff_workload(baseline.workloads[key], current.workloads[key], key))

    # --- configmaps and secrets -----------------------------------------
    for label, b_group, c_group in (
        ("configmap", baseline.configmaps, current.configmaps),
        ("secret", baseline.secrets, current.secrets),
    ):
        for key in sorted(set(b_group) - set(c_group)):
            entries.append(_entry("BREAKING", label, key, b_group[key].name, f"{label} deleted"))
        for key in sorted(set(c_group) - set(b_group)):
            entries.append(_entry("ADDITIVE", label, key, c_group[key].name, f"new {label}"))
        for key in sorted(set(b_group) & set(c_group)):
            entries.extend(_diff_keyed(b_group[key].keys, c_group[key].keys, key, label))

    return DiffResult(
        baseline_captured_at=baseline.captured_at,
        current_captured_at=current.captured_at,
        entries=entries,
    )
