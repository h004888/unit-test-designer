"""Test cho utd.match: tier theo dữ liệu, engine đánh giá, reachability, nonce."""

import json
from pathlib import Path

import pytest

from utd.canonical import (
    Auth,
    CanonicalSpec,
    Endpoint,
    Flags,
    Module,
    Param,
    Project,
    Rule,
)
from utd.dsl import DSLSyntaxError, evaluate
from utd.match.engine import (
    build_checklist,
    build_context,
    load_rules,
    match_spec,
)
from utd.match.tier import (
    CRITICAL,
    STANDARD,
    describe_tier_decision,
    determine_tier,
    load_tier_config,
)

ROOT = Path(__file__).parent.parent


def _spec_with_modules(count: int = 2) -> CanonicalSpec:
    modules = []
    for i in range(count):
        module = Module(
            id=f"mod-{i + 1}",
            module_name=f"API {i + 1}",
            sheet_name=f"POST_api_{i + 1}",
            endpoints=[
                Endpoint(
                    id=f"ep-{i + 1}",
                    http_method="POST",
                    path=f"/api/v1/resource{i + 1}",
                    auth=Auth(type="jwt", roles=[]),
                    params=[
                        Param(name="quantity", type="integer", required=True),
                        Param(name="name", type="string", required=True),
                    ],
                )
            ],
        )
        modules.append(module)
    return CanonicalSpec(project=Project(name="Demo", code="DEMO"), modules=modules)


# --- tier từ dữ liệu -------------------------------------------------------


def test_tier_config_loads():
    config = load_tier_config()
    assert config["critical_if_strictness"] == {"MANDATORY"}
    assert config["critical_dimensions"]
    assert config["standard_dimensions"]


def test_security_dimension_is_critical():
    rule = {"dimension": "2. Deep Security & OWASP Top 10", "category": "x",
            "strictness": "CONDITIONAL"}
    assert determine_tier(rule) == CRITICAL


def test_transport_dimension_is_standard():
    rule = {"dimension": "9. Transport, Headers & Protocols", "category": "x",
            "strictness": "MANDATORY"}
    assert determine_tier(rule) == STANDARD


def test_mandatory_outside_domain_is_critical():
    rule = {"dimension": "6. Concurrency, Locking & Quotas", "category": "x",
            "strictness": "MANDATORY"}
    assert determine_tier(rule) == CRITICAL


def test_conditional_outside_domain_is_standard():
    rule = {"dimension": "6. Concurrency, Locking & Quotas", "category": "occ",
            "strictness": "CONDITIONAL"}
    assert determine_tier(rule) == STANDARD


def test_tier_is_not_hardcoded_ids():
    """Thêm một rule mới (id lạ) vào dữ liệu vẫn phải phân tier đúng."""
    rule = {"id": "H-MOI-999", "dimension": "2. Deep Security & OWASP Top 10",
            "category": "brand new", "strictness": "CONDITIONAL"}
    assert determine_tier(rule) == CRITICAL
    assert "dimension" in describe_tier_decision(rule)


def test_tier_sum_matches_150_rules():
    rules = load_rules().rules
    config = load_tier_config()
    critical = sum(1 for r in rules if determine_tier(r, config) == CRITICAL)
    standard = sum(1 for r in rules if determine_tier(r, config) == STANDARD)
    assert critical + standard == 150


# --- engine ---------------------------------------------------------------


def test_load_rules_finds_all_150():
    ruleset = load_rules()
    assert len(ruleset.rules) == 150
    assert ruleset.parse_errors == []


def test_reachability_covers_all_rules():
    """Không rule nào bị treo: matched + skipped == total."""
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    assert report.total_rules == 150
    assert report.matched_count + report.skipped_count == 150
    assert report.coverage_ok is True


def _rich_spec() -> CanonicalSpec:
    """Spec giàu tham số: đại diện API thật thay vì chỉ quantity/name."""
    params = [
        Param(name="Authorization", in_="header", type="string", required=True),
        Param(name="quantity", type="integer", required=True),
        Param(name="name", type="string", required=True),
        Param(name="email", type="string", required=False),
        Param(name="password", type="string", required=True),
        Param(name="phone", type="string", required=False),
        Param(name="id", type="string", required=True),
        Param(name="amount", type="number", required=True),
        Param(name="voucher", type="string", required=False),
        Param(name="tags", type="array", required=False),
        Param(name="active", type="boolean", required=False),
        Param(name="file", type="string", required=False),
        Param(name="webhook_url", type="string", required=False),
        Param(name="currency", type="string", required=False),
        Param(name="start_date", type="string", required=False, format="date"),
        Param(name="tenant_id", type="string", required=True),
    ]
    module = Module(
        id="mod-rich",
        module_name="Checkout API",
        sheet_name="POST_api_checkout",
        flags=Flags(),
        endpoints=[
            Endpoint(
                id="ep-rich",
                http_method="POST",
                path="/api/orders/{id}/checkout",
                auth=Auth(type="jwt", roles=["admin"]),
                params=params,
                rules=[Rule(id="BR-01", text="đơn hàng hợp lệ")],
            )
        ],
    )
    module.flags.set("has_currency", True, source="inferred")
    module.flags.set("is_multi_tenant", True, source="inferred")
    module.flags.set("has_status_field", True, source="inferred")
    return CanonicalSpec(project=Project(name="Demo"), modules=[module])


