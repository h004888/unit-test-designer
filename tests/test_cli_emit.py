"""Test CLI emit: chặn khi thiếu audit, chặn khi SSOT đổi, ghi run.json."""

import json
from pathlib import Path

import pytest

from utd.cli import (
    EXIT_GATE,
    EXIT_HASH_MISMATCH,
    EXIT_INVALID_INPUT,
    EXIT_PASS,
    main,
)

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


@pytest.fixture
def workspace(tmp_path):
    """Workspace đã chạy ingest -> inventory -> generate -> audit."""
    code = main(["ingest", "--from", "utd-v1", "--in", str(LEGACY),
                 "--workspace", str(tmp_path)])
    assert code == EXIT_PASS
    assert main(["inventory", "--workspace", str(tmp_path)]) == EXIT_PASS
    assert main(["generate", "--workspace", str(tmp_path),
                 "--source", ".unittest-design/canonical/spec.json"]) == EXIT_PASS
    assert main(["audit", "--workspace", str(tmp_path)]) == EXIT_PASS
    return tmp_path


def _emit(workspace, **kwargs):
    args = ["emit", "--workspace", str(workspace)]
    if "xlsx" in kwargs:
        args += ["--xlsx", kwargs["xlsx"]]
    if "md_dir" in kwargs:
        args += ["--md-dir", kwargs["md_dir"]]
    return main(args)


def test_emit_succeeds_after_audit(workspace):
    code = _emit(workspace, xlsx=".unittest-design/unit_test.xlsx",
                 md_dir=".unittest-design/docs")

    assert code == EXIT_PASS
    assert (workspace / ".unittest-design" / "unit_test.xlsx").exists()
    assert (workspace / ".unittest-design" / "docs" / "index.md").exists()


def test_emit_blocked_without_audit_report(workspace):
    report = workspace / ".unittest-design" / "audit" / "report.json"
    report.unlink()

    code = _emit(workspace, xlsx=".unittest-design/out.xlsx")
    assert code == EXIT_GATE
    assert not (workspace / ".unittest-design" / "out.xlsx").exists()


def test_emit_blocked_when_audit_failed(workspace):
    report = workspace / ".unittest-design" / "audit" / "report.json"
    data = json.loads(report.read_text(encoding="utf-8"))
    data["passed"] = False
    report.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    assert _emit(workspace, xlsx=".unittest-design/out.xlsx") == EXIT_GATE


def test_emit_blocked_when_ssot_modified_after_audit(workspace):
    ssot = workspace / ".unittest-design" / "canonical" / "unit_test_spec.json"
    data = json.loads(ssot.read_text(encoding="utf-8"))
    data["project"]["name"] = "Bị sửa tay"
    ssot.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    code = _emit(workspace, xlsx=".unittest-design/out.xlsx")
    assert code == EXIT_HASH_MISMATCH
    assert not (workspace / ".unittest-design" / "out.xlsx").exists()


def test_emit_requires_output_flag(workspace):
    assert _emit(workspace) == EXIT_INVALID_INPUT


def test_emit_missing_ssot_exit_2(tmp_path):
    code = main(["emit", "--workspace", str(tmp_path),
                 "--xlsx", "out.xlsx"])
    assert code == EXIT_INVALID_INPUT


def test_emit_records_run_state(workspace):
    _emit(workspace, xlsx=".unittest-design/unit_test.xlsx")

    run_file = workspace / ".unittest-design" / "run.json"
    state = json.loads(run_file.read_text(encoding="utf-8"))

    assert state["stage"] == "emit"
    emitted = [k for k in state["artifacts"] if k.startswith("emit:")]
    assert emitted
    for key in emitted:
        assert len(state["artifacts"][key]["sha256"]) == 64


def test_generate_writes_ssot_gate(workspace):
    run_file = workspace / ".unittest-design" / "run.json"
    state = json.loads(run_file.read_text(encoding="utf-8"))

    assert state["gates"]["generate"]["passed"] is True
    assert "ssot" in state["artifacts"]
