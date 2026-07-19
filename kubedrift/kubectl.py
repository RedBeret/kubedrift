"""
Thin subprocess wrapper around kubectl.

kubedrift deliberately shells out to kubectl instead of depending on the
kubernetes Python client: kubectl already handles kubeconfig contexts and
exec-based auth plugins (EKS, GKE, AKS), so anything `kubectl get` can reach,
kubedrift can snapshot — with zero extra dependencies.

All functions here return parsed JSON. Everything downstream is pure and
testable without a cluster.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


class KubectlError(RuntimeError):
    """Raised when kubectl is missing or a kubectl command fails."""


def _run(args: list[str], context: str | None = None) -> str:
    if shutil.which("kubectl") is None:
        raise KubectlError("kubectl not found on PATH — install it or add it to PATH.")

    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
    cmd += args

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise KubectlError(f"`{' '.join(cmd)}` failed: {result.stderr.strip()}")
    return result.stdout


def get_items(
    kind: str, namespace: str | None = None, context: str | None = None
) -> list[dict[str, Any]]:
    """Return the .items list of `kubectl get <kind> -o json`.

    namespace=None means --all-namespaces.
    """
    args = ["get", kind, "-o", "json"]
    args += ["--namespace", namespace] if namespace else ["--all-namespaces"]
    return json.loads(_run(args, context)).get("items", [])


def current_context() -> str:
    try:
        return _run(["config", "current-context"]).strip()
    except KubectlError:
        return "unknown"


def server_version(context: str | None = None) -> str:
    try:
        data = json.loads(_run(["version", "-o", "json"], context))
        sv = data.get("serverVersion", {})
        return sv.get("gitVersion", "unknown")
    except (KubectlError, json.JSONDecodeError):
        return "unknown"


def apply_manifest(path: str, namespace: str, context: str | None = None) -> None:
    _run(["apply", "-f", path, "--namespace", namespace], context)


def delete_resource(
    kind: str, name: str, namespace: str, context: str | None = None, ignore_missing: bool = False
) -> None:
    args = ["delete", kind, name, "--namespace", namespace]
    if ignore_missing:
        args.append("--ignore-not-found")
    _run(args, context)


def ensure_namespace(namespace: str, context: str | None = None) -> None:
    manifest = json.dumps(
        {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}
    )
    cmd = ["kubectl"]
    if context:
        cmd += ["--context", context]
    cmd += ["apply", "-f", "-"]
    result = subprocess.run(cmd, input=manifest, capture_output=True, text=True)
    if result.returncode != 0:
        raise KubectlError(f"failed to create namespace {namespace}: {result.stderr.strip()}")


def delete_namespace(namespace: str, context: str | None = None) -> None:
    _run(["delete", "namespace", namespace, "--ignore-not-found", "--wait=false"], context)
