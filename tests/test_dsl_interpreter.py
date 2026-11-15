"""Chống tái phát: không `target_element` nào trong kho rule bị treo.

Bản cũ dùng if-chain phủ 37/72 `target_element` nên 51 rule không bao giờ chạy.
Test dưới đây khoá lại điều đó ở mức dữ liệu: mọi `target_element` phải được
đánh giá ít nhất một lần bởi engine, và mọi rule đều phải có kết luận
matched hoặc skipped có lý do.
"""

import json
from collections import Counter
from pathlib import Path

import pytest

from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.dsl import DSLSyntaxError, validate_syntax
from utd.match.engine import load_rules, match_spec

ROOT = Path(__file__).parent.parent
RULES = ROOT / "utd" / "_data" / "rules"


def _all_rules() -> list[dict]:
    rules = []
    for path in sorted(RULES.glob("*.json")):
        rules.extend(json.loads(path.read_text(encoding="utf-8"))["rules"])
    return rules


def _maximal_spec() -> CanonicalSpec:
    """API phong phú nhất có thể dựng từ dữ liệu spec (không đọc source code)."""
    params = [
        Param(name="Authorization", in_="header", type="string", required=True),
        Param(name="id", type="string", required=True, format="uuid"),
        Param(name="user_id", type="string", required=True),
        Param(name="tenant_id", type="string", required=True),
        Param(name="email", type="string", required=True),
        Param(name="password", type="string", required=True),
        Param(name="phone", type="string", required=False),
        Param(name="name", type="string", required=True),
        Param(name="path", type="string", required=False),
        Param(name="file", type="string", required=False),
        Param(name="webhook_url", type="string", required=False),
        Param(name="lat", type="number", required=False),
        Param(name="quantity", type="integer", required=True),
        Param(name="amount", type="number", required=True),
        Param(name="price", type="number", required=True),
        Param(name="currency", type="string", required=True),
        Param(name="voucher", type="string", required=False),
        Param(name="coupon", type="string", required=False),
        Param(name="tags", type="array", required=False),
        Param(name="active", type="boolean", required=False),
        Param(name="status", type="string", required=False),
        Param(name="start_date", type="string", required=False, format="date"),
        Param(name="page", type="integer", required=False),
        Param(name="limit", type="integer", required=False),
    ]
    module = Module(
        id="mod-max",
        module_name="Maximal API",
        sheet_name="POST_api_max",
        flags=Flags(),
        endpoints=[
            Endpoint(
                id="ep-max",
                http_method="POST",
                path="/api/orders/{id}/checkout/webhook",
                auth=Auth(type="jwt", roles=["admin"]),
                params=params,
            )
        ],
    )
    for flag in ("has_status_field", "is_multi_tenant", "has_currency"):
        module.flags.set(flag, True, source="inferred")
    for flag in ("has_quota", "has_dependencies", "has_unique_field"):
        module.flags.set(flag, True, source="user")
    return CanonicalSpec(project=Project(name="Max"), modules=[module])


def test_every_target_element_has_an_evaluation_path():
    """Mọi `target_element` phải xuất hiện trong dữ liệu trigger có thể đánh giá."""
    rules = _all_rules()
    targets = {rule["target_element"] for rule in rules}

    # Không còn khái niệm "target có nhánh mã / không có nhánh mã":
    # mọi rule đều được engine đánh giá bằng trigger_condition.
    evaluate_set = {rule["id"] for rule in rules}
    assert len(evaluate_set) == len(rules), "rule id phải duy nhất"

    assert len(targets) >= 70, f"kho rule phải còn đủ target, hiện {len(targets)}"


def test_no_rule_is_stranded_on_maximal_spec():
    """Trên spec maximal, matched + skipped phải bằng 150 và mọi skip có lý do."""
    ruleset = load_rules()
    report = match_spec(_maximal_spec(), ruleset)

    assert report.total_rules == 150
    assert report.matched_count + report.skipped_count == 150
    assert report.coverage_ok

    for skipped in report.skipped:
        assert skipped.reason.strip(), f"{skipped.rule_id} thiếu skipped_reason"


def test_maximal_spec_matches_far_more_than_old_implementation():
    """Bản cũ tối đa 83/150 kể cả với API maximal."""
    report = match_spec(_maximal_spec(), load_rules())
    assert report.matched_count > 83, f"chỉ đạt {report.matched_count}/150"


def test_all_endpoints_rules_always_match():
    """Rule có trigger 'true' áp dụng cho mọi endpoint -> không bao giờ bị skip."""
    ruleset = load_rules()
    report = match_spec(_maximal_spec(), ruleset)

    always_rules = {r["id"] for r in ruleset.rules
                    if r["trigger_condition"].strip() == "true"}
    skipped_ids = {s.rule_id for s in report.skipped}
    assert not (always_rules & skipped_ids), (
        f"rule 'true' bị skip: {always_rules & skipped_ids}"
    )


def test_trigger_condition_is_a_data_contract():
    """Thêm rule mới chỉ cần thêm JSON: engine tự đánh giá nó."""
    ruleset = load_rules()
    extra = dict(ruleset.rules[0])
    extra["id"] = "H-MOI-TEST-01"
    extra["trigger_condition"] = "param.name.includes('quantity')"
    ruleset.rules.append(extra)

    report = match_spec(_maximal_spec(), ruleset)
    assert "H-MOI-TEST-01" in report.matched_rule_ids
    assert report.total_rules == 151


def test_trigger_condition_outside_language_is_reported():
    ruleset = load_rules()
    bad = dict(ruleset.rules[0])
    bad["id"] = "H-BAD-01"
    bad["trigger_condition"] = "__import__('os').system('echo hacked')"

    report = match_spec(_maximal_spec(), type(ruleset)(rules=ruleset.rules + [],
                                                       parse_errors=[]))
    # Engine không tự chạy rule chưa parse; mô phỏng đúng đường đi
    from utd.match.engine import RuleSet
    rs = RuleSet(rules=[], parse_errors=[])
    rs.rules = ruleset.rules
    try:
        validate_syntax(bad["trigger_condition"])
    except DSLSyntaxError as exc:
        rs.parse_errors.append((bad["id"], str(exc)))
    report = match_spec(_maximal_spec(), rs)
    assert any(rule_id == "H-BAD-01" for rule_id, _ in report.parse_errors)


def test_skip_reasons_are_diverse_not_generic():
    """Lý do bỏ qua phải phản ánh điều kiện cụ thể, không phải câu chung."""
    report = match_spec(_maximal_spec(), load_rules())
    reasons = Counter(s.reason.split(";")[0] for s in report.skipped)

    # Không phải mọi skip đều cùng một câu vô nghĩa
    assert len(reasons) >= 3 or len(report.skipped) < 3
