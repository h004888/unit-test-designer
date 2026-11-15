"""Test cho utd.ingest: bốn adapter và phân loại lỗi exit 2/3."""

import json
from pathlib import Path

import pytest

from utd.canonical import (
    SCHEMA_VERSION,
    Endpoint,
    Module,
    Param,
    validate,
)
from utd.ingest import IngestError, convert
from utd.ingest.constraints import parse_constraints
from utd.ingest.drafts import missing_fields
from utd.ingest.flags import apply_inferred_flags

FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_yaml(name: str):
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((FIXTURES / name).read_text(encoding="utf-8"))


# --- adapter utd-v1 ---------------------------------------------------------


def test_legacy_spec_yields_two_modules():
    data = json.loads(LEGACY.read_text(encoding="utf-8"))
    spec = convert("utd-v1", data)

    assert len(spec.modules) == 2
    assert spec.endpoint_count() == 2
    assert {m.sheet_name for m in spec.modules} == {"POST_api_orders", "GET_api_orders_id"}


def test_legacy_constraints_are_structured():
    data = json.loads(LEGACY.read_text(encoding="utf-8"))
    spec = convert("utd-v1", data)

    first = spec.modules[0].endpoints[0]
    quantity = next(p for p in first.params if p.name == "quantity")
    assert quantity.constraints.min == 1
    assert quantity.constraints.max == 100

    auth_param = next(p for p in first.params if p.name == "Authorization")
    assert auth_param.constraints.is_empty()


def test_legacy_auth_detected_as_jwt():
    data = json.loads(LEGACY.read_text(encoding="utf-8"))
    spec = convert("utd-v1", data)

    assert spec.modules[0].endpoints[0].auth.type == "jwt"


def test_legacy_module_without_modules_key_raises():
    with pytest.raises(ValueError):
        convert("utd-v1", {"project": {}})


# --- adapter openapi --------------------------------------------------------


def test_openapi_yields_two_endpoints_with_constraints():
    spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))

    assert spec.endpoint_count() == 2
    sheets = {m.sheet_name for m in spec.modules}
    assert sheets == {"POST_api_orders", "GET_api_orders_id"}

    post = next(m for m in spec.modules if m.sheet_name == "POST_api_orders").endpoints[0]
    quantity = next(p for p in post.params if p.name == "quantity")
    assert quantity.constraints.min == 1
    assert quantity.constraints.max == 100

    product_id = next(p for p in post.params if p.name == "productId")
    assert product_id.constraints.min == 3
    assert product_id.constraints.max == 20

    voucher = next(p for p in post.params if p.name == "voucher")
    assert voucher.constraints.enum == ["SAVE10", "SAVE20"]


def test_openapi_params_have_correct_location():
    spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))

    post = next(m for m in spec.modules if m.sheet_name == "POST_api_orders").endpoints[0]
    assert all(p.in_ == "body" for p in post.params)

    get = next(m for m in spec.modules if m.sheet_name == "GET_api_orders_id").endpoints[0]
    assert get.params[0].in_ == "path"


def test_openapi_responses_carry_error_code():
    spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))

    post = next(m for m in spec.modules if m.sheet_name == "POST_api_orders").endpoints[0]
    statuses = {r.status for r in post.responses}
    assert {201, 400, 401} == statuses
    error = next(r for r in post.responses if r.status == 400)
    assert error.error_code == "VALIDATION_ERROR"


def test_openapi_auth_detected():
    spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))
    assert spec.modules[0].endpoints[0].auth.type == "jwt"


def test_openapi_wrong_version_raises():
    with pytest.raises(ValueError):
        convert("openapi", {"openapi": "2.0", "paths": {}})


def test_openapi_without_paths_raises():
    with pytest.raises(ValueError):
        convert("openapi", {"openapi": "3.0.3", "paths": {}})


# --- adapter swagger --------------------------------------------------------


def test_swagger_matches_openapi_shape():
    swagger_spec = convert("swagger", _load_json("swagger_minimal.json"))
    openapi_spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))

    assert {m.sheet_name for m in swagger_spec.modules} == {
        m.sheet_name for m in openapi_spec.modules
    }
    assert swagger_spec.endpoint_count() == openapi_spec.endpoint_count()

    sw_post = next(
        m for m in swagger_spec.modules if m.sheet_name == "POST_api_orders"
    ).endpoints[0]
    op_post = next(
        m for m in openapi_spec.modules if m.sheet_name == "POST_api_orders"
    ).endpoints[0]

    assert {p.name for p in sw_post.params} == {p.name for p in op_post.params}
    sw_quantity = next(p for p in sw_post.params if p.name == "quantity")
    assert (sw_quantity.constraints.min, sw_quantity.constraints.max) == (1, 100)


