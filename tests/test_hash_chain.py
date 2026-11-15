"""Test chuỗi hash: sửa artifact ngoài luồng phải bị stage sau phát hiện (exit 5).

Đây là cơ chế thay cho việc tin vào lời khai. Ba artifact được kiểm:
  - canonical/spec.json         (ingest -> inventory)
  - canonical/locked_spec.json  (lock -> generate)
  - canonical/unit_test_spec.json (audit -> emit)
"""

import json
from pathlib import Path

import pytest

from utd.cli import (
    EXIT_HASH_MISMATCH,
    EXIT_PASS,
    main,
)
from utd.io import atomic_write, sha256_file
from utd.lock import lock_spec, verify_lock
from utd.state import (
    HashMismatchError,
    empty_state,
    load_state,
    record_artifact,
    require_artifacts,
    save_state,
    verify_artifacts,
)

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def test_artifact_tamper_detected_by_state(tmp_path):
    artifact = tmp_path / "canonical" / "spec.json"
    atomic_write(artifact, '{"a":1}\n')

    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    atomic_write(artifact, '{"a":2}\n')

    with pytest.raises(HashMismatchError):
        require_artifacts(tmp_path, ["spec"])


def test_newline_only_change_not_flagged(tmp_path):
    artifact = tmp_path / "spec.json"
    atomic_write(artifact, 'line1\nline2\n')

    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    artifact.write_bytes(b"line1\r\nline2\r\n")
    assert verify_artifacts(tmp_path) == []


def test_deleted_artifact_flagged(tmp_path):
    artifact = tmp_path / "spec.json"
    atomic_write(artifact, "x")

    state = empty_state()
    record_artifact(tmp_path, state, "spec", artifact)
    save_state(tmp_path, state)

    artifact.unlink()
    problems = verify_artifacts(tmp_path)
    assert problems
    assert problems[0][2] == "file không tồn tại"


def _confirmed_flags_payload():
    """Sáu cờ đều source=user để lock không chặn vì lý do cờ."""
    names = ("has_status_field", "has_quota", "has_dependencies",
             "is_multi_tenant", "has_unique_field", "has_currency")
    return {
        "values": {n: False for n in names},
        "sources": {n: "user" for n in names},
    }


def test_lock_hash_detects_spec_tamper(tmp_path):
    """Sửa locked_spec.json sau khi khoá -> verify_lock báo lệch."""
    spec = tmp_path / "spec.json"
    atomic_write(spec, json.dumps(
        {"modules": [{"id": "m1", "sheet_name": "S",
                      "flags": _confirmed_flags_payload()}]},
        ensure_ascii=False,
    ))

    checklist = tmp_path / "checklist.json"
    atomic_write(checklist, json.dumps(
        {"questions": [], "modules": [{"id": "m1", "sheet_name": "S",
                                       "flags": _confirmed_flags_payload()}]},
        ensure_ascii=False,
    ))

    from utd.match.reconcile_checklist import checklist_digest

    verified = tmp_path / "verified.json"
    atomic_write(verified, json.dumps({
        "verified": True,
        "checklist_sha256": checklist_digest(json.loads(checklist.read_text(encoding="utf-8"))),
    }))

    result = lock_spec(spec, checklist, verified, sign="Chốt", out_dir=tmp_path)

    data = json.loads(result.locked_spec.read_text(encoding="utf-8"))
    data["modules"] = [{"bi": "sua"}]
    result.locked_spec.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    problems = verify_lock(result.locked_spec, result.lock_file)
    assert problems
    assert "bị sửa" in problems[0]


def test_generate_blocked_when_locked_spec_tampered(tmp_path):
    """E2E: lock -> sửa locked_spec -> generate phải exit 5."""
    assert main(["ingest", "--from", "utd-v1", "--in", str(LEGACY),
                 "--workspace", str(tmp_path)]) == EXIT_PASS
    assert main(["inventory", "--workspace", str(tmp_path)]) == EXIT_PASS

    checklist_path = tmp_path / ".unittest-design" / "interview" / "checklist.json"
    checklist = json.loads(checklist_path.read_text(encoding="utf-8"))

    # trả lời mọi câu bằng USER_CHAT để qua verify; câu cờ cần giá trị boolean
    from utd.match.flags_questions import coerce_flag_value, parse_flag_rule_id

    questions = checklist["questions"]
    for question in questions:
        question["status"] = "ANSWERED"
        question["answered_by"] = "USER_CHAT"
        question["evidence"] = "người dùng trả lời trong hội thoại"
        flag_name = parse_flag_rule_id(str(question.get("rule_id", "")))
        if flag_name:
            question["answer"] = "Không"
            module_id = question.get("module_id")
            for module in checklist.get("modules", []):
                if module.get("id") == module_id:
                    flags = module.setdefault("flags", {})
                    flags.setdefault("values", {})[flag_name] = False
                    flags.setdefault("sources", {})[flag_name] = "user"
        else:
            question["answer"] = "theo đặc tả"
    checklist_path.write_text(
        json.dumps(checklist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    from utd.interview.verify import verify_file

    report = verify_file(checklist_path)
    assert report.passed

    canonical = tmp_path / ".unittest-design" / "canonical"
    result = lock_spec(
        canonical / "spec.json",
        checklist_path,
        tmp_path / ".unittest-design" / "interview" / "verified.json",
        sign="Chốt",
        out_dir=canonical,
    )
    assert result.locked_spec.exists()

    # sửa locked spec sau khi khoá
    data = json.loads(result.locked_spec.read_text(encoding="utf-8"))
    data["modules"][0]["endpoints"][0]["params"][0]["constraints"]["max"] = 99999
    result.locked_spec.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    code = main(["generate", "--workspace", str(tmp_path),
                 "--source", ".unittest-design/canonical/locked_spec.json"])
    assert code == EXIT_HASH_MISMATCH


def test_sha256_stable_across_reads(tmp_path):
    artifact = tmp_path / "a.json"
    atomic_write(artifact, "nội dung tiếng Việt")
    first = sha256_file(artifact)
    second = sha256_file(artifact)
    assert first == second
    assert len(first) == 64
