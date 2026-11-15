"""Test cho utd.audit: 9 cổng, mỗi cổng 1 pass + 1 fail."""

import json

import pytest

from utd.audit.gates import (
    GATE_IDS,
    GATE_NAMES,
    audit_ssot,
    format_markdown,
    gate_ep,
    gate_ep_proper,
    gate_anti_slop,
    gate_bva,
    gate_dual_path,
    gate_http_status,
    gate_no_slop_property,
    gate_security,
    gate_source_rule_coverage,
)


def _method(params=None, rules=None, responses=None, cases=None, auth="jwt") -> dict:
    return {
        "name": "createOrder",
        "api": {
            "http_method": "POST",
            "path": "/api/orders",
            "auth": auth,
            "request": params or [],
            "responses": responses or [],
            "rules": rules or [],
        },
        "test_cases": cases or [],
    }


def _case(case_type="Normal", input_text="quantity=5", expected=None, refs=None,
          note="", case_id=None) -> dict:
    data = {
        "input": input_text,
        "expected": expected or {"return": "HTTP 201", "exception": "N/A", "log": "ok"},
        "type": case_type,
        "rule_refs": refs or [],
        "note": note,
    }
    if case_id:
        data["id"] = case_id
    return data


# --- G1 EP -----------------------------------------------------------------


def test_g1_fails_when_required_param_has_no_abnormal_case():
    params = [{"name": "quantity", "required": True, "constraints": {"min": 1, "max": 100}}]
    method = _method(params=params, cases=[_case(input_text="quantity=5")])

    result = gate_ep("sheet", method)
    assert result.passed is False
    assert any("quantity" in i.message for i in result.issues)


def test_g1_passes_with_absent_abnormal_case():
    params = [{"name": "quantity", "required": True}]
    method = _method(params=params, cases=[
        _case("Abnormal", "productId=X", note="missing required quantity"),
    ])

    result = gate_ep("sheet", method)
    assert result.passed is True


# --- G2 BVA ----------------------------------------------------------------


def test_g2_fails_without_min_minus_max_plus():
    params = [{"name": "quantity", "required": True, "constraints": {"min": 1, "max": 100}}]
    method = _method(params=params, cases=[_case("Normal", "quantity=50")])

    result = gate_bva("sheet", method)
    assert result.passed is False
    assert len(result.issues) == 2


def test_g2_passes_with_both_edges():
    params = [{"name": "quantity", "required": True, "constraints": {"min": 1, "max": 100}}]
    method = _method(params=params, cases=[
        _case("Abnormal", "quantity=0"),
        _case("Abnormal", "quantity=101"),
    ])

    result = gate_bva("sheet", method)
    assert result.passed is True


def test_g2_skips_params_without_bounds():
    params = [{"name": "note", "required": False}]
    method = _method(params=params, cases=[])

    result = gate_bva("sheet", method)
    assert result.passed is True


# --- G3 DUAL-PATH ---------------------------------------------------------


def test_g3_fails_when_rule_has_no_valid_case():
    rules = [{"id": "BR-01", "text": "a"}]
    method = _method(rules=rules, cases=[_case("Abnormal", refs=["BR-01"])])

    result = gate_dual_path("sheet", method)
    assert result.passed is False
    assert any("hợp lệ" in i.message for i in result.issues)


def test_g3_fails_when_rule_has_no_invalid_case():
    rules = [{"id": "BR-01", "text": "a"}]
    method = _method(rules=rules, cases=[_case("Normal", refs=["BR-01"])])

    result = gate_dual_path("sheet", method)
    assert result.passed is False
    assert any("vi phạm" in i.message for i in result.issues)


def test_g3_passes_with_both_paths():
    rules = [{"id": "BR-01", "text": "a"}]
    method = _method(rules=rules, cases=[
        _case("Normal", refs=["BR-01"]),
        _case("Abnormal", refs=["BR-01"]),
    ])

    assert gate_dual_path("sheet", method).passed is True


# --- G4 HTTP-STATUS -------------------------------------------------------


def test_g4_fails_when_status_uncovered():
    responses = [{"status": 400, "error_code": "E"}]
    method = _method(responses=responses, cases=[_case(expected={"return": "HTTP 201"})])

    result = gate_http_status("sheet", method)
    assert result.passed is False
    assert any("400" in i.message for i in result.issues)


