"""Chống tái phát: generator, budget, và ID không dừng ở module đầu.

Bản cũ (`test_matrix_generator.py`, `test_budget_calculator.py`) chỉ đọc
`modules[0].methods[0]`, khiến spec nhiều API chỉ sinh được 1 sheet. Test này
khoá lại hành vi đúng.
"""

import json
from pathlib import Path

import pytest

from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project
from utd.generate.budget import calculate_budgets
from utd.generate.data import DataProvider
from utd.generate.ids import assign_ids, next_id
from utd.generate.matrix import build_ssot, merge_module


def _endpoint(index: int) -> Endpoint:
    return Endpoint(
        id=f"ep-{index}",
        http_method="POST" if index % 2 else "GET",
        path=f"/api/v1/resource-{index}",
        auth=Auth(type="jwt"),
        params=[Param(name=f"field_{index}", type="string", required=True)],
    )


def _spec(module_count: int) -> CanonicalSpec:
    modules = [
        Module(
            id=f"mod-{i}",
            module_name=f"API {i}",
            sheet_name=f"sheet_{i}",
            flags=Flags(),
            endpoints=[_endpoint(i)],
        )
        for i in range(1, module_count + 1)
    ]
    return CanonicalSpec(project=Project(name="Multi"), modules=modules)


def test_budgets_cover_every_module():
    budgets = calculate_budgets(_spec(5).modules)
    assert len(budgets) == 5
    assert {b.sheet_name for b in budgets} == {f"sheet_{i}" for i in range(1, 6)}


def test_ssot_covers_every_module():
    ssot = build_ssot(_spec(4), DataProvider.load())
    assert len(ssot["modules"]) == 4
    assert {m["sheet_name"] for m in ssot["modules"]} == {
        f"sheet_{i}" for i in range(1, 5)
    }


def test_every_module_has_normal_case():
    ssot = build_ssot(_spec(3), DataProvider.load())
    for module in ssot["modules"]:
        cases = [c for m in module["methods"] for c in m["test_cases"]]
        assert any(c["type"] == "Normal" for c in cases), module["sheet_name"]


def test_every_module_has_test_cases():
    ssot = build_ssot(_spec(3), DataProvider.load())
    for module in ssot["modules"]:
        total = sum(len(m["test_cases"]) for m in module["methods"])
        assert total > 0, module["sheet_name"]


def test_ids_are_continuous_per_sheet():
    ssot = build_ssot(_spec(2), DataProvider.load())
    assign_ids(ssot["modules"])

    for module in ssot["modules"]:
        ids = [c["id"] for m in module["methods"] for c in m["test_cases"]]
        numbers = [int(i[3:]) for i in ids]
        assert numbers == sorted(numbers)
        assert numbers[0] == 1
        assert len(numbers) == len(set(numbers))


def test_existing_ids_preserved_on_regeneration():
    """Case cũ phải giữ mã; case mới nối tiếp dải."""
    module = {
        "module_name": "X", "sheet_name": "S",
        "methods": [{
            "name": "f", "api": {},
            "test_cases": [
                {"id": "UTC001", "type": "Normal"},
                {"id": "UTC002", "type": "Abnormal"},
                {"type": "Boundary"},  # case mới, chưa có mã
            ],
        }],
    }
    assign_ids([module])

    cases = module["methods"][0]["test_cases"]
    assert cases[0]["id"] == "UTC001"
    assert cases[1]["id"] == "UTC002"
    assert cases[2]["id"] == "UTC003"


def test_insert_in_middle_does_not_shift_later_ids():
    module = {
        "module_name": "X", "sheet_name": "S",
        "methods": [{
            "name": "f", "api": {},
            "test_cases": [
                {"id": "UTC001", "type": "Normal"},
                {"type": "Boundary"},          # chèn vào giữa
                {"id": "UTC002", "type": "Abnormal"},
            ],
        }],
    }
    assign_ids([module])

    cases = module["methods"][0]["test_cases"]
    assert cases[0]["id"] == "UTC001"
    assert cases[1]["id"] == "UTC003", "case chèn giữa nhận mã ở cuối dải"
    assert cases[2]["id"] == "UTC002"


def test_next_id_uses_max_plus_one():
    assert next_id([{"id": "UTC013"}]) == "UTC014"
    assert next_id([]) == "UTC001"


def test_merge_preserves_existing_modules_and_ids():
    ssot = build_ssot(_spec(2), DataProvider.load())
    assign_ids(ssot["modules"])

    snapshot = json.loads(json.dumps(ssot["modules"]))

    new_module = {
        "module_name": "New", "sheet_name": "sheet_new",
        "methods": [{"name": "f", "api": {}, "test_cases": [{
            "pre": "x", "input": "a=1",
            "expected": {"return": "HTTP 200", "exception": "N/A", "log": "ok"},
            "type": "Normal", "rule_refs": [], "note": "n",
        }]}],
    }
    merged = merge_module(ssot, new_module)
    assign_ids(merged["modules"])

    assert len(merged["modules"]) == 3
    assert merged["modules"][:2] == snapshot, "module cũ phải nguyên vẹn từng byte"
    assert merged["modules"][2]["methods"][0]["test_cases"][0]["id"] == "UTC001"
