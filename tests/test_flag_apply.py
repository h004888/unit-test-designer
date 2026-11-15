"""Test: trả lời câu cờ cập nhật flags, bỏ qua mục đã biến mất, khoá chặn khi thiếu cờ."""

import json
from pathlib import Path

import pytest

from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.interview.apply import TamperError, apply_answers
from utd.interview.signature import make_salt, signature
from utd.match.engine import build_checklist, load_rules, match_spec
from utd.match.flags_questions import build_flag_questions


def _module(sheet="POST_orders", module_id="mod-1") -> Module:
    return Module(
        id=module_id,
        module_name="Order API",
        sheet_name=sheet,
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


@pytest.fixture
def checklist_file(tmp_path):
    module = _module()
    spec = CanonicalSpec(project=Project(name="Demo"), modules=[module])
    report = match_spec(spec, load_rules())
    checklist = build_checklist(report, spec)
    path = tmp_path / "checklist.json"
    path.write_text(json.dumps(checklist, ensure_ascii=False), encoding="utf-8")
    return path, checklist


def _signed_answers(questions, values, salt):
    return {
        "schema_version": 1,
        "salt": salt,
        "answers": [
            {
                "id": q["id"],
                "value": values[q["id"]],
                "nonce": q["nonce"],
                "sig": signature(q["id"], values[q["id"]], q["nonce"], salt),
            }
            for q in questions
            if q["id"] in values
        ],
    }


def test_answering_flag_sets_flag_and_source(checklist_file, tmp_path):
    path, checklist = checklist_file
    flag_q = [q for q in checklist["questions"] if q["rule_id"] == "FLAG:has_quota"][0]

    salt = make_salt()
    answers = _signed_answers([flag_q], {flag_q["id"]: "Có"}, salt)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    result = apply_answers(path, answers_path)
    assert result.applied == 1

    saved = json.loads(path.read_text(encoding="utf-8"))
    module = saved["modules"][0]
    assert module["flags"]["values"]["has_quota"] is True
    assert module["flags"]["sources"]["has_quota"] == "user"


def test_answering_flag_false_records_user_source(checklist_file, tmp_path):
    path, checklist = checklist_file
    flag_q = [q for q in checklist["questions"] if q["rule_id"] == "FLAG:has_unique_field"][0]

    salt = make_salt()
    answers = _signed_answers([flag_q], {flag_q["id"]: "Không"}, salt)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    apply_answers(path, answers_path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    flags = saved["modules"][0]["flags"]
    assert flags["values"]["has_unique_field"] is False
    assert flags["sources"]["has_unique_field"] == "user"


def test_unknown_flag_answer_rejected(checklist_file, tmp_path):
    path, checklist = checklist_file
    flag_q = [q for q in checklist["questions"] if q["rule_id"] == "FLAG:has_quota"][0]

    salt = make_salt()
    answers = _signed_answers([flag_q], {flag_q["id"]: "tuỳ"}, salt)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    with pytest.raises(TamperError) as excinfo:
        apply_answers(path, answers_path)
    assert "has_quota" in str(excinfo.value)
    assert "đọc được giá trị cờ" in str(excinfo.value)


def test_answer_marks_flags_regenerated(checklist_file, tmp_path):
    path, checklist = checklist_file
    flag_q = [q for q in checklist["questions"] if q["rule_id"] == "FLAG:has_quota"][0]

    salt = make_salt()
    answers = _signed_answers([flag_q], {flag_q["id"]: "Có"}, salt)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    result = apply_answers(path, answers_path)
    assert result.regenerated_from_flags is True


def test_non_flag_answer_does_not_set_regenerated(checklist_file, tmp_path):
    path, checklist = checklist_file
    rule_q = [q for q in checklist["questions"]
              if not str(q["rule_id"]).startswith("FLAG:") and q["tier"] == "CRITICAL"][0]

    salt = make_salt()
    answers = _signed_answers([rule_q], {rule_q["id"]: "theo đặc tả"}, salt)
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    result = apply_answers(path, answers_path)
    assert result.regenerated_from_flags is False


def test_removed_question_skipped_when_sha_matches(tmp_path, checklist_file):
    path, checklist = checklist_file
    from utd.match.reconcile_checklist import checklist_digest

    previous_sha = checklist_digest(checklist)
    checklist["removed_questions"] = [
        {"id": "GONE_1", "rule_id": "H-FIN-EXCHANGE-DRIFT-01",
         "removed_reason": "cờ has_currency chuyển false"}
    ]
    checklist["previous_sha256"] = previous_sha
    path.write_text(json.dumps(checklist, ensure_ascii=False), encoding="utf-8")

    salt = make_salt()
    answers = {
        "schema_version": 1,
        "salt": salt,
        "checklist_sha256": previous_sha,
        "answers": [{
            "id": "GONE_1",
            "value": "theo đặc tả",
            "nonce": "n-any",
            "sig": signature("GONE_1", "theo đặc tả", "n-any", salt),
        }],
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    result = apply_answers(path, answers_path)
    assert result.skipped_unknown == ["GONE_1"]
    assert result.applied == 0


def test_removed_question_rejected_when_sha_missing(tmp_path, checklist_file):
    path, checklist = checklist_file
    checklist["removed_questions"] = [
        {"id": "GONE_1", "rule_id": "X", "removed_reason": "test"}
    ]
    checklist["previous_sha256"] = "deadbeef"
    path.write_text(json.dumps(checklist, ensure_ascii=False), encoding="utf-8")

    salt = make_salt()
    answers = {
        "schema_version": 1,
        "salt": salt,
        "answers": [{
            "id": "GONE_1",
            "value": "x",
            "nonce": "n",
            "sig": signature("GONE_1", "x", "n", salt),
        }],
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    with pytest.raises(TamperError):
        apply_answers(path, answers_path)


def test_unknown_id_not_in_removed_still_rejected(tmp_path, checklist_file):
    path, _ = checklist_file
    salt = make_salt()
    answers = {
        "schema_version": 1,
        "salt": salt,
        "answers": [{
            "id": "RAC_ID",
            "value": "x",
            "nonce": "n",
            "sig": signature("RAC_ID", "x", "n", salt),
        }],
    }
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(answers), encoding="utf-8")

    with pytest.raises(TamperError) as excinfo:
        apply_answers(path, answers_path)
    assert "RAC_ID" in str(excinfo.value)
