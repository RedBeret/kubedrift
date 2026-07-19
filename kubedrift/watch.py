"""
Watch mode — poll the cluster for drift against a baseline snapshot.

Designed for CI gates and incident response: exits 1 the first time a
BREAKING change appears, so it can fail a pipeline or page a human.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from rich.console import Console

from kubedrift.diff import compute_diff
from kubedrift.models import DiffResult, SnapshotModel
from kubedrift.report import print_diff_report
from kubedrift.snapshot import take_snapshot


def watch_for_drift(
    baseline: SnapshotModel,
    namespace: str | None,
    context: str | None,
    interval: int,
    max_iterations: int | None = None,
    console: Console | None = None,
    snapshot_fn: Callable[[], SnapshotModel] | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> bool:
    """Poll until a BREAKING change is seen (returns True) or iterations run out.

    snapshot_fn/sleep_fn exist for testing — the default path hits the cluster.
    """
    con = console or Console()
    take = snapshot_fn or (lambda: take_snapshot(namespace=namespace, context=context))

    iteration = 0
    while True:
        iteration += 1
        current = take()
        diff: DiffResult = compute_diff(baseline, current)

        stamp = time.strftime("%H:%M:%S")
        if diff.has_breaking:
            con.print(f"[bold red]\\[{stamp}] BREAKING drift detected[/bold red]")
            print_diff_report(diff, con)
            return True
        if diff.entries:
            con.print(
                f"[yellow]\\[{stamp}] {len(diff.entries)} non-breaking changes[/yellow] "
                f"[dim](run `kubedrift diff` for details)[/dim]"
            )
        else:
            con.print(f"[dim]\\[{stamp}] no drift[/dim]")

        if max_iterations is not None and iteration >= max_iterations:
            return False
        sleep_fn(interval)
