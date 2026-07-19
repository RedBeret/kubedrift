"""
Demo orchestration: deploy the baseline stack, snapshot it, apply drift,
snapshot again, and print the diff — all inside a throwaway namespace.
"""

from __future__ import annotations

from importlib.resources import as_file, files

from rich.console import Console

from kubedrift import kubectl
from kubedrift.diff import compute_diff
from kubedrift.report import print_diff_report
from kubedrift.snapshot import take_snapshot

DEMO_NAMESPACE = "kubedrift-demo"


def _apply_bundled(manifest_name: str, context: str | None) -> None:
    resource = files("kubedrift.demo").joinpath(manifest_name)
    with as_file(resource) as path:
        kubectl.apply_manifest(str(path), DEMO_NAMESPACE, context)


def run_demo(context: str | None, keep: bool, console: Console) -> None:
    console.print(f"[bold]1/5[/bold] Creating namespace [bold]{DEMO_NAMESPACE}[/bold]...")
    kubectl.ensure_namespace(DEMO_NAMESPACE, context)

    console.print(
        "[bold]2/5[/bold] Deploying baseline stack (4 workloads, configmap, secret, service)..."
    )
    _apply_bundled("baseline.yaml", context)

    console.print("[bold]3/5[/bold] Taking baseline snapshot...")
    baseline = take_snapshot(namespace=DEMO_NAMESPACE, context=context)

    console.print(
        "[bold]4/5[/bold] Applying drift (image bump, scale-to-zero, config changes, a deletion)..."
    )
    _apply_bundled("mutations.yaml", context)
    kubectl.delete_resource(
        "deployment", "legacy-cache", DEMO_NAMESPACE, context, ignore_missing=True
    )

    console.print("[bold]5/5[/bold] Taking second snapshot and diffing...\n")
    current = take_snapshot(namespace=DEMO_NAMESPACE, context=context)
    print_diff_report(compute_diff(baseline, current), console)

    if keep:
        console.print(
            f"[dim]Namespace {DEMO_NAMESPACE} kept — clean up with:"
            f" kubectl delete namespace {DEMO_NAMESPACE}[/dim]"
        )
    else:
        console.print(f"[dim]Cleaning up namespace {DEMO_NAMESPACE}...[/dim]")
        kubectl.delete_namespace(DEMO_NAMESPACE, context)
