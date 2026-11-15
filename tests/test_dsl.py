"""Test cho utd.dsl: ngôn ngữ đóng, an toàn, đánh giá đúng.

Đây là test chống tái phát quan trọng nhất: bản cũ bỏ qua `trigger_condition`
nên 51/150 rule không bao giờ kích hoạt.
"""

import json
from pathlib import Path

import pytest

from utd.dsl import (
    DSLSyntaxError,
    evaluate,
    validate_syntax,
    _normalise,
)

ROOT = Path(__file__).parent.parent
RULES = ROOT / "utd" / "_data" / "rules"


def _all_rules() -> list[dict]:
    rules = []
    for path in sorted(RULES.glob("*.json")):
        rules.extend(json.loads(path.read_text(encoding="utf-8"))["rules"])
    return rules


def _context(method="POST", path="/api/orders", auth="Bearer JWT", roles=None,
             param=None, **extra):
    ctx = {
        "method": method,
        "endpoint": {"auth": auth, "path": path, "roles": roles or []},
        "param": param or {"name": "quantity", "type": "integer", "required": True,
                           "default": None, "enum": None, "format": None},
    }
    ctx.update(extra)
    return ctx


# --- toàn bộ 150 rule trong kho ---------------------------------------------


def test_all_trigger_conditions_parse():
    """150/150 biểu thức trong `rules/` phải nằm trong ngôn ngữ DSL."""
    rules = _all_rules()
    assert len(rules) == 150

    bad = []
    for rule in rules:
        try:
            validate_syntax(rule["trigger_condition"])
        except DSLSyntaxError as exc:
            bad.append((rule["id"], rule["trigger_condition"], str(exc)))

    assert bad == [], f"{len(bad)} biểu thức ngoài ngôn ngữ: {bad[:3]}"


def test_all_trigger_conditions_evaluate_without_crashing():
    """Mọi biểu thức phải đánh giá được trên một ngữ cảnh bất kỳ."""
    rules = _all_rules()
    context = _context()

    for rule in rules:
        result = evaluate(rule["trigger_condition"], context)
        assert isinstance(result.value, bool), rule["id"]


# --- ngôn ngữ đóng: từ chối mã độc -----------------------------------------


def test_rejects_import_call():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("__import__('os').system('x')")


def test_rejects_attribute_dunder():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("param.__class__")


def test_rejects_lambda():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("(lambda: 1)()")


def test_rejects_list_comprehension():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("[x for x in [1]]")


def test_rejects_unlisted_method():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("param.name.replace('a','b')")


def test_rejects_assignment_expression():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("(x := 1)")


def test_rejects_empty_expression():
    with pytest.raises(DSLSyntaxError):
        validate_syntax("   ")


def test_rejects_non_string():
    with pytest.raises(DSLSyntaxError):
        validate_syntax(123)  # type: ignore[arg-type]


def test_malicious_expression_never_executes(tmp_path):
    marker = tmp_path / "bi_xoa.txt"
    expression = f"__import__('pathlib').Path(r'{marker}').write_text('x') or true"
    with pytest.raises(DSLSyntaxError):
        evaluate(expression, {})
    assert not marker.exists()


# --- đánh giá đúng ---------------------------------------------------------


@pytest.mark.parametrize(
    "expression,context_kwargs,expected",
    [
        ("true", {}, True),
        ("false", {}, False),
        ("method == 'POST'", {"method": "POST"}, True),
        ("method == 'POST'", {"method": "GET"}, False),
        ("method in ['PUT', 'PATCH']", {"method": "PATCH"}, True),
        ("method in ['PUT', 'PATCH']", {"method": "POST"}, False),
        ("method in ['POST', 'PUT']", {"method": "DELETE"}, False),
        ("method != 'GET'", {"method": "POST"}, True),
    ],
)
def test_method_expressions(expression, context_kwargs, expected):
    assert evaluate(expression, _context(**context_kwargs)).value is expected


@pytest.mark.parametrize(
    "param_type,expression,expected",
    [
        ("string", "param.type == 'string'", True),
        ("integer", "param.type == 'string'", False),
        ("integer", "param.type in ['integer', 'number']", True),
        ("array", "param.type == 'array'", True),
        ("boolean", "param.type == 'boolean'", True),
    ],
)
def test_param_type_expressions(param_type, expression, expected):
    param = {"name": "x", "type": param_type, "required": True}
    assert evaluate(expression, _context(param=param)).value is expected


