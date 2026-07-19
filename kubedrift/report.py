"""
Rich terminal rendering for kubedrift output.

Keeps all display logic here so cli.py stays thin and report
output can be tested by capturing console output.
"""

from __future__ import annotations

import json

from rich import box
from rich.console import Console
from rich.table import Table

from kubedrift.models import DiffResult, SnapshotModel

CATEGORY_STYLES = {
    "BREAKING": ("red", "x"),
    "IMAGE": ("magenta", "~"),
    "ADDITIVE": ("green", "+"),
    "INFORMATIONAL": ("yellow", "o"),
}

CATEGORY_ORDER = ["BREAKING", "IMAGE", "ADDITIVE", "INFORMATIONAL"]


def print_snapshot_report(snap: SnapshotModel, console: Console | None = None) -> None:
    """Render a snapshot summary — workloads table plus resource counts."""
    con = console or Console()

    con.print(f"\n[bold]Cluster snapshot[/bold]  -  captured {snap.captured_at}")
    con.print(f"[dim]context: {snap.context}  |  server: {snap.server_version}[/dim]")
    con.print(f"[dim]namespaces: {', '.join(snap.namespaces) or '(none)'}[/dim]\n")

    tbl = Table(box=box.SIMPLE_HEAD, header_style="bold cyan")
    tbl.add_column("workload")
    tbl.add_column("replicas", justify="right")
    tbl.add_column("containers", style="dim")

    for key, w in sorted(snap.workloads.items()):
        images = ", ".join(f"{c.name}={c.image}" for c in w.containers)
        tbl.add_row(key, "-" if w.replicas is None else str(w.replicas), images)
    con.print(tbl)

    con.print(
        f"[dim]{len(snap.configmaps)} configmaps  |  {len(snap.secrets)} secrets  |  "
        f"{len(snap.services)} services  |  {len(snap.ingresses)} ingresses[/dim]\n"
    )


def print_diff_report(diff: DiffResult, console: Console | None = None) -> None:
    con = console or Console()

    con.print(
        f"\n[bold]Drift report[/bold]  -  baseline {diff.baseline_captured_at}"
        f"  ->  current {diff.current_captured_at}\n"
    )

    if not diff.entries:
        con.print("[green]No drift detected.[/green]\n")
        return

    for category in CATEGORY_ORDER:
        entries = diff.by_category(category)
        if not entries:
            continue
        color, marker = CATEGORY_STYLES[category]
        con.print(f"[bold {color}]{category}[/bold {color}] ({len(entries)})")
        for e in entries:
            con.print(
                f"  [{color}]{marker}[/{color}] {e.resource}  [bold]{e.name}[/bold]: {e.detail}"
            )
        con.print()

    counts = "  ".join(
        f"{cat.lower()}={len(diff.by_category(cat))}"
        for cat in CATEGORY_ORDER
        if diff.by_category(cat)
    )
    con.print(f"[dim]{len(diff.entries)} changes  ({counts})[/dim]\n")


def diff_to_json(diff: DiffResult) -> str:
    """Machine-readable diff for piping into other tools."""
    return json.dumps(diff.to_dict(), indent=2, sort_keys=True)
