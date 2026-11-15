"""Test cho utd.state: run.json, chuỗi hash, phát hiện sửa ngoài luồng."""

import json

import pytest

from utd.io import atomic_write
from utd.state import (
    HashMismatchError,
    empty_state,
    load_state,
    mark_stage,
    record_artifact,
    record_gate,
    require_artifacts,
    run_path,
    save_state,
    verify_artifacts,
)


def _write_artifact(workspace, name, text):
    path = workspace / ".unittest-design" / "canonical" / name
    atomic_write(path, text)
    return path


def test_load_state_returns_empty_when_absent(tmp_path):
    assert load_state(tmp_path) == empty_state()


def test_save_and_load_roundtrip(tmp_path):
    state = empty_state()
    record_gate(state, "G1", True)
    save_state(tmp_path, state)

    loaded = load_state(tmp_path)
    assert loaded["gates"]["G1"]["passed"] is True
    assert loaded["updated_at"] is not None


def test_run_path_points_into_unittest_design(tmp_path):
    path = run_path(tmp_path)
    assert path.name == "run.json"
    assert path.parent.name == ".unittest-design"


def test_record_artifact_stores_sha256(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)

    assert state["artifacts"]["spec"]["sha256"]
    assert len(state["artifacts"]["spec"]["sha256"]) == 64


def test_verify_artifacts_clean_after_record(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    assert verify_artifacts(tmp_path) == []


def test_verify_detects_modified_artifact(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    atomic_write(artifact, '{"a":2}\n')

    problems = verify_artifacts(tmp_path)
    assert len(problems) == 1
    name, expected, actual = problems[0]
    assert name == "spec"
    assert expected != actual


def test_verify_detects_deleted_artifact(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    artifact.unlink()

    problems = verify_artifacts(tmp_path)
    assert len(problems) == 1
    assert problems[0][2] == "file không tồn tại"


def test_verify_ignores_newline_style_changes(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", 'line1\nline2\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    artifact.write_bytes(b"line1\r\nline2\r\n")

    assert verify_artifacts(tmp_path) == []


def test_require_artifacts_raises_on_mismatch(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    atomic_write(artifact, '{"a":9}\n')

    with pytest.raises(HashMismatchError) as excinfo:
        require_artifacts(tmp_path, ["spec"])
    assert "spec" in str(excinfo.value)


def test_require_artifacts_passes_when_clean(tmp_path):
    artifact = _write_artifact(tmp_path, "spec.json", '{"a":1}\n')
    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    require_artifacts(tmp_path, ["spec"])  # không ném


def test_require_artifacts_rejects_unrecorded_name(tmp_path):
    state = empty_state()
    save_state(tmp_path, state)

    with pytest.raises(HashMismatchError):
        require_artifacts(tmp_path, ["chua_ghi"])


def test_mark_stage_persists(tmp_path):
    state = empty_state()
    mark_stage(tmp_path, state, "ingest")

    saved = json.loads(run_path(tmp_path).read_text(encoding="utf-8"))
    assert saved["stage"] == "ingest"


def test_mark_stage_rejects_unknown_stage(tmp_path):
    with pytest.raises(ValueError):
        mark_stage(tmp_path, empty_state(), "khong_hop_le")


def test_record_gate_keeps_issues(tmp_path):
    state = empty_state()
    record_gate(state, "G3", False, ["BR-04 chưa có case vi phạm"])
    save_state(tmp_path, state)

    loaded = load_state(tmp_path)
    assert loaded["gates"]["G3"]["passed"] is False
    assert loaded["gates"]["G3"]["issues"] == ["BR-04 chưa có case vi phạm"]
