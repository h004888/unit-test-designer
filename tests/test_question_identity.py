"""Test id câu hỏi ổn định: đặt theo khoá gộp, không theo rule đại diện."""

import json
from pathlib import Path

import pytest

from utd.canonical import CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.ingest import convert
from utd.match.engine import load_rules, match_spec
from utd.match.question_id import (
    build_question_id,
    endpoint_question_id,
    param_question_id,
    parse_question_id,
)
from utd.match.reconcile_checklist import expanded_answered_questions

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"

ALL_FLAGS = (
    "has_status_field", "has_quota", "has_dependencies",
    "is_multi_tenant", "has_unique_field", "has_currency",
)


def _spec():
    return convert("utd-v1", json.loads(LEGACY.read_text(encoding="utf-8")))


def _snapshot(spec, ruleset):
    return {
        q.id: tuple(sorted(q.rule_ids))
        for q in match_spec(spec, ruleset).questions
        if not q.rule_id.startswith("FLAG:")
    }


def _set_all_flags(spec, value: bool):
    for module in spec.modules:
        for name in ALL_FLAGS:
            module.flags.set(name, value, source="user")


# --- 1.1 id helpers -------------------------------------------------------


def test_endpoint_id_format():
    assert endpoint_question_id("POST_api_orders", "state_machine_endpoint") == (
        "row:POST_api_orders:endpoint:state_machine_endpoint"
    )


def test_param_id_format():
    assert param_question_id("POST_api_orders", "quantity", "integer_param") == (
        "row:POST_api_orders:param:quantity:integer_param"
    )


def test_build_question_id_picks_kind():
    assert ":endpoint:" in build_question_id("S", "t")
    assert ":param:quantity:" in build_question_id("S", "t", "quantity")


def test_id_sanitises_separators():
    result = endpoint_question_id("sheet:with:colons", "target")
    assert result.count(":") == 3, result


def test_id_handles_spaces():
    result = param_question_id("My Sheet", "full name", "string_param")
    assert result == "row:My Sheet:param:full name:string_param"


def test_parse_roundtrip_endpoint():
    qid = endpoint_question_id("S1", "all_endpoints")
    parsed = parse_question_id(qid)
    assert parsed["kind"] == "endpoint"
    assert parsed["sheet_name"] == "S1"
    assert parsed["target_element"] == "all_endpoints"
    assert parsed["param_name"] is None


def test_parse_roundtrip_param():
    qid = param_question_id("S1", "quantity", "integer_param")
    parsed = parse_question_id(qid)
    assert parsed["kind"] == "param"
    assert parsed["param_name"] == "quantity"
    assert parsed["target_element"] == "integer_param"


def test_parse_rejects_old_format():
    assert parse_question_id("POST_api_orders_H-DATA-STR-01_quantity") == {}
    assert parse_question_id("") == {}


# --- 1.2 engine uses new ids ---------------------------------------------


def test_engine_ids_use_row_prefix():
    spec = _spec()
    report = match_spec(spec, load_rules())

    for question in report.questions:
        if question.rule_id.startswith("FLAG:"):
            continue
        assert question.id.startswith("row:"), question.id


def test_engine_endpoint_question_contains_endpoint_kind():
    spec = _spec()
    report = match_spec(spec, load_rules())
    endpoint_qs = [
        q for q in report.questions
        if not q.rule_id.startswith("FLAG:") and q.param_name is None
    ]
    assert endpoint_qs
    for question in endpoint_qs:
        assert ":endpoint:" in question.id


def test_engine_param_question_contains_param_name():
    spec = _spec()
    report = match_spec(spec, load_rules())
    param_qs = [q for q in report.questions if q.param_name]

    assert param_qs
    for question in param_qs:
        assert f":param:{question.param_name}:" in question.id


# --- 1.3 flag question ids unchanged ------------------------------------


def test_flag_question_ids_keep_old_format():
    spec = _spec()
    report = match_spec(spec, load_rules())
    flag_qs = [q for q in report.questions if q.rule_id.startswith("FLAG:")]

    assert len(flag_qs) == 6 * len(spec.modules)
    for question in flag_qs:
        assert question.id.endswith(f"_FLAG_{question.flag_name}")
        assert not question.id.startswith("row:")


# --- 1.4 order independence ---------------------------------------------


def test_ids_independent_of_rule_order():
    ruleset = load_rules()
    reversed_rules = type(ruleset)(rules=list(reversed(ruleset.rules)), parse_errors=[])

    spec_a = _spec()
    spec_b = _spec()

    ids_a = set(_snapshot(spec_a, ruleset))
    ids_b = set(_snapshot(spec_b, reversed_rules))

    assert ids_a == ids_b


