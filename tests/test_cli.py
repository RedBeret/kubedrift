"""CLI tests via click's CliRunner — exit codes, JSON output, error paths."""

import json

from click.testing import CliRunner

from kubedrift.cli import main
from kubedrift.snapshot import save_snapshot
from tests.helpers import deployment, snap


def _write(tmp_path, name, model):
    path = tmp_path / name
    save_snapshot(model, str(path))
    return str(path)


def test_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "kubedrift" in result.output


def test_diff_exits_1_on_breaking(tmp_path):
    a = _write(tmp_path, "a.json", snap(workloads=deployment()))
    b = _write(tmp_path, "b.json", snap())
    result = CliRunner().invoke(main, ["diff", a, b])
    assert result.exit_code == 1
    assert "BREAKING" in result.output


def test_diff_no_fail_flag_exits_0(tmp_path):
    a = _write(tmp_path, "a.json", snap(workloads=deployment()))
    b = _write(tmp_path, "b.json", snap())
    result = CliRunner().invoke(main, ["diff", a, b, "--no-fail-on-breaking"])
    assert result.exit_code == 0


def test_diff_clean_exits_0(tmp_path):
    a = _write(tmp_path, "a.json", snap(workloads=deployment()))
    b = _write(tmp_path, "b.json", snap(workloads=deployment()))
    result = CliRunner().invoke(main, ["diff", a, b])
    assert result.exit_code == 0
    assert "No drift" in result.output


def test_diff_json_output_is_parseable(tmp_path):
    a = _write(tmp_path, "a.json", snap(workloads=deployment(image="nginx:1.25")))
    b = _write(tmp_path, "b.json", snap(workloads=deployment(image="nginx:1.27")))
    result = CliRunner().invoke(main, ["diff", a, b, "--json", "--no-fail-on-breaking"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["entries"][0]["category"] == "IMAGE"


def test_diff_missing_file_errors():
    result = CliRunner().invoke(main, ["diff", "/no/such/a.json", "/no/such/b.json"])
    assert result.exit_code != 0


def test_report_renders_snapshot(tmp_path):
    path = _write(tmp_path, "snap.json", snap(workloads=deployment(name="parts-api")))
    result = CliRunner().invoke(main, ["report", path])
    assert result.exit_code == 0
    assert "parts-api" in result.output
