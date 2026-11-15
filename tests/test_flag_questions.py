"""Test cho sáu câu hỏi cờ: sinh, nội dung, id ổn định, coerce giá trị."""

import json
from pathlib import Path

import pytest

from utd.canonical import CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.match.engine import load_rules, match_spec
from utd.match.flags_questions import (
    FLAG_META,
    build_flag_question,
    build_flag_questions,
    coerce_flag_value,
    flag_question_id,
    flag_rule_id,
    parse_flag_rule_id,
    parse_flag_target,
)

ROOT = Path(__file__).parent.parent


def _module(sheet="POST_api_orders", module_id="mod-1") -> Module:
    return Module(
        id=module_id,
        module_name="Order API",
        sheet_name=sheet,
        flags=Flags(),
        endpoints=[
            Endpoint(
                id=f"ep-{module_id}",
                http_method="POST",
                path="/api/orders",
                params=[Param(name="quantity", type="integer", required=True)],
            )
        ],
    )


def _spec(modules=2) -> CanonicalSpec:
    return CanonicalSpec(
        project=Project(name="Demo"),
        modules=[_module(sheet=f"sheet_{i}", module_id=f"mod-{i}") for i in range(modules)],
    )


# --- 1.1 FLAG_META ---------------------------------------------------------


def test_flag_meta_has_six_entries():
    assert len(FLAG_META) == 6


def test_flag_meta_names_match_canonical():
    from utd.canonical import FLAG_NAMES

    assert set(FLAG_META) == set(FLAG_NAMES)


def test_flag_meta_marks_three_inferred():
    inferred = {name for name, meta in FLAG_META.items() if meta.inferred}
    assert inferred == {"has_status_field", "is_multi_tenant", "has_currency"}


def test_flag_meta_labels_not_empty():
    for name, meta in FLAG_META.items():
        assert meta.label.strip(), name
        assert meta.question_when_unknown.strip(), name


# --- 1.2 build_flag_questions --------------------------------------------


def test_one_module_yields_six_questions():
    assert len(build_flag_questions(_module())) == 6


def test_two_modules_yield_twelve_questions():
    questions = []
    for module in _spec(2).modules:
        questions.extend(build_flag_questions(module))
    assert len(questions) == 12


def test_flag_question_ids_follow_schema():
    questions = build_flag_questions(_module(sheet="POST_api_orders"))

    for question in questions:
        assert question.id == flag_question_id("POST_api_orders", question.flag_name)
        assert question.rule_id == flag_rule_id(question.flag_name)
        assert question.target == f"flag:{question.flag_name}"


def test_flag_questions_are_critical():
    for question in build_flag_questions(_module()):
        assert question.tier == "CRITICAL"


def test_flag_questions_have_unique_nonce():
    questions = build_flag_questions(_module())
    nonces = [q.nonce for q in questions]
    assert len(nonces) == len(set(nonces))
    assert all(len(n) == 32 for n in nonces)


def test_flag_questions_carry_flag_fields():
    for question in build_flag_questions(_module()):
        data = question.to_dict()
        assert data["flag_name"] in FLAG_META
        assert isinstance(data["flag_known"], bool)


# --- 1.3 inferred flags show value ---------------------------------------


def test_inferred_flag_shows_suggested_value():
    module = _module()
    module.flags.set("has_currency", True, source="inferred")

    question = build_flag_question(module, "has_currency")

    assert question.flag_known is True
    assert question.flag_current is True
    assert "Có" in question.question
    assert question.recommended_option.startswith("(Recommended) Đồng ý")


def test_inferred_flag_offers_flip():
    module = _module()
    module.flags.set("has_currency", True, source="inferred")

    question = build_flag_question(module, "has_currency")
    assert question.alternative_options == ["Sửa thành Không"]


def test_inferred_flag_false_shows_no():
    module = _module()
    module.flags.set("is_multi_tenant", False, source="inferred")

    question = build_flag_question(module, "is_multi_tenant")
    assert question.flag_known is True
    assert "Không" in question.question
    assert "Sửa thành Có" in question.alternative_options


# --- 1.4 user-only flags do not claim a value ----------------------------


@pytest.mark.parametrize("flag_name", ["has_quota", "has_dependencies", "has_unique_field"])
def test_user_only_flag_has_no_suggested_value(flag_name):
    question = build_flag_question(_module(), flag_name)

    assert question.flag_known is False
    assert "đã suy đoán" not in question.question
    assert "Đồng ý" not in question.recommended_option
    assert "Có" in question.alternative_options


# --- 1.5 integrated into match_spec -------------------------------------


def test_match_spec_includes_flag_questions():
    report = match_spec(_spec(2), load_rules())
    flag_questions = [q for q in report.questions if q.rule_id.startswith("FLAG:")]

    assert len(flag_questions) == 12


def test_flag_questions_come_first():
    report = match_spec(_spec(1), load_rules())
    assert report.questions[0].rule_id.startswith("FLAG:")


def test_flag_questions_do_not_affect_coverage():
    report = match_spec(_spec(1), load_rules())
    assert report.coverage_ok is True
    assert report.matched_count + report.skipped_count == 150


def test_flag_questions_do_not_enter_matched_rules():
    report = match_spec(_spec(1), load_rules())
    assert not any(rid.startswith("FLAG:") for rid in report.matched_rule_ids)


# --- id stability -------------------------------------------------------


def test_flag_question_id_stable_across_runs():
    first = [q.id for q in build_flag_questions(_module())]
    second = [q.id for q in build_flag_questions(_module())]
    assert first == second


def test_flag_question_nonce_differs_across_runs():
    first = [q.nonce for q in build_flag_questions(_module())]
    second = [q.nonce for q in build_flag_questions(_module())]
    assert set(first) & set(second) == set()


# --- parse helpers ------------------------------------------------------


def test_parse_flag_rule_id():
    assert parse_flag_rule_id("FLAG:has_quota") == "has_quota"
    assert parse_flag_rule_id("H-DATA-STR-01") is None
    assert parse_flag_rule_id("FLAG:khong_ton_tai") is None


def test_parse_flag_target():
    assert parse_flag_target("flag:has_currency") == "has_currency"
    assert parse_flag_target("param:quantity") is None
    assert parse_flag_target(None) is None


# --- coerce_flag_value ---------------------------------------------------


@pytest.mark.parametrize("raw", ["Có", "có", "yes", "true", "1", 1, True])
def test_coerce_positive(raw):
    assert coerce_flag_value(raw) is True


@pytest.mark.parametrize("raw", ["Không", "không", "no", "false", "0", 0, False])
def test_coerce_negative(raw):
    assert coerce_flag_value(raw) is False


def test_coerce_agree_keeps_current_true():
    assert coerce_flag_value("Đồng ý — giữ giá trị Có", current=True) is True


def test_coerce_agree_keeps_current_false():
    assert coerce_flag_value("Đồng ý — giữ giá trị Không", current=False) is False


def test_coerce_agree_without_current_is_none():
    assert coerce_flag_value("Đồng ý") is None


def test_coerce_flip_to_no():
    assert coerce_flag_value("Sửa thành Không", current=True) is False


def test_coerce_flip_to_yes():
    assert coerce_flag_value("Sửa thành Có", current=False) is True


@pytest.mark.parametrize("raw", ["tuỳ", "", None, "không rõ"])
def test_coerce_unknown_is_none(raw):
    assert coerce_flag_value(raw) is None