# --- 2.1 expanded warnings ----------------------------------------------


def _q(qid, rule_ids, status="PENDING"):
    return {"id": qid, "rule_ids": rule_ids, "rule_id": rule_ids[0], "status": status}


def test_expanded_detects_answered_growth():
    old = {"questions": [_q("row:S:endpoint:t", ["R1"], status="ANSWERED")]}
    new = {"questions": [_q("row:S:endpoint:t", ["R1", "R2", "R3"])]}

    result = expanded_answered_questions(old, new)
    assert result == [("row:S:endpoint:t", ["R2", "R3"])]


def test_expanded_ignores_pending_questions():
    old = {"questions": [_q("row:S:endpoint:t", ["R1"], status="PENDING")]}
    new = {"questions": [_q("row:S:endpoint:t", ["R1", "R2"])]}

    assert expanded_answered_questions(old, new) == []


def test_expanded_ignores_shrinking():
    old = {"questions": [_q("row:S:endpoint:t", ["R1", "R2"], status="ANSWERED")]}
    new = {"questions": [_q("row:S:endpoint:t", ["R1"])]}

    assert expanded_answered_questions(old, new) == []


def test_expanded_ignores_new_questions():
    old = {"questions": []}
    new = {"questions": [_q("row:S:endpoint:t", ["R1"])]}

    assert expanded_answered_questions(old, new) == []


def test_expanded_handles_missing_old():
    assert expanded_answered_questions(None, {"questions": []}) == []


# --- 3.1-3.3 measured behaviour on fixture ------------------------------


def test_no_id_lost_when_all_flags_flip():
    ruleset = load_rules()
    spec = _spec()

    before = _snapshot(spec, ruleset)
    _set_all_flags(spec, True)
    after = _snapshot(spec, ruleset)

    lost = set(before) - set(after)
    assert lost == set(), f"mất {len(lost)} id: {sorted(lost)[:5]}"


def test_eight_new_questions_when_all_flags_flip():
    ruleset = load_rules()
    spec = _spec()

    before = _snapshot(spec, ruleset)
    _set_all_flags(spec, True)
    after = _snapshot(spec, ruleset)

    new = set(after) - set(before)
    assert len(new) == 8, f"có {len(new)} câu mới: {sorted(new)}"


def test_six_questions_expand_when_all_flags_flip():
    ruleset = load_rules()
    spec = _spec()

    before = _snapshot(spec, ruleset)
    _set_all_flags(spec, True)
    after = _snapshot(spec, ruleset)

    expanded = [k for k in set(before) & set(after) if before[k] != after[k]]
    assert len(expanded) == 6, f"có {len(expanded)}: {sorted(expanded)}"


def test_expanded_rules_are_still_applicable():
    """Mọi rule trong câu bị mất id (nếu có) phải vẫn áp dụng."""
    ruleset = load_rules()
    spec = _spec()

    before = _snapshot(spec, ruleset)
    _set_all_flags(spec, True)
    report_after = match_spec(spec, ruleset)
    after = {q.id: tuple(sorted(q.rule_ids)) for q in report_after.questions
             if not q.rule_id.startswith("FLAG:")}

    lost_rules = set()
    for qid in set(before) - set(after):
        lost_rules.update(before[qid])

    for rule_id in lost_rules:
        assert rule_id in report_after.matched_rule_ids or rule_id in {
            s.rule_id for s in report_after.skipped
        }


# --- 3.4 answers preserved ---------------------------------------------


def test_answered_question_keeps_answer_when_rules_expand():
    ruleset = load_rules()
    spec = _spec()

    before = match_spec(spec, ruleset)
    target = next(
        q for q in before.questions
        if not q.rule_id.startswith("FLAG:") and q.param_name is None
        and q.id.startswith("row:")
    )
    old = {
        "questions": [{
            "id": target.id,
            "rule_ids": list(target.rule_ids),
            "status": "ANSWERED",
            "answer": "câu trả lời cũ",
            "nonce": "abc123",
            "answered_by": "USER_UI",
        }]
    }

    _set_all_flags(spec, True)
    after = match_spec(spec, ruleset)
    matching = next((q for q in after.questions if q.id == target.id), None)
    assert matching is not None, "id phải còn sau khi bật cờ"

    new = {"questions": [matching.to_dict()]}
    from utd.match.reconcile_checklist import reconcile_checklist

    merged = reconcile_checklist(old, new)
    saved = next(q for q in merged["questions"] if q["id"] == target.id)

    assert saved["nonce"] == "abc123"
    assert saved["status"] == "ANSWERED"
    assert saved["answer"] == "câu trả lời cũ"
