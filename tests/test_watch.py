"""Tests for watch mode using injected snapshot/sleep functions — no cluster."""

from rich.console import Console

from kubedrift.watch import watch_for_drift
from tests.helpers import deployment, snap


def _console():
    return Console(file=open("/dev/null", "w"), force_terminal=False)


def test_watch_returns_true_on_breaking_drift():
    baseline = snap(workloads=deployment(replicas=2))
    drifted = snap(workloads=deployment(replicas=0))
    result = watch_for_drift(
        baseline,
        namespace=None,
        context=None,
        interval=0,
        max_iterations=5,
        console=_console(),
        snapshot_fn=lambda: drifted,
        sleep_fn=lambda _: None,
    )
    assert result is True


def test_watch_returns_false_when_no_breaking_drift():
    baseline = snap(workloads=deployment(image="nginx:1.25"))
    image_only = snap(workloads=deployment(image="nginx:1.27"))
    result = watch_for_drift(
        baseline,
        namespace=None,
        context=None,
        interval=0,
        max_iterations=3,
        console=_console(),
        snapshot_fn=lambda: image_only,
        sleep_fn=lambda _: None,
    )
    assert result is False


def test_watch_respects_max_iterations():
    calls = []
    baseline = snap()
    watch_for_drift(
        baseline,
        namespace=None,
        context=None,
        interval=0,
        max_iterations=3,
        console=_console(),
        snapshot_fn=lambda: (calls.append(1), baseline)[1],
        sleep_fn=lambda _: None,
    )
    assert len(calls) == 3