def test_swagger_inline_param_bounds():
    spec = convert("swagger", _load_json("swagger_minimal.json"))
    get = next(m for m in spec.modules if m.sheet_name == "GET_api_orders_id").endpoints[0]
    assert get.params[0].constraints.min == 1


def test_swagger_wrong_version_raises():
    with pytest.raises(ValueError):
        convert("swagger", {"swagger": "3.0", "paths": {}})


# --- adapter draft ----------------------------------------------------------


def test_draft_reports_missing_params():
    draft = {
        "modules": [
            {
                "module_name": "Order",
                "sheet_name": "POST_orders",
                "endpoints": [{"http_method": "POST", "path": "/orders"}],
            }
        ]
    }
    problems = missing_fields(draft)

    assert any("params" in p for p in problems)


def test_draft_missing_modules_reported():
    assert missing_fields({}) == ["modules: thiếu hoặc rỗng"]


def test_draft_complete_is_converted():
    draft = {
        "schema_version": SCHEMA_VERSION,
        "project": {"name": "Demo", "code": "DEMO"},
        "modules": [
            {
                "module_name": "Order",
                "sheet_name": "POST_orders",
                "endpoints": [
                    {
                        "http_method": "POST",
                        "path": "/orders",
                        "params": [
                            {
                                "name": "quantity",
                                "type": "integer",
                                "required": True,
                                "constraints": {"min": 1, "max": 10},
                            }
                        ],
                    }
                ],
            }
        ],
    }
    spec = convert("draft", draft)
    assert validate(spec).errors == []


def test_draft_incomplete_raises_value_error():
    with pytest.raises(ValueError):
        convert("draft", {"modules": [{"module_name": "X", "endpoints": []}]})


# --- phân loại lỗi ----------------------------------------------------------


def test_unknown_source_kind_exits_2():
    with pytest.raises(IngestError) as excinfo:
        convert("khong_ho_tro", {})
    assert excinfo.value.exit_code == 2


def test_structural_problem_is_value_error_not_ingest_error():
    # adapter ném ValueError -> CLI ánh xạ sang exit 2 cho nguồn có cấu trúc
    with pytest.raises(ValueError):
        convert("utd-v1", {"modules": []})


# --- cờ suy tự động --------------------------------------------------------


def test_currency_flag_inferred():
    spec = convert("openapi", _load_yaml("openapi_minimal.yaml"))
    # fixture không có tham số currency
    assert spec.modules[0].flags.get("has_currency") is False


def test_multi_tenant_flag_from_param_name():
    draft = {
        "schema_version": SCHEMA_VERSION,
        "modules": [
            {
                "module_name": "Tenant API",
                "sheet_name": "POST_tenant",
                "endpoints": [
                    {
                        "http_method": "POST",
                        "path": "/tenant/users",
                        "params": [{"name": "tenant_id", "type": "string", "required": True}],
                    }
                ],
            }
        ],
    }
    spec = convert("draft", draft)
    flags = spec.modules[0].flags
    assert flags.get("is_multi_tenant") is True
    assert flags.source("is_multi_tenant") == "inferred"


def test_status_field_inferred_from_param():
    module = Module(
        id="m",
        module_name="Order",
        sheet_name="POST_orders",
        endpoints=[
            Endpoint(
                id="e",
                http_method="POST",
                path="/orders",
                params=[Param(name="status", type="string", required=False)],
            )
        ],
    )
    apply_inferred_flags(module)
    assert module.flags.get("has_status_field") is True
    assert module.flags.source("has_status_field") == "inferred"


def test_user_only_flags_stay_default():
    module = Module(id="m", module_name="X", sheet_name="S", endpoints=[])
    apply_inferred_flags(module)
    for name in ("has_quota", "has_dependencies", "has_unique_field"):
        assert module.flags.source(name) == "default"


# --- parse constraints ------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected_min,expected_max",
    [
        ("1..100", 1, 100),
        ("1 <= quantity <= 100 và <= tồn kho", 1, 100),
        ("từ 1 đến 100", 1, 100),
        (">= 1 và <= 100", 1, 100),
        ("<= 100 và >= 1", 1, 100),
        ("tối đa 100 ký tự", None, 100),
        ("100 ký tự", None, 100),
    ],
)
def test_parse_constraints_bounds(raw, expected_min, expected_max):
    constraints = parse_constraints(raw)
    assert constraints.min == expected_min
    assert constraints.max == expected_max


def test_parse_constraints_ignores_bearer_token():
    assert parse_constraints("Bearer <JWT hợp lệ>").is_empty()


def test_parse_constraints_enum_brackets():
    assert parse_constraints("[A|B|C]").enum == ["A", "B", "C"]


def test_parse_constraints_dict_passthrough():
    constraints = parse_constraints({"min": 1, "max": 5})
    assert constraints.min == 1
    assert constraints.max == 5


def test_parse_constraints_swaps_reversed_range():
    assert parse_constraints("100..1").min == 1
    assert parse_constraints("100..1").max == 100
