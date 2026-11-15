"""Test cho utd.lock: sign-off, điều kiện khoá, hash chain."""

import json
from pathlib import Path

import pytest

from utd.interview.apply import apply_batch_consent, apply_answers
from utd.interview.export import build_ui_payload
from utd.interview.signature import make_salt, signature
from utd.interview.verify import verify_file
from utd.lock import (
    LockError,
    is_valid_sign,
    lock_spec,
    normalise_sign,
    verify_lock,
)
from utd.match.engine import build_checklist, load_rules, match_spec
from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project


def _prepare(tmp_path):
    """Chuẩn bị spec + checklist đã verify, trả về các đường dẫn."""
    module = Module(
        id="mod-1", module_name="Order API", sheet_name="POST_orders", flags=Flags(),
        endpoints=[Endpoint(id="ep-1", http_method="POST", path="/api/orders",
                            auth=Auth(type="jwt"),
                            params=[Param(name="quantity", type="integer", required=True)])],
    )
    module.flags.set("has_currency", True, source="inferred")
    spec_obj = CanonicalSpec(project=Project(name="Demo", code="DEMO"), modules=[module])

    report = match_spec(spec_obj, load_rules())
    data = build_checklist(report, spec_obj)

    canonical = tmp_path / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    spec_path = canonical / "spec.json"
    spec_path.write_text(
        json.dumps(spec_obj.to_dict(), ensure_ascii=False), encoding="utf-8"
    )

    interview = tmp_path / "interview"
    interview.mkdir(parents=True, exist_ok=True)
    checklist_path = interview / "checklist.json"
    checklist_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return spec_path, checklist_path, data, canonical


def _answer_value(question):
    """Câu hỏi cờ phải trả lời boolean; câu rule dùng câu trả lời chung."""
    return "Không" if str(question.get("rule_id", "")).startswith("FLAG:") else "ok"


def _answer_all(checklist_path, data, tmp_path):
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"]
    answers = {
        "schema_version": 1,
        "salt": salt,
        "answers": [
            {"id": q["id"], "value": _answer_value(q), "nonce": q["nonce"],
             "sig": signature(q["id"], _answer_value(q), q["nonce"], salt)}
            for q in critical
        ],
    }
    answers_path = tmp_path / "interview" / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")
    apply_answers(checklist_path, answers_path)
    if any(q["tier"] == "STANDARD" for q in data["questions"]):
        apply_batch_consent(checklist_path)
    return verify_file(checklist_path)


# --- sign-off -------------------------------------------------------------


@pytest.mark.parametrize("text", ["Chốt", "chốt", "CHỐT", "Chot", "OK", "ok", "  Chốt  "])
def test_valid_signs(text):
    assert is_valid_sign(text) is True


@pytest.mark.parametrize("text", ["", "khong", "chua chot", "yes", "huy"])
def test_invalid_signs(text):
    assert is_valid_sign(text) is False


def test_normalise_strips_diacritics():
    assert normalise_sign("Chốt") == "chot"
    assert normalise_sign("CHỐT") == "chot"


# --- lock -----------------------------------------------------------------


def test_lock_creates_files_when_all_conditions_met(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)

    result = lock_spec(
        spec_path, checklist_path,
        tmp_path / "interview" / "verified.json",
        sign="Chốt",
        out_dir=canonical,
    )

    assert result.locked_spec.exists()
    assert result.lock_file.exists()
    assert len(result.sha256) == 64

    locked = json.loads(result.locked_spec.read_text(encoding="utf-8"))
    assert locked["interview"]["signoff"] == "USER"
    assert len(locked["interview"]["answers"]) == len(data["questions"])


def test_lock_without_sign_raises(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)

    with pytest.raises(LockError) as excinfo:
        lock_spec(spec_path, checklist_path,
                  tmp_path / "interview" / "verified.json",
                  sign="khong dong y", out_dir=canonical)
    assert "Chốt" in str(excinfo.value) or "OK" in str(excinfo.value)


def test_lock_without_verified_raises(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)

    with pytest.raises(LockError) as excinfo:
        lock_spec(spec_path, checklist_path,
                  tmp_path / "interview" / "verified.json",
                  sign="OK", out_dir=canonical)
    assert "verify" in str(excinfo.value).lower()