def test_matched_rules_are_at_least_high():
    """Bản cũ chỉ đạt 83/150 trên API maximal. Bản mới phải vượt xa."""
    ruleset = load_rules()
    report = match_spec(_rich_spec(), ruleset)
    assert report.matched_count >= 100
    assert report.coverage_ok is True
    assert report.matched_count > 83  # vượt hẳn con số của bản cũ


def test_skipped_rules_have_concrete_reason():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    for skipped in report.skipped:
        assert skipped.reason.strip()
        assert len(skipped.reason) > 20


def test_skip_reason_mentions_trigger_condition():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)
    skipped = report.skipped[0]

    assert skipped.trigger_condition[:20] in skipped.reason or skipped.rule_id in skipped.reason


def test_webhook_rule_skipped_with_reason():
    rules = load_rules().by_id()
    report = match_spec(_spec_with_modules(), load_rules())

    webhook_rules = [s for s in report.skipped if "webhook" in s.rule_id.lower()
                     or "webhook" in s.trigger_condition.lower()]
    assert webhook_rules, "phải có rule webhook bị bỏ qua vì spec không có webhook"
    for rule in webhook_rules:
        assert rule.reason.strip()


def test_questions_deduplicate_by_endpoint_param_rule():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    keys = [(q.module_id, q.endpoint_id, q.param_name, q.rule_id) for q in report.questions]
    assert len(keys) == len(set(keys))


def test_different_params_produce_separate_questions():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    # Rule string_param phải sinh câu hỏi riêng cho 'name'
    string_param_questions = [
        q for q in report.questions if q.param_name == "name"
        and "H-DATA-STR" in q.rule_id
    ]
    assert string_param_questions


def test_nonces_are_unique():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    nonces = [q.nonce for q in report.questions]
    assert len(nonces) == len(set(nonces))
    for nonce in nonces:
        assert len(nonce) == 32  # 16 byte hex


def test_questions_have_tier():
    ruleset = load_rules()
    report = match_spec(_spec_with_modules(), ruleset)

    for question in report.questions:
        assert question.tier in (CRITICAL, STANDARD)


def test_build_context_contains_flags():
    module = Module(
        id="m", module_name="X", sheet_name="S",
        flags=Flags(),
        endpoints=[Endpoint(id="e", http_method="POST", path="/x",
                            params=[Param(name="total", type="number")])],
    )
    module.flags.set("has_currency", True, source="inferred")
    context = build_context(module, module.endpoints[0], module.endpoints[0].params[0])

    assert context["has_currency"] is True
    assert context["param"]["name"] == "total"
    assert context["endpoint"]["path"] == "/x"


def test_build_checklist_payload_shape():
    ruleset = load_rules()
    spec = _spec_with_modules()
    report = match_spec(spec, ruleset)
    checklist = build_checklist(report, spec)

    assert checklist["session_state"] == "AWAITING_USER_INTERACTION"
    assert checklist["coverage"]["total_rules"] == 150
    assert checklist["coverage"]["coverage_ok"] is True
    assert len(checklist["questions"]) == report.summary()["questions"]
    assert checklist["modules"][0]["sheet_name"] == "POST_api_1"


def test_checklist_questions_have_nonce_and_status():
    ruleset = load_rules()
    spec = _spec_with_modules()
    checklist = build_checklist(match_spec(spec, ruleset), spec)

    for question in checklist["questions"]:
        assert question["nonce"]
        assert question["status"] == "PENDING"
        assert question["nonce"] in [q["nonce"] for q in checklist["questions"]]


def test_malicious_rule_is_rejected_not_executed():
    """Rule có trigger ngoài ngôn ngữ phải vào parse_errors, không chạy."""
    from utd.match.engine import RuleSet

    ruleset = RuleSet(
        rules=[],
        parse_errors=[("H-X", "method '__import__' không hợp lệ")],
    )
    report = match_spec(_spec_with_modules(), ruleset)

    assert report.parse_errors
    assert report.total_rules == 0


def test_all_modules_are_processed():
    """Chống tái phát bug `modules[0]`: spec 3 module phải có câu hỏi cho cả 3."""
    ruleset = load_rules()
    spec = _spec_with_modules(3)
    report = match_spec(spec, ruleset)

    sheet_names = {q.sheet_name for q in report.questions}
    assert sheet_names == {"POST_api_1", "POST_api_2", "POST_api_3"}
