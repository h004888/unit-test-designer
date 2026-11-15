"""Test cho utd.interview: chữ ký, apply, USER_CHAT, batch consent, verify.

Trọng tâm: chứng minh cơ chế chống gian lận thật sự hoạt động — AI không thể
tự ghi câu trả lời mà vẫn qua cổng.
"""

import json
from pathlib import Path

import pytest

from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.interview.apply import (
    TamperError,
    apply_answers,
    apply_batch_consent,
    apply_chat_answer,
)
from utd.interview.export import build_ui_payload, export_html, export_ui_payload
from utd.interview.signature import make_salt, signature, verify_signature
from utd.interview.verify import EXIT_CLEAN, EXIT_PENDING, EXIT_TAMPER, verify_checklist
from utd.match.engine import build_checklist, load_rules, match_spec


def _spec() -> CanonicalSpec:
    module = Module(
        id="mod-1",
        module_name="Order API",
        sheet_name="POST_orders",
        flags=Flags(),
        endpoints=[
            Endpoint(
                id="ep-1",
                http_method="POST",
                path="/api/orders",
                auth=Auth(type="jwt"),
                params=[Param(name="quantity", type="integer", required=True)],
            )
        ],
    )
    module.flags.set("has_currency", True, source="inferred")
    return CanonicalSpec(project=Project(name="Demo", code="DEMO"), modules=[module])


@pytest.fixture
def checklist(tmp_path):
    ruleset = load_rules()
    spec = _spec()
    report = match_spec(spec, ruleset)
    data = build_checklist(report, spec)
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path, data


def _sign_answer(question, value, salt):
    return {
        "id": question["id"],
        "value": value,
        "nonce": question["nonce"],
        "sig": signature(question["id"], value, question["nonce"], salt),
    }


# --- signature --------------------------------------------------------------


def test_signature_is_deterministic():
    salt = "abc"
    assert signature("q1", "v1", "n1", salt) == signature("q1", "v1", "n1", salt)


def test_signature_changes_with_value():
    assert signature("q1", "v1", "n1", "s") != signature("q1", "v2", "n1", "s")


def test_signature_changes_with_nonce():
    assert signature("q1", "v1", "n1", "s") != signature("q1", "v1", "n2", "s")


def test_verify_signature_accepts_match():
    sig = signature("q1", "v1", "n1", "s")
    assert verify_signature("q1", "v1", "n1", "s", sig) is True


def test_verify_signature_rejects_tampered_value():
    sig = signature("q1", "v1", "n1", "s")
    assert verify_signature("q1", "v2", "n1", "s", sig) is False


def test_verify_signature_rejects_empty():
    assert verify_signature("q1", "v1", "n1", "s", "") is False


# --- export -----------------------------------------------------------------


def test_export_html_creates_self_contained_file(checklist, tmp_path):
    path, data = checklist
    out = tmp_path / "interview.html"
    export_html(data, out)

    text = out.read_text(encoding="utf-8")
    assert out.exists()
    assert "<script>" in text
    assert "http://" not in text and "https://" not in text, "không được có tài nguyên ngoài"
    assert "fetch(" not in text
    assert data["questions"][0]["nonce"] in text


def test_export_html_has_all_questions(checklist, tmp_path):
    _, data = checklist
    out = tmp_path / "interview.html"
    export_html(data, out)

    text = out.read_text(encoding="utf-8")
    for question in data["questions"]:
        assert question["id"] in text


def test_export_ui_payload_only_critical(checklist, tmp_path):
    _, data = checklist
    out = tmp_path / "ui.json"
    export_ui_payload(data, out)

    payload = json.loads(out.read_text(encoding="utf-8"))
    critical_ids = {q["id"] for q in data["questions"] if q["tier"] == "CRITICAL"}
    assert {q["id"] for q in payload["questions"]} == critical_ids
    assert payload["salt"]


def test_build_ui_payload_has_recommended_first(checklist):
    _, data = checklist
    payload = build_ui_payload(data)
    for question in payload["questions"]:
        assert question["options"][0].startswith("(Recommended)")


# --- apply_answers ----------------------------------------------------------


def test_apply_valid_answers_marked_user_ui(checklist, tmp_path):
    path, data = checklist
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"]
    answers = {
        "schema_version": 1,
        "salt": salt,
        "answers": [_sign_answer(q, "đồng ý " + q["id"], salt) for q in critical],
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    result = apply_answers(path, answers_path)

    assert result.applied == len(critical)
    assert result.by_source == {"USER_UI": len(critical)}

    saved = json.loads(path.read_text(encoding="utf-8"))
    for question in saved["questions"]:
        if question["tier"] == "CRITICAL":
            assert question["status"] == "ANSWERED"
            assert question["answered_by"] == "USER_UI"


def test_apply_rejects_tampered_value(checklist, tmp_path):
    path, data = checklist
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"][:1]
    item = _sign_answer(critical[0], "đồng ý", salt)
    item["value"] = "giá trị bị sửa sau khi ký"

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"schema_version": 1, "salt": salt, "answers": [item]}),
        encoding="utf-8",
    )

    with pytest.raises(TamperError) as excinfo:
        apply_answers(path, answers_path)
    assert "chữ ký" in str(excinfo.value).lower() or "sửa" in str(excinfo.value)


def test_apply_rejects_missing_nonce(checklist, tmp_path):
    path, data = checklist
    salt = make_salt()
    q = [x for x in data["questions"] if x["tier"] == "CRITICAL"][0]
    item = _sign_answer(q, "ok", salt)
    del item["nonce"]

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"schema_version": 1, "salt": salt, "answers": [item]}),
        encoding="utf-8",
    )

    with pytest.raises(TamperError) as excinfo:
        apply_answers(path, answers_path)
    assert "nonce" in str(excinfo.value).lower()


