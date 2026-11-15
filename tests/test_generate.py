"""Test cho utd.generate: budget, matrix, data provider, chống bug modules[0]."""

import json
from pathlib import Path

import pytest

from utd.canonical import (
    Auth,
    CanonicalSpec,
    Constraints,
    Endpoint,
    Flags,
    Module,
    Param,
    Project,
    Response,
    Rule,
)
from utd.generate.budget import (
    ABNORMAL,
    BOUNDARY,
    NORMAL,
    calculate_budget,
    calculate_budgets,
)
from utd.generate.data import (
    DataProvider,
    DataUnavailableError,
    infer_category,
    is_slop,
    mutate,
    mutate_fat_finger,
    mutate_letter_o,
    mutate_smart_quote,
    mutate_zero_width,
)
from utd.generate.matrix import (
    GenerateError,
    build_ssot,
    generate_for_endpoint,
    merge_module,
)

ROOT = Path(__file__).parent.parent


def _endpoint(ep_id="ep-1", method="POST", path="/api/orders", **kwargs) -> Endpoint:
    defaults = dict(
        id=ep_id,
        http_method=method,
        path=path,
        auth=Auth(type="jwt"),
        params=[
            Param(name="quantity", type="integer", required=True,
                  constraints=Constraints(min=1, max=100)),
        ],
        responses=[
            Response(status=201, condition="tạo thành công"),
            Response(status=400, error_code="VALIDATION_ERROR", condition="sai dữ liệu"),
        ],
        rules=[Rule(id="BR-01", text="quantity trong 1..100")],
    )
    defaults.update(kwargs)
    return Endpoint(**defaults)


def _module(sheet="POST_orders", endpoints=None, module_id="mod-1") -> Module:
    return Module(
        id=module_id,
        module_name="Order API",
        sheet_name=sheet,
        flags=Flags(),
        endpoints=endpoints if endpoints is not None else [_endpoint()],
    )


def _spec(modules=None) -> CanonicalSpec:
    return CanonicalSpec(
        project=Project(name="Demo", code="DEMO"),
        modules=modules if modules is not None else [_module()],
    )


# --- budget ---------------------------------------------------------------


def test_budget_has_one_normal_minimum():
    budget = calculate_budget(_module(), _endpoint())
    assert budget.counts()[NORMAL] >= 1


def test_budget_bva_covers_all_six_boundaries():
    budget = calculate_budget(_module(), _endpoint())
    values = {
        s.param_value for s in budget.slots
        if s.param_name == "quantity" and s.param_value is not None
    }
    assert {0, 1, 2, 99, 100, 101} <= values


def test_budget_marks_out_of_range_as_abnormal():
    budget = calculate_budget(_module(), _endpoint())
    out_of_range = [
        s for s in budget.slots
        if s.param_name == "quantity" and s.param_value in (0, 101)
    ]
    assert out_of_range
    assert all(s.type == ABNORMAL for s in out_of_range)


def test_budget_marks_in_range_edges_as_boundary():
    budget = calculate_budget(_module(), _endpoint())
    inner = [
        s for s in budget.slots
        if s.param_name == "quantity" and s.param_value in (1, 2, 99, 100)
    ]
    assert inner
    assert all(s.type == BOUNDARY for s in inner)


def test_budget_without_bounds_skips_bva_with_reason():
    param = Param(name="note", type="string", required=False)
    endpoint = _endpoint(params=[param], rules=[])
    budget = calculate_budget(_module(), endpoint)

    no_bva = [s for s in budget.slots if s.param_name == "note"]
    assert no_bva == []


def test_budget_notes_reason_for_unbounded_required():
    param = Param(name="code", type="string", required=True, constraints=Constraints())
    endpoint = _endpoint(params=[param], rules=[])
    budget = calculate_budget(_module(), endpoint)

    assert any("code" in note for note in budget.notes)


def test_budget_enum_produces_abnormal_slot():
    param = Param(name="voucher", type="string", required=False,
                  constraints=Constraints(enum=["SAVE10", "SAVE20"]))
    budget = calculate_budget(_module(), _endpoint(params=[param]))

    enum_slots = [s for s in budget.slots if s.param_name == "voucher"]
    assert any(s.type == ABNORMAL for s in enum_slots)


