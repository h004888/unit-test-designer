"""Test cho utd.canonical: dataclass, roundtrip, validator."""

import json

import pytest

from utd.canonical import (
    CanonicalSpec,
    Constraints,
    Flags,
    Module,
    Param,
    Endpoint,
    SCHEMA_VERSION,
    parse,
    validate,
)


def _minimal_spec() -> CanonicalSpec:
    return parse(
        {
            "schema_version": SCHEMA_VERSION,
            "project": {"name": "Demo", "code": "DEMO"},
            "auth_global": {"type": "jwt", "roles": ["user"]},
            "modules": [
                {
                    "id": "mod-001",
                    "module_name": "Order API",
                    "sheet_name": "POST_api_orders",
                    "kind": "http",
                    "endpoints": [
                        {
                            "id": "ep-001",
                            "http_method": "POST",
                            "path": "/api/orders",
                            "auth": {"type": "jwt", "roles": ["user"]},
                            "params": [
                                {
                                    "name": "quantity",
                                    "in": "body",
                                    "type": "integer",
                                    "required": True,
                                    "constraints": {"min": 1, "max": 100},
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_minimal_spec_is_valid():
    result = validate(_minimal_spec())
    assert result.errors == []
    assert result.ok is True


def test_roundtrip_preserves_structure():
    spec = _minimal_spec()
    dumped = json.loads(json.dumps(spec.to_dict(), ensure_ascii=False))
    reparsed = parse(dumped)

    assert reparsed.endpoint_count() == 1
    param = reparsed.modules[0].endpoints[0].params[0]
    assert param.constraints.min == 1
    assert param.constraints.max == 100


def test_missing_sheet_name_is_error():
    spec = _minimal_spec()
    spec.modules[0].sheet_name = ""
    result = validate(spec)

    assert any("sheet_name" in e for e in result.errors)


def test_duplicate_sheet_name_is_error():
    spec = _minimal_spec()
    spec.modules.append(Module(
        id="mod-002",
        module_name="Khác",
        sheet_name="POST_api_orders",
        endpoints=spec.modules[0].endpoints,
    ))
    result = validate(spec)

    assert any("trùng" in e for e in result.errors)


def test_empty_modules_is_error():
    spec = parse({"schema_version": SCHEMA_VERSION, "modules": []})
    result = validate(spec)

    assert any("không có module" in e for e in result.errors)


def test_module_without_endpoints_is_error():
    spec = _minimal_spec()
    spec.modules[0].endpoints = []
    result = validate(spec)

    assert any("không có endpoint" in e for e in result.errors)


def test_min_greater_than_max_is_error():
    spec = _minimal_spec()
    spec.modules[0].endpoints[0].params[0].constraints = Constraints(min=10, max=1)
    result = validate(spec)

    assert any("lớn hơn" in e for e in result.errors)


def test_required_param_without_constraints_is_missing_info():
    spec = _minimal_spec()
    param = spec.modules[0].endpoints[0].params[0]
    param.constraints = Constraints()
    result = validate(spec)

    assert result.errors == []
    assert any("quantity" in m for m in result.missing_info)


def test_invalid_param_location_is_error():
    spec = _minimal_spec()
    spec.modules[0].endpoints[0].params[0].in_ = "cookie"
    result = validate(spec)

    assert any("'in' không hợp lệ" in e for e in result.errors)


def test_http_endpoint_requires_path():
    spec = _minimal_spec()
    spec.modules[0].endpoints[0].path = ""
    result = validate(spec)

    assert any("thiếu 'path'" in e for e in result.errors)


def test_constraints_default_all_null():
    c = Constraints()
    assert c.to_dict() == {"min": None, "max": None, "pattern": None, "enum": None}
    assert c.is_empty() is True


def test_flags_defaults_and_sources():
    flags = Flags()
    assert flags.values["has_currency"] is False
    assert flags.source("has_currency") == "default"
    assert len(flags.pending_user_confirmation()) == 6


def test_flags_set_inferred_and_user():
    flags = Flags()
    flags.set("has_currency", True, source="inferred")
    flags.set("has_quota", True, source="user")

    assert flags.get("has_currency") is True
    assert flags.source("has_currency") == "inferred"
    assert "has_currency" in flags.pending_user_confirmation()
    assert "has_quota" not in flags.pending_user_confirmation()


def test_flags_reject_unknown_name():
    with pytest.raises(ValueError):
        Flags().set("khong_ton_tai", True)


def test_flags_reject_unknown_source():
    with pytest.raises(ValueError):
        Flags().set("has_currency", True, source="model")


def test_schema_version_mismatch_is_error():
    spec = _minimal_spec()
    spec.schema_version = "1.0"
    result = validate(spec)

    assert any("schema_version" in e for e in result.errors)


def test_duplicate_param_name_in_same_location_is_error():
    spec = _minimal_spec()
    spec.modules[0].endpoints[0].params.append(
        Param(name="quantity", in_="body", type="integer", required=True)
    )
    result = validate(spec)

    assert any("tham số trùng" in e for e in result.errors)
