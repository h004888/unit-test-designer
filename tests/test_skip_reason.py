"""Test: skipped_reason trung thực về cờ chưa xác nhận."""

import pytest

from utd.canonical import CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.match.engine import (
    _flag_dependencies,
    _unconfirmed_flags,
    load_rules,
    match_spec,
)


def _spec(flag_setups=None) -> CanonicalSpec:
    module = Module(
        id="m", module_name="X", sheet_name="S", flags=Flags(),
        endpoints=[Endpoint(id="e", http_method="POST", path="/api/x",
                            params=[Param(name="quantity", type="integer", required=True)])],
    )
    for name, value, source in (flag_setups or []):
        module.flags.set(name, value, source=source)
    return CanonicalSpec(project=Project(name="Demo"), modules=[module])


def _rule(rule_id: str) -> dict:
    rules = load_rules().by_id()
    return rules[rule_id]


# --- _flag_dependencies --------------------------------------------------


def test_flag_dependencies_detects_single_flag():
    assert _flag_dependencies({"trigger_condition": "has_quota == true"}) == ["has_quota"]


def test_flag_dependencies_detects_multiple():
    deps = _flag_dependencies({"trigger_condition": "has_quota && has_currency"})
    assert deps == ["has_quota", "has_currency"]


def test_flag_dependencies_empty_when_no_flag():
    assert _flag_dependencies({"trigger_condition": "method == 'POST'"}) == []


def test_flag_dependencies_order_follows_condition():
    deps = _flag_dependencies({"trigger_condition": "has_currency && has_quota"})
    assert deps == ["has_currency", "has_quota"]


# --- _unconfirmed_flags --------------------------------------------------


def test_unconfirmed_when_default():
    rule = {"trigger_condition": "has_unique_field == true"}
    assert _unconfirmed_flags(rule, _spec()) == ["has_unique_field"]


def test_confirmed_is_not_unconfirmed():
    rule = {"trigger_condition": "has_unique_field == true"}
    spec = _spec([("has_unique_field", False, "user")])
    assert _unconfirmed_flags(rule, spec) == []


def test_inferred_counts_as_confirmed_source():
    """Nguồn `inferred` không phải `default` -> không còn bị coi là chưa xác nhận."""
    rule = {"trigger_condition": "has_currency == true"}
    spec = _spec([("has_currency", True, "inferred")])
    assert _unconfirmed_flags(rule, spec) == []


def test_rule_without_flag_dependency_is_empty():
    rule = {"trigger_condition": "method == 'DELETE'"}
    assert _unconfirmed_flags(rule, _spec()) == []


# --- integrated into match_spec -----------------------------------------


def test_skip_reason_mentions_unconfirmed_flag():
    report = match_spec(_spec(), load_rules())
    skipped = {s.rule_id: s for s in report.skipped}

    entry = skipped.get("H-STATE-UNIQUE-01")
    assert entry is not None
    assert "has_unique_field" in entry.reason
    assert "chưa được xác nhận" in entry.reason
    assert "FLAG:has_unique_field" in entry.reason


def test_skip_reason_changes_after_flag_confirmed():
    report_default = match_spec(_spec(), load_rules())
    default_entry = {s.rule_id: s for s in report_default.skipped}["H-STATE-UNIQUE-01"]

    report_confirmed = match_spec(_spec([("has_unique_field", False, "user")]), load_rules())
    confirmed_skipped = {s.rule_id: s for s in report_confirmed.skipped}
    confirmed_entry = confirmed_skipped.get("H-STATE-UNIQUE-01")

    assert "chưa được xác nhận" in default_entry.reason
    # Khi cờ đã xác nhận false, rule vẫn skip nhưng lý do không còn nhắc "chưa xác nhận"
    if confirmed_entry is not None:
        assert "chưa được xác nhận" not in confirmed_entry.reason


def test_quota_rules_skip_reason_mentions_has_quota():
    report = match_spec(_spec(), load_rules())
    for rule_id in ("H-STATE-STOCK-QUOTA-01", "H-CONC-RACE-01"):
        entry = next((s for s in report.skipped if s.rule_id == rule_id), None)
        if entry is None:
            continue
        assert "has_quota" in entry.reason
        assert "chưa được xác nhận" in entry.reason


def test_five_flag_rules_now_explain_themselves():
    """Năm rule phụ thuộc cờ user-only phải nêu đúng tên cờ, không nói chung chung."""
    report = match_spec(_spec(), load_rules())
    skipped = {s.rule_id: s for s in report.skipped}

    affected = {
        "H-STATE-STOCK-QUOTA-01": "has_quota",
        "H-CONC-RACE-01": "has_quota",
        "H-DIST-CIRCUIT-BREAKER-01": "has_dependencies",
        "H-DIST-TIMEOUT-FALLBACK-01": "has_dependencies",
        "H-STATE-UNIQUE-01": "has_unique_field",
    }
    for rule_id, flag in affected.items():
        entry = skipped.get(rule_id)
        assert entry is not None, f"{rule_id} phải bị skip khi cờ còn default"
        assert flag in entry.reason, rule_id
        assert "chưa được xác nhận" in entry.reason, rule_id