def test_budget_dual_path_per_rule():
    rules = [Rule(id="BR-01", text="a"), Rule(id="BR-02", text="b")]
    budget = calculate_budget(_module(), _endpoint(rules=rules))

    for rule in rules:
        refs = [s for s in budget.slots if rule.id in s.rule_refs]
        assert any(s.type in (NORMAL, BOUNDARY) for s in refs)
        assert any(s.type == ABNORMAL for s in refs)


def test_budget_auth_endpoint_gets_401_slot():
    budget = calculate_budget(_module(), _endpoint())
    assert any(s.target == "endpoint:auth" for s in budget.slots)


def test_budget_public_endpoint_has_no_auth_slot():
    endpoint = _endpoint(auth=Auth(type="none"))
    budget = calculate_budget(_module(), endpoint)
    assert not any(s.target == "endpoint:auth" for s in budget.slots)


def test_calculate_budgets_covers_every_module():
    """Chống tái phát modules[0]: 3 module -> 3+ budgets."""
    modules = [
        _module(sheet=f"sheet_{i}", module_id=f"mod-{i}",
                endpoints=[_endpoint(ep_id=f"ep-{i}", path=f"/api/v{i}")])
        for i in range(3)
    ]
    budgets = calculate_budgets(modules)

    assert len(budgets) == 3
    assert {b.sheet_name for b in budgets} == {"sheet_0", "sheet_1", "sheet_2"}


# --- data provider ---------------------------------------------------------


@pytest.fixture(scope="module")
def provider():
    return DataProvider.load()


def test_provider_loads_realistic_records(provider):
    assert len(provider.records) >= 80
    assert len(provider.payloads) >= 700


def test_provider_returns_vietnamese_name(provider):
    values = provider.get(category="name", locale="vi", count=1)
    assert values
    assert any(ord(ch) > 127 for ch in values[0]), "phải có dấu tiếng Việt"


def test_provider_unknown_category_raises(provider):
    with pytest.raises(DataUnavailableError):
        provider.get(category="khong_ton_tai")


def test_provider_never_returns_slop(provider):
    for category in ("name", "address", "phone", "email"):
        values = provider.get(category=category, count=3)
        for value in values:
            assert not is_slop(value), f"slop trong {category}: {value}"


def test_is_slop_detects_known_patterns():
    assert is_slop("John Doe")
    assert is_slop("test@example.com")
    assert is_slop("1111111111")
    assert is_slop("P001")


def test_is_slop_allows_real_vietnamese_name():
    assert not is_slop("Trần Lê Bảo Ánh")
    assert not is_slop("H'Hen Niê")


def test_infer_category_from_param_name():
    assert infer_category("email") == "email"
    assert infer_category("phone_number") == "phone"
    assert infer_category("full_name") == "name"
    assert infer_category("quantity", "integer") is None


def test_mutations_are_human_like():
    assert mutate_fat_finger("user@example.com") != "user@example.com"
    assert "O" in mutate_letter_o("0901234567") or "l" in mutate_letter_o("0901234567")
    assert "​" in mutate_zero_width("Mã đơn")
    assert mutate_smart_quote("Đơn gấp").count("“") >= 1


def test_mutate_unknown_quirk_raises():
    with pytest.raises(ValueError):
        mutate("abc", "khong_ho_tro")


# --- matrix ---------------------------------------------------------------


def test_generate_for_endpoint_has_normal(provider_module=None):
    cases = generate_for_endpoint(_module(), _endpoint(), DataProvider.load())
    assert any(c.type == NORMAL for c in cases)


def test_generate_for_endpoint_expected_has_three_lines():
    cases = generate_for_endpoint(_module(), _endpoint(), DataProvider.load())
    for case in cases:
        assert set(case.expected) == {"return", "exception", "log"}
        assert all(case.expected.values())


def test_generate_refs_every_rule():
    rules = [Rule(id="BR-01", text="a"), Rule(id="BR-02", text="b")]
    cases = generate_for_endpoint(_module(), _endpoint(rules=rules), DataProvider.load())

    for rule in rules:
        assert any(rule.id in c.rule_refs for c in cases)