def test_g4_passes_when_all_statuses_covered():
    responses = [{"status": 201}, {"status": 400}]
    method = _method(responses=responses, cases=[
        _case(expected={"return": "HTTP 201"}),
        _case("Abnormal", expected={"return": "HTTP 400; body"}),
    ])

    assert gate_http_status("sheet", method).passed is True


# --- G5 ANTI-SLOP ---------------------------------------------------------


def test_g5_fails_on_blacklisted_value():
    method = _method(cases=[_case(input_text="email=test@example.com")])
    result = gate_anti_slop("sheet", method)

    assert result.passed is False
    assert "test@example.com" in result.issues[0].message


def test_g5_passes_with_real_data():
    method = _method(cases=[_case(input_text="email=nguyenvana@congty.vn")])
    assert gate_anti_slop("sheet", method).passed is True


# --- G6 SECURITY ----------------------------------------------------------


def test_g6_fails_when_auth_without_401_case():
    method = _method(auth="jwt", cases=[_case(expected={"return": "HTTP 201"})])
    result = gate_security("sheet", method)

    assert result.passed is False


def test_g6_passes_with_401_case():
    method = _method(auth="jwt", cases=[_case("Abnormal", expected={"return": "HTTP 401"})])
    assert gate_security("sheet", method).passed is True


def test_g6_ignores_public_endpoint():
    method = _method(auth="none", cases=[_case()])
    assert gate_security("sheet", method).passed is True


# --- G8 EP-PROPER (mới) ---------------------------------------------------


def test_g8_fails_when_normal_case_is_missing_param():
    """Lỗ hổng bản cũ: case Normal thiếu param được tính là đã phủ."""
    params = [{"name": "id", "required": True}]
    method = _method(params=params, cases=[_case("Normal", "other=x")])

    result = gate_ep_proper("sheet", method)
    assert result.passed is False
    assert any("id" in i.message for i in result.issues)


def test_g8_passes_when_missing_case_is_abnormal():
    params = [{"name": "id", "required": True}]
    method = _method(params=params, cases=[_case("Abnormal", "other=x", note="missing id")])

    assert gate_ep_proper("sheet", method).passed is True


def test_g8_ignores_non_required_params():
    params = [{"name": "note", "required": False}]
    method = _method(params=params, cases=[_case("Normal", "other=x")])

    assert gate_ep_proper("sheet", method).passed is True


# --- G9 NO-SLOP-PROPERTY (mới) -------------------------------------------


def test_g9_detects_fake_id_p001():
    method = _method(cases=[_case(input_text="productId=P001")])
    result = gate_no_slop_property("sheet", method)

    assert result.passed is False
    assert any("P001" in i.message for i in result.issues)


def test_g9_detects_id_equals_one():
    method = _method(cases=[_case(input_text="orderId=1")])
    result = gate_no_slop_property("sheet", method)

    assert result.passed is False


def test_g9_detects_repeated_characters():
    method = _method(cases=[_case(input_text="phone=1111111111")])
    result = gate_no_slop_property("sheet", method)

    assert result.passed is False


def test_g9_allows_vietnamese_name():
    method = _method(cases=[_case(input_text="name=Trần Lê Bảo Ánh")])
    assert gate_no_slop_property("sheet", method).passed is True


def test_g9_allows_real_quantity():
    method = _method(cases=[_case(input_text="quantity=50")])
    assert gate_no_slop_property("sheet", method).passed is True


def test_g9_detects_placeholder():
    method = _method(cases=[_case(input_text="field=<quantity>")])
    result = gate_no_slop_property("sheet", method)

    assert result.passed is False


# --- G7 SOURCE-RULE-COVERAGE ---------------------------------------------


def test_g7_fails_with_unaccounted_rules():
    coverage = {"total_rules": 150, "matched": 92, "skipped": 51, "unaccounted": 7}
    result = gate_source_rule_coverage("(global)", {"name": "all"}, coverage)

    assert result.passed is False
    assert any("7" in i.message for i in result.issues)


def test_g7_fails_when_sum_mismatch():
    coverage = {"total_rules": 150, "matched": 90, "skipped": 50, "unaccounted": 0}
    result = gate_source_rule_coverage("(global)", {"name": "all"}, coverage)

    assert result.passed is False


def test_g7_passes_when_everything_accounted():
    coverage = {"total_rules": 150, "matched": 92, "skipped": 58, "unaccounted": 0}
    assert gate_source_rule_coverage("(global)", {"name": "all"}, coverage).passed


def test_g7_skips_without_coverage():
    assert gate_source_rule_coverage("(global)", {}, None).passed is True


