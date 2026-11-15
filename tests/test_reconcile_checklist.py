"""Test append-merge: giữ nguyên câu cũ, thêm câu mới, ghi removed_questions."""

import json

import pytest

from utd.match.reconcile_checklist import (
    added_question_ids,
    checklist_digest,
    has_answered,
    reconcile_checklist,
)


def _q(qid, rule_id="BR-01", nonce="n1", status="PENDING", answer=None):
    return {
        "id": qid,
        "rule_id": rule_id,
        "nonce": nonce,
        "status": status,
        "answer": answer,
        "answered_by": "USER_UI" if status == "ANSWERED" else None,
        "tier": "CRITICAL",
    }


def _checklist(questions):
    return {"schema_version": 1, "questions": questions}


def test_old_questions_keep_identity():
    old = _checklist([_q("A", nonce="nA", status="ANSWERED", answer="có")])
    new = _checklist([
        _q("A", nonce="NEW_NONCE"),      # đề xuất nonce mới từ engine
        _q("B", nonce="nB"),
    ])

    merged = reconcile_checklist(old, new)

    by_id = {q["id"]: q for q in merged["questions"]}
    assert by_id["A"]["nonce"] == "nA", "nonce cũ phải được giữ"
    assert by_id["A"]["status"] == "ANSWERED"
    assert by_id["A"]["answer"] == "có"


def test_new_questions_appended():
    old = _checklist([_q("A")])
    new = _checklist([_q("A"), _q("B")])

    merged = reconcile_checklist(old, new)

    assert [q["id"] for q in merged["questions"]] == ["A", "B"]


def test_removed_questions_recorded_with_reason():
    old = _checklist([_q("A"), _q("GONE", rule_id="H-FIN-EXCHANGE-DRIFT-01")])
    new = _checklist([_q("A")])

    merged = reconcile_checklist(old, new, removed_reason="cờ has_currency chuyển false")

    removed = merged["removed_questions"]
    assert len(removed) == 1
    assert removed[0]["id"] == "GONE"
    assert removed[0]["rule_id"] == "H-FIN-EXCHANGE-DRIFT-01"
    assert removed[0]["removed_reason"] == "cờ has_currency chuyển false"


def test_previous_sha256_matches_old_digest():
    old = _checklist([_q("A")])
    new = _checklist([_q("A"), _q("B")])

    merged = reconcile_checklist(old, new)
    assert merged["previous_sha256"] == checklist_digest(old)


def test_first_run_has_no_previous_sha():
    merged = reconcile_checklist(None, _checklist([_q("A")]))
    assert "previous_sha256" not in merged or not merged.get("previous_sha256")
    assert merged["removed_questions"] == []


def test_added_question_ids_lists_only_new():
    old = _checklist([_q("A")])
    new = _checklist([_q("A"), _q("B"), _q("C")])
    assert added_question_ids(old, new) == ["B", "C"]


def test_added_question_ids_empty_when_no_previous():
    assert added_question_ids(None, _checklist([_q("A")])) == []


def test_has_answered():
    assert has_answered(_checklist([_q("A", status="ANSWERED")])) is True
    assert has_answered(_checklist([_q("A")])) is False
    assert has_answered(None) is False


def test_digest_is_stable_across_key_order():
    first = {"questions": [_q("A")], "coverage": {"a": 1, "b": 2}}
    second = {"coverage": {"b": 2, "a": 1}, "questions": [_q("A")]}
    assert checklist_digest(first) == checklist_digest(second)


def test_digest_changes_when_content_changes():
    first = _checklist([_q("A", nonce="n1")])
    second = _checklist([_q("A", nonce="n2")])
    assert checklist_digest(first) != checklist_digest(second)


def test_merge_preserves_answered_across_flag_change():
    """Kịch bản thật: câu A đã ký, cờ đổi làm câu B mới xuất hiện."""
    old = _checklist([_q("A", nonce="nA", status="ANSWERED", answer="đồng ý")])
    new = _checklist([_q("A", nonce="nA_new"), _q("B", rule_id="H-CONC-RACE-01")])

    merged = reconcile_checklist(old, new, removed_reason="cờ has_quota = true")
    by_id = {q["id"]: q for q in merged["questions"]}

    assert by_id["A"]["nonce"] == "nA"
    assert by_id["A"]["status"] == "ANSWERED"
    assert by_id["B"]["status"] == "PENDING"


def test_merge_idempotent_when_no_changes():
    old = _checklist([_q("A", nonce="nA"), _q("B", nonce="nB")])
    new = _checklist([_q("A"), _q("B")])

    merged = reconcile_checklist(old, new)

    assert [q["nonce"] for q in merged["questions"]] == ["nA", "nB"]
    assert merged["removed_questions"] == []