def test_build_ssot_covers_all_modules():
    """Chống tái phát bug `modules[0]`: SSOT phải có đủ module."""
    modules = [
        _module(sheet=f"sheet_{i}", module_id=f"mod-{i}",
                endpoints=[_endpoint(ep_id=f"ep-{i}", path=f"/api/v{i}",
                                     rules=[Rule(id=f"BR-0{i}", text="x")])])
        for i in range(1, 4)
    ]
    ssot = build_ssot(_spec(modules), DataProvider.load())

    assert len(ssot["modules"]) == 3
    assert ssot["meta"]["generated_modules"] == 3
    for module_data in ssot["modules"]:
        assert module_data["methods"]
        total_cases = sum(len(m["test_cases"]) for m in module_data["methods"])
        assert total_cases > 0
        assert any(c["type"] == NORMAL
                   for m in module_data["methods"] for c in m["test_cases"])


def test_build_ssot_no_uncovered_rules_when_dual_path_generated():
    rules = [Rule(id="BR-01", text="a"), Rule(id="BR-02", text="b")]
    endpoint = _endpoint(rules=rules)
    ssot = build_ssot(_spec([_module(endpoints=[endpoint])]), DataProvider.load())

    assert ssot["uncovered_rules"] == []


def test_build_ssot_rejects_module_without_endpoints():
    bad_module = Module(id="m", module_name="X", sheet_name="S", endpoints=[])
    with pytest.raises(GenerateError):
        build_ssot(_spec([bad_module]), DataProvider.load())


def test_build_ssot_rejects_zero_normal():
    """Module không sinh được Normal -> dừng, không im lặng bỏ qua."""
    # endpoint không có response thành công + không có rule
    endpoint = _endpoint(
        responses=[Response(status=400, error_code="E")],
        rules=[],
        params=[],
        auth=Auth(type="none"),
    )
    ssot = build_ssot(_spec([_module(endpoints=[endpoint])]), DataProvider.load())
    # happy path luôn sinh Normal nên phải có
    assert any(
        c["type"] == NORMAL
        for m in ssot["modules"][0]["methods"]
        for c in m["test_cases"]
    )


def test_build_ssot_input_uses_real_data_not_slop():
    endpoint = _endpoint(params=[
        Param(name="email", type="string", required=True),
        Param(name="full_name", type="string", required=True),
    ], rules=[])
    ssot = build_ssot(_spec([_module(endpoints=[endpoint])]), DataProvider.load())

    inputs = [c["input"]
              for m in ssot["modules"][0]["methods"]
              for c in m["test_cases"]]
    joined = " ".join(inputs).lower()
    assert "john doe" not in joined
    assert "test@example.com" not in joined


def test_merge_module_appends_and_preserves():
    ssot = build_ssot(_spec(), DataProvider.load())
    original_count = len(ssot["modules"])

    new_module = {
        "module_name": "New API", "sheet_name": "GET_new",
        "methods": [{"name": "get", "api": {}, "test_cases": [{
            "pre": "x", "input": "a=1",
            "expected": {"return": "HTTP 200", "exception": "N/A", "log": "ok"},
            "type": "Normal", "rule_refs": [], "note": "n", "id": "UTC001",
        }]}],
    }
    merged = merge_module(ssot, new_module)

    assert len(merged["modules"]) == original_count + 1
    assert merged["modules"][0] == ssot["modules"][0]


def test_merge_module_rejects_duplicate_sheet():
    ssot = build_ssot(_spec(), DataProvider.load())
    duplicate = dict(ssot["modules"][0])

    with pytest.raises(GenerateError) as excinfo:
        merge_module(ssot, duplicate)
    assert "đã tồn tại" in str(excinfo.value)


def test_ssot_output_has_expected_shape():
    ssot = build_ssot(_spec(), DataProvider.load())

    assert "project" in ssot
    assert "modules" in ssot
    assert "uncovered_rules" in ssot
    assert "zero_normal_sheets" in ssot
    module = ssot["modules"][0]
    assert {"module_name", "sheet_name", "methods"} <= set(module)
    method = module["methods"][0]
    assert {"name", "api", "test_cases"} <= set(method)