def test_apply_rejects_missing_salt(checklist, tmp_path):
    path, _ = checklist
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"schema_version": 1, "answers": []}), encoding="utf-8"
    )

    with pytest.raises(TamperError):
        apply_answers(path, answers_path)


def test_apply_rejects_one_bad_item_so_none_are_written(checklist, tmp_path):
    """Không mục nào được ghi nếu một mục sai: nguyên tử."""
    path, data = checklist
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"][:2]
    good = _sign_answer(critical[0], "ok", salt)
    bad = _sign_answer(critical[1], "ok", salt)
    bad["value"] = "sửa"

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"schema_version": 1, "salt": salt, "answers": [good, bad]}),
        encoding="utf-8",
    )

    with pytest.raises(TamperError):
        apply_answers(path, answers_path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert all(q["status"] == "PENDING" for q in saved["questions"])


def test_apply_rejects_nonce_from_other_question(checklist, tmp_path):
    path, data = checklist
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"][:2]
    item = _sign_answer(critical[0], "ok", salt)
    item["nonce"] = critical[1]["nonce"]

    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps({"schema_version": 1, "salt": salt,
                    "answers": [item]}), encoding="utf-8",
    )

    with pytest.raises(TamperError):
        apply_answers(path, answers_path)


# --- USER_CHAT --------------------------------------------------------------


def test_chat_answer_requires_evidence(checklist):
    path, data = checklist
    q = [x for x in data["questions"]
         if x["tier"] == "CRITICAL" and not str(x.get("rule_id", "")).startswith("FLAG:")][0]

    with pytest.raises(TamperError) as excinfo:
        apply_chat_answer(path, q["id"], "ok", evidence="")
    assert "evidence" in str(excinfo.value)


def test_chat_answer_records_evidence(checklist):
    path, data = checklist
    # chọn câu rule (không phải câu cờ) để giá trị tự do hợp lệ
    q = [x for x in data["questions"]
         if x["tier"] == "CRITICAL" and not str(x.get("rule_id", "")).startswith("FLAG:")][0]
    evidence = "Người dùng: quantity từ 1 đến 100"

    apply_chat_answer(path, q["id"], "1..100", evidence=evidence)

    saved = json.loads(path.read_text(encoding="utf-8"))
    target = next(x for x in saved["questions"] if x["id"] == q["id"])
    assert target["answered_by"] == "USER_CHAT"
    assert target["evidence"] == evidence


# --- batch consent ---------------------------------------------------------


def test_batch_consent_only_standard(checklist):
    path, data = checklist
    apply_batch_consent(path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    for question in saved["questions"]:
        if question["tier"] == "CRITICAL":
            assert question["status"] == "PENDING", "batch không được chạm CRITICAL"
        else:
            assert question["answered_by"] == "STANDARD_BATCH"


# --- verify ---------------------------------------------------------------


def test_verify_pending_returns_1_and_lists(checklist):
    _, data = checklist
    report = verify_checklist(data)
    assert report.exit_code == EXIT_PENDING
    assert report.pending_items


def test_verify_blocks_critical_answered_by_model(checklist):
    _, data = checklist
    for question in data["questions"]:
        question["status"] = "ANSWERED"
        question["answered_by"] = "MODEL" if question["tier"] == "CRITICAL" else "USER_UI"

    report = verify_checklist(data)
    assert report.exit_code == EXIT_TAMPER
    assert report.tampered


def test_verify_blocks_critical_batch_consent(checklist):
    _, data = checklist
    for question in data["questions"]:
        question["status"] = "ANSWERED"
        question["answered_by"] = "STANDARD_BATCH"

    report = verify_checklist(data)
    assert report.exit_code == EXIT_TAMPER


def test_verify_blocks_chat_without_evidence(checklist):
    _, data = checklist
    for question in data["questions"]:
        question["status"] = "ANSWERED"
        question["answered_by"] = "USER_CHAT"
        question["evidence"] = None

    report = verify_checklist(data)
    assert report.exit_code == EXIT_TAMPER


def test_verify_passes_when_critical_signed_and_standard_batched(checklist):
    path, data = checklist
    salt = make_salt()
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"]
    answers_path = path.with_name("answers.json")
    answers_path.write_text(
        json.dumps({
            "schema_version": 1, "salt": salt,
            "answers": [_sign_answer(q, "đồng ý", salt) for q in critical],
        }),
        encoding="utf-8",
    )
    apply_answers(path, answers_path)
    apply_batch_consent(path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    report = verify_checklist(saved)

    assert report.exit_code == EXIT_CLEAN
    assert report.pending == 0
    assert report.by_source.get("USER_UI") == len(critical)


def test_verify_handles_no_critical_questions():
    """Spec rỗng rule CRITICAL vẫn verify được nếu STANDARD đã duyệt."""
    data = {
        "questions": [
            {"id": "q1", "tier": "STANDARD", "status": "ANSWERED",
             "answered_by": "STANDARD_BATCH", "nonce": "n"},
        ]
    }
    assert verify_checklist(data).exit_code == EXIT_CLEAN


def test_verify_marks_chat_items_separately(checklist):
    path, data = checklist
    critical = [q for q in data["questions"] if q["tier"] == "CRITICAL"][:1]
    apply_chat_answer(path, critical[0]["id"], "ok", evidence="người dùng nói ok")

    saved = json.loads(path.read_text(encoding="utf-8"))
    report = verify_checklist(saved)
    # còn pending các CRITICAL khác -> exit 1, nhưng chat item phải được liệt kê
    assert critical[0]["id"] in report.chat_evidence_items