# --- toàn bộ --------------------------------------------------------------


def test_audit_reports_all_nine_gates():
    ssot = {"modules": [{"sheet_name": "S", "methods": [_method()]}]}
    report = audit_ssot(ssot)

    assert len(report.results) == 9
    assert set(r.gate for r in report.results) == set(GATE_IDS)


def test_audit_passes_with_clean_ssot():
    params = [{"name": "quantity", "required": True, "constraints": {"min": 1, "max": 100}}]
    rules = [{"id": "BR-01", "text": "a"}]
    responses = [{"status": 201}, {"status": 400}, {"status": 401}]
    cases = [
        _case("Normal", "quantity=50", expected={"return": "HTTP 201"}, refs=["BR-01"]),
        _case("Abnormal", "quantity=0", expected={"return": "HTTP 400"}, refs=["BR-01"]),
        _case("Abnormal", "quantity=101", expected={"return": "HTTP 400"}),
        _case("Abnormal", "quantity=5", expected={"return": "HTTP 401"}),
        _case("Abnormal", "productId=", expected={"return": "HTTP 400"},
              note="missing quantity"),
    ]
    ssot = {
        "modules": [{"sheet_name": "S", "methods": [
            _method(params=params, rules=rules, responses=responses, cases=cases)
        ]}],
        "uncovered_rules": [],
        "zero_normal_sheets": [],
    }
    coverage = {"total_rules": 150, "matched": 92, "skipped": 58, "unaccounted": 0}
    report = audit_ssot(ssot, coverage=coverage)

    assert report.passed is True, [
        (r.gate, [i.message for i in r.issues]) for r in report.results if not r.passed
    ]


def test_audit_fails_with_uncovered_rules_in_ssot():
    ssot = {
        "modules": [{"sheet_name": "S", "methods": [_method()]}],
        "uncovered_rules": ["S:BR-05"],
    }
    report = audit_ssot(ssot)

    assert report.passed is False
    g3 = report.by_gate("G3")
    assert any("BR-05" in i.message for i in g3.issues)


def test_audit_fails_on_legacy_example_fixture():
    """Fixture legacy phải bị từ chối — chứng minh cổng thực sự chặn."""
    from pathlib import Path

    root = Path(__file__).parent.parent
    legacy = root / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"
    data = json.loads(legacy.read_text(encoding="utf-8"))
    # chuyển sơ bộ sang hình dạng SSOT của v2
    modules = []
    for module in data.get("modules", []):
        methods = []
        for method in module.get("methods", []):
            methods.append({
                "name": method.get("name"),
                "api": method.get("api") or {},
                "test_cases": method.get("test_cases") or [],
            })
        modules.append({"sheet_name": module.get("sheet_name"), "methods": methods})

    report = audit_ssot({"modules": modules})
    assert report.passed is False
    assert report.total_issues > 0


def test_format_markdown_lists_each_failing_gate():
    ssot = {"modules": [{"sheet_name": "S", "methods": [
        _method(cases=[_case(input_text="productId=P001")])
    ]}]}
    report = audit_ssot(ssot)
    text = format_markdown(report)

    assert "# Audit Report" in text
    assert "| Cổng |" in text
    failing = [r for r in report.results if not r.passed]
    for result in failing:
        assert result.gate in text
        assert result.gate in GATE_NAMES


def test_format_markdown_reports_pass():
    params = [{"name": "quantity", "required": True, "constraints": {"min": 1, "max": 100}}]
    rules = [{"id": "BR-01", "text": "a"}]
    responses = [{"status": 201}, {"status": 400}, {"status": 401}]
    cases = [
        _case("Normal", "quantity=50", expected={"return": "HTTP 201"}, refs=["BR-01"]),
        _case("Abnormal", "quantity=0", expected={"return": "HTTP 400"}, refs=["BR-01"]),
        _case("Abnormal", "quantity=101", expected={"return": "HTTP 400"}),
        _case("Abnormal", "quantity=5", expected={"return": "HTTP 401"}),
        _case("Abnormal", "productId=", expected={"return": "HTTP 400"},
              note="missing quantity"),
    ]
    ssot = {"modules": [{"sheet_name": "S", "methods": [
        _method(params=params, rules=rules, responses=responses, cases=cases)
    ]}]}
    coverage = {"total_rules": 150, "matched": 92, "skipped": 58, "unaccounted": 0}
    text = format_markdown(audit_ssot(ssot, coverage=coverage))

    assert "PASSED" in text