def test_lock_after_checklist_modified_raises(tmp_path):
    """Sửa checklist sau verify -> sha lệch, lock phải từ chối (D6).

    Trước đây test này kiểm thông điệp "chưa trả lời"; với điều kiện sha mới,
    mọi thay đổi sau verify đều bị chặn sớm hơn. Trạng thái PENDING được
    `utd interview --verify` chặn ở cửa trước, nên không tới được lock.
    """
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)

    raw = json.loads(checklist_path.read_text(encoding="utf-8"))
    raw["questions"][0]["status"] = "PENDING"
    checklist_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(LockError) as excinfo:
        lock_spec(spec_path, checklist_path,
                  tmp_path / "interview" / "verified.json",
                  sign="Chốt", out_dir=canonical)
    message = str(excinfo.value)
    assert "đã thay đổi sau bước verify" in message
    assert not (canonical / "locked_spec.json").exists()


def test_lock_blocked_when_flags_unconfirmed(tmp_path):
    """Còn cờ source=default -> lock từ chối (D4b)."""
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)

    # Trả lời mọi câu TRỪ câu cờ, để cờ vẫn default
    salt = make_salt()
    non_flag = [
        q for q in data["questions"]
        if q["tier"] == "CRITICAL" and not str(q.get("rule_id", "")).startswith("FLAG:")
    ]
    answers = {
        "schema_version": 1,
        "salt": salt,
        "answers": [
            {"id": q["id"], "value": "ok", "nonce": q["nonce"],
             "sig": signature(q["id"], "ok", q["nonce"], salt)}
            for q in non_flag
        ],
    }
    answers_path = tmp_path / "interview" / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")
    apply_answers(checklist_path, answers_path)
    apply_batch_consent(checklist_path)

    # Không thể verify vì còn câu cờ PENDING -> test trực tiếp điều kiện cờ
    raw = json.loads(checklist_path.read_text(encoding="utf-8"))
    for question in raw["questions"]:
        question["status"] = "ANSWERED"
        question["answered_by"] = "USER_CHAT"
        question["evidence"] = "giả lập để đi tới kiểm tra cờ"
    checklist_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    verify_file(checklist_path)

    with pytest.raises(LockError) as excinfo:
        lock_spec(spec_path, checklist_path,
                  tmp_path / "interview" / "verified.json",
                  sign="Chốt", out_dir=canonical)

    message = str(excinfo.value)
    assert "cờ nghiệp vụ chưa được xác nhận" in message
    assert "has_quota" in message
    assert not (canonical / "locked_spec.json").exists()


def test_lock_copies_confirmed_flags_to_locked_spec(tmp_path):
    """Cờ người dùng xác nhận phải tới được locked_spec (D4c)."""
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)

    result = lock_spec(spec_path, checklist_path,
                       tmp_path / "interview" / "verified.json",
                       sign="Chốt", out_dir=canonical)

    locked = json.loads(result.locked_spec.read_text(encoding="utf-8"))
    module = locked["modules"][0]
    for name in ("has_quota", "has_dependencies", "has_unique_field"):
        assert module["flags"]["sources"][name] == "user"


def test_lock_no_files_created_on_failure(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)

    with pytest.raises(LockError):
        lock_spec(spec_path, checklist_path,
                  tmp_path / "interview" / "verified.json",
                  sign="OK", out_dir=canonical)

    assert not (canonical / "locked_spec.json").exists()
    assert not (canonical / "lock.sha256").exists()


# --- verify_lock ---------------------------------------------------------


def test_verify_lock_clean(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)
    result = lock_spec(spec_path, checklist_path,
                       tmp_path / "interview" / "verified.json",
                       sign="Chốt", out_dir=canonical)

    assert verify_lock(result.locked_spec, result.lock_file) == []


def test_verify_lock_detects_tamper(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)
    result = lock_spec(spec_path, checklist_path,
                       tmp_path / "interview" / "verified.json",
                       sign="OK", out_dir=canonical)

    locked = json.loads(result.locked_spec.read_text(encoding="utf-8"))
    locked["modules"][0]["endpoints"][0]["params"][0]["constraints"]["max"] = 999
    result.locked_spec.write_text(
        json.dumps(locked, ensure_ascii=False), encoding="utf-8"
    )

    problems = verify_lock(result.locked_spec, result.lock_file)
    assert problems
    assert "bị sửa" in problems[0]


def test_verify_lock_missing_files(tmp_path):
    problems = verify_lock(tmp_path / "nope.json", tmp_path / "nope.sha256")
    assert len(problems) == 2


def test_verify_lock_ignores_newline_style(tmp_path):
    spec_path, checklist_path, data, canonical = _prepare(tmp_path)
    _answer_all(checklist_path, data, tmp_path)
    result = lock_spec(spec_path, checklist_path,
                       tmp_path / "interview" / "verified.json",
                       sign="OK", out_dir=canonical)

    raw = result.locked_spec.read_bytes()
    result.locked_spec.write_bytes(raw.replace(b"\n", b"\r\n"))

    assert verify_lock(result.locked_spec, result.lock_file) == []