@pytest.mark.parametrize(
    "param_name,expression,expected",
    [
        ("total_amount", "param.name.includes('price') || param.name.includes('amount')", True),
        ("unit_price", "param.name.includes('price') || param.name.includes('total')", True),
        ("voucher_code", "param.name.includes('voucher') || param.name.includes('coupon')", True),
        ("email", "param.name.includes('voucher') || param.name.includes('coupon')", False),
        ("file_path", "param.name.includes('path') || param.name.includes('file')", True),
    ],
)
def test_param_name_expressions(param_name, expression, expected):
    param = {"name": param_name, "type": "string", "required": False}
    assert evaluate(expression, _context(param=param)).value is expected


@pytest.mark.parametrize(
    "auth,expression,expected",
    [
        ("Bearer JWT", "endpoint.auth.includes('jwt')", True),
        ("Bearer JWT", "endpoint.auth.includes('oauth')", False),
        ("OAuth2", "endpoint.auth.includes('oauth')", True),
        ("public", "endpoint.auth != 'public'", False),
        ("none", "endpoint.auth == 'public'", False),
    ],
)
def test_auth_expressions(auth, expression, expected):
    assert evaluate(expression, _context(auth=auth)).value is expected


@pytest.mark.parametrize(
    "path,expression,expected",
    [
        ("/api/orders", "endpoint.path.includes('order')", True),
        ("/api/webhooks/stripe", "endpoint.path.includes('webhook')", True),
        ("/api/orders/{id}", "endpoint.path.includes('{id}')", True),
        ("/api/users/{userid}", "endpoint.path.includes('{id}')", False),
        ("/api/export/report", "endpoint.path.includes('export') || endpoint.path.includes('report')", True),
    ],
)
def test_path_expressions(path, expression, expected):
    assert evaluate(expression, _context(path=path)).value is expected


def test_required_and_default_checks():
    param = {"name": "x", "type": "string", "required": True, "default": None}
    assert evaluate("param.required == true", _context(param=param)).value is True
    assert evaluate("param.default != null", _context(param=param)).value is False

    param2 = {"name": "y", "type": "string", "required": False, "default": "x"}
    assert evaluate("param.required == false", _context(param=param2)).value is True
    assert evaluate("param.default != null", _context(param=param2)).value is True


def test_enum_and_format_checks():
    param = {"name": "v", "type": "string", "enum": ["A", "B"]}
    assert evaluate("param.enum != null", _context(param=param)).value is True

    param_none = {"name": "v", "type": "string", "enum": None}
    assert evaluate("param.enum != null", _context(param=param_none)).value is False

    date_param = {"name": "d", "type": "string", "format": "date"}
    assert evaluate("param.format in ['date', 'date-time']", _context(param=date_param)).value is True


def test_boolean_flag_context():
    assert evaluate("has_currency == true", _context(has_currency=True)).value is True
    assert evaluate("has_currency == true", _context(has_currency=False)).value is False
    assert evaluate("is_multi_tenant == true", _context(is_multi_tenant=True)).value is True


# --- ngữ cảnh thiếu trường ------------------------------------------------


def test_missing_field_returns_false_with_warning():
    result = evaluate("foo.bar == 1", _context())
    assert result.value is False
    assert result.warnings
    assert "foo" in result.warnings[0] or "foo.bar" in result.warnings[0]


def test_missing_field_does_not_raise():
    # đánh giá trên ngữ cảnh rỗng không được ném
    assert evaluate("endpoint.auth.includes('jwt')", {}).value is False


# --- so sánh thứ tự (BVA dùng sau này) -------------------------------------


def test_ordered_comparisons():
    assert evaluate("param.constraints.min >= 1", {"param": {"constraints": {"min": 5}}}).value is True
    assert evaluate("param.constraints.min >= 1", {"param": {"constraints": {"min": 0}}}).value is False


def test_chained_comparison():
    ctx = {"param": {"constraints": {"min": 1, "max": 100}}}
    assert evaluate("param.constraints.min <= 10 <= param.constraints.max", ctx).value is True


# --- chuẩn hoá cú pháp JS ------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("a || b", "a  or  b"),
        ("a && b", "a  and  b"),
        ("!a", " not a"),
        ("a != b", "a != b"),
    ],
)
def test_normalise_js_operators(raw, expected):
    assert _normalise(raw) == expected


def test_normalise_keeps_string_literal_content():
    assert _normalise("x.includes('a||b')") == "x.includes('a||b')"
