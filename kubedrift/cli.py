"""
kubedrift CLI — entry point for all commands.

Commands:
  snapshot  Capture cluster state to a JSON file.
  diff      Compare two snapshot files and report drift.
  watch     Poll the cluster for drift against a baseline.
  report    Pretty-print a snapshot.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import click
from rich.console import Console

from kubedrift.diff import compute_diff
from kubedrift.kubectl import KubectlError
from kubedrift.report import diff_to_json, print_diff_report, print_snapshot_report
from kubedrift.snapshot import load_snapshot, save_snapshot, take_snapshot

console = Console()


@click.group()
@click.version_option(package_name="kubedrift", prog_name="kubedrift")
def main() -> None:
    """kubedrift — Kubernetes cluster state snapshot and drift detector."""


@main.command()
@click.option("--namespace", "-n", default=None, help="Namespace to snapshot (default: all).")
@click.option("--context", default=None, help="kubeconfig context (default: current).")
@click.option("--include-system", is_flag=True, help="Include kube-system and friends.")
@click.option("--out", default="snapshots", show_default=True, help="Directory to write into.")
@click.option("--label", default=None, help="Optional label included in the output filename.")
def snapshot(
    namespace: str | None, context: str | None, include_system: bool, out: str, label: str | None
) -> None:
    """Capture cluster state to a JSON snapshot file."""
    console.print("[dim]Reading cluster state via kubectl...[/dim]")
    try:
        snap = take_snapshot(namespace=namespace, context=context, include_system=include_system)
    except KubectlError as exc:
        raise click.ClickException(str(exc)) from exc

    os.makedirs(out, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    filename = os.path.join(out, f"snapshot_{ts}{suffix}.json")
    save_snapshot(snap, filename)

    console.print(
        f"Captured [bold]{len(snap.workloads)}[/bold] workloads, "
        f"{len(snap.configmaps)} configmaps, {len(snap.secrets)} secrets, "
        f"{len(snap.services)} services across {len(snap.namespaces)} namespaces."
    )
    console.print(f"Wrote [bold]{filename}[/bold]")


@main.command()
@click.argument("baseline", type=click.Path(exists=True))
@click.argument("current", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
@click.option(
    "--fail-on-breaking/--no-fail-on-breaking",
    default=True,
    show_default=True,
    help="Exit 1 if any BREAKING change is found (for CI gates).",
)
def diff(baseline: str, current: str, as_json: bool, fail_on_breaking: bool) -> None:
    """Compare two snapshot files and report drift."""
    result = compute_diff(load_snapshot(baseline), load_snapshot(current))
    if as_json:
        click.echo(diff_to_json(result))
    else:
        print_diff_report(result, console)
    if fail_on_breaking and result.has_breaking:
        sys.exit(1)


@main.command()
@click.option("--baseline", required=True, type=click.Path(exists=True), help="Baseline snapshot.")
@click.option("--namespace", "-n", default=None, help="Namespace to watch (default: all).")
@click.option("--context", default=None, help="kubeconfig context (default: current).")
@click.option("--interval", default=60, show_default=True, help="Seconds between polls.")
@click.option(
    "--max-iterations", default=None, type=int, help="Stop after N polls (default: forever)."
)
def watch(
    baseline: str,
    namespace: str | None,
    context: str | None,
    interval: int,
    max_iterations: int | None,
) -> None:
    """Poll the cluster for drift against a baseline. Exits 1 on BREAKING drift."""
    from kubedrift.watch import watch_for_drift

    base = load_snapshot(baseline)
    console.print(
        f"Watching for drift against [bold]{baseline}[/bold] every {interval}s. Ctrl-C to stop."
    )
    try:
        breaking = watch_for_drift(
            base,
            namespace=namespace,
            context=context,
            interval=interval,
            max_iterations=max_iterations,
            console=console,
        )
    except KubectlError as exc:
        raise click.ClickException(str(exc)) from exc
    if breaking:
        sys.exit(1)


@main.command()
@click.argument("snapshot_file", type=click.Path(exists=True))
def report(snapshot_file: str) -> None:
    """Pretty-print a snapshot file."""
    print_snapshot_report(load_snapshot(snapshot_file), console)


if __name__ == "__main__":
    main()
