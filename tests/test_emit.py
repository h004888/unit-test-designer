"""Test cho utd.emit: bố cục xlsx theo layout, công thức an toàn, markdown khớp."""

import json
from pathlib import Path

import pytest
from openpyxl import load_workbook

from utd.canonical import Auth, CanonicalSpec, Endpoint, Flags, Module, Param, Project, Response, Rule
from utd.emit.layout import (
    DETAIL_HEADERS,
    RESULT_LIST,
    SHEET_COVER,
    SHEET_STATISTICS,
    SHEET_TEST_CASES,
    clean_sheet_name,
)
from utd.emit.markdown import build_module_md, trace_rows, write_markdown
from utd.emit.xlsx import build_workbook, write_xlsx
from utd.generate.data import DataProvider
from utd.generate.ids import assign_ids
from utd.generate.matrix import build_ssot


def _spec(modules: int = 2) -> CanonicalSpec:
    result = []
    for index in range(1, modules + 1):
        module = Module(
            id=f"mod-{index}",
            module_name=f"API {index}",
            sheet_name=f"POST_api_{index}",
            flags=Flags(),
            endpoints=[
                Endpoint(
                    id=f"ep-{index}",
                    http_method="POST",
                    path=f"/api/v1/resource{index}",
                    auth=Auth(type="jwt"),
                    params=[Param(name="quantity", type="integer", required=True,
                                  constraints=__import__("utd.canonical", fromlist=["Constraints"]).Constraints(min=1, max=100))],
                    responses=[Response(status=201, condition="ok"),
                               Response(status=400, error_code="E", condition="bad")],
                    rules=[Rule(id=f"BR-0{index}", text="rule")],
                )
            ],
        )
        result.append(module)
    return CanonicalSpec(project=Project(name="Demo", code="DEMO", version="v1.0",
                                         issue_date="01/01/2026"), modules=result)


@pytest.fixture(scope="module")
def ssot():
    data = build_ssot(_spec(2), DataProvider.load())
    assign_ids(data["modules"])
    return data


@pytest.fixture(scope="module")
def workbook(ssot):
    return build_workbook(ssot)


# --- bố cục xlsx -----------------------------------------------------------


def test_sheet_order(workbook):
    names = workbook.sheetnames
    assert names[:3] == [SHEET_COVER, SHEET_TEST_CASES, SHEET_STATISTICS]
    assert names[3:] == ["POST_api_1", "POST_api_2"]


def test_detail_headers_exactly_sixteen(workbook):
    ws = workbook["POST_api_1"]
    headers = [ws.cell(row=11, column=c).value for c in range(1, 17)]
    assert headers == DETAIL_HEADERS
    assert len(headers) == 16


def test_detail_headers_use_green_fill(workbook):
    ws = workbook["POST_api_1"]
    assert ws.cell(row=11, column=1).fill.fgColor.rgb.endswith("339966")


def test_group_row_is_aqua_and_bold(workbook):
    ws = workbook["POST_api_1"]
    assert ws.cell(row=12, column=1).font.bold is True
    assert ws.cell(row=12, column=1).fill.fgColor.rgb.endswith("CCFFFF")


def test_number_of_tcs_formula(workbook):
    ws = workbook["POST_api_1"]
    assert ws["B3"].value == '=COUNTIF(A12:A1005,"UTC*")'


def test_round_count_formulas(workbook):
    ws = workbook["POST_api_1"]
    assert ws["B5"].value == "=COUNTIF($F$12:$F$1003,B$4)"
    assert ws["B6"].value == "=COUNTIF($I$12:$I$1003,B$4)"
    assert ws["B7"].value == "=COUNTIF($L$12:$L$1003,B$4)"


def test_type_count_formula(workbook):
    ws = workbook["POST_api_1"]
    assert ws["B9"].value == "=COUNTIF($E$12:$E$1003,B$8)"


def test_dropdown_has_all_four_results(workbook):
    ws = workbook["POST_api_1"]
    values = [ws.cell(row=2 + i, column=20).value for i in range(4)]
    assert tuple(values) == RESULT_LIST
    assert "Failed" in values


def test_hidden_columns(workbook):
    ws = workbook["POST_api_1"]
    for col in "JKMN":
        assert ws.column_dimensions[col].hidden is True
    assert ws.column_dimensions["T"].hidden is True


def test_no_gridlines_on_system_sheets(workbook):
    for name in (SHEET_COVER, SHEET_TEST_CASES, SHEET_STATISTICS):
        assert workbook[name].sheet_view.showGridLines is False


def test_cover_has_required_cells(workbook):
    ws = workbook[SHEET_COVER]
    assert ws["B2"].value == "UNIT TEST DOCUMENT"
    assert ws["A4"].value == "Project Name"
    assert ws["B6"].value == '=B5&"_UnitTest_"&F6'
    assert ws["A9"].value == "Record of change"


def test_test_cases_list_cross_sheet_formula(workbook):
    ws = workbook[SHEET_TEST_CASES]
    assert ws["D3"].value == "=Cover!B4"
    assert ws["D4"].value == "=Cover!B5"


def test_statistics_formulas_reference_module_sheets(workbook):
    ws = workbook[SHEET_STATISTICS]
    assert ws["C12"].value == "='POST_api_1'!B7"
    assert ws["I12"].value == "='POST_api_1'!B3"


def test_statistics_percent_guard_against_zero(workbook):
    ws = workbook[SHEET_STATISTICS]
    percent_formulas = [
        ws.cell(row=r, column=4).value
        for r in range(1, ws.max_row + 1)
        if str(ws.cell(row=r, column=4).value or "").startswith("=IF(I")
    ]
    assert len(percent_formulas) == 5
    for formula in percent_formulas:
        assert "=0,0," in formula


def test_statistics_subtotal_uses_sum(workbook):
    ws = workbook[SHEET_STATISTICS]
    assert ws["C14"].value == "=SUM(C12:C13)"


def test_zero_case_module_does_not_error(tmp_path):
    """Module 0 test case: công thức % phải trả 0, không lỗi chia 0."""
    from utd.emit.xlsx import build_workbook as build

    empty_ssot = {
        "project": {"name": "E", "code": "E", "creator": "", "reviewer": "",
                    "version": "v1", "issue_date": "", "reference": "", "environment": ""},
        "stats_round": 3,
        "modules": [{"module_name": "M", "sheet_name": "S", "methods": [],
                     "description": "", "pre_condition": ""}],
    }
    wb = build(empty_ssot)
    ws = wb[SHEET_STATISTICS]
    assert "IF(I" in ws["D15"].value


def test_clean_sheet_name_sanitises():
    used = set()
    assert clean_sheet_name("POST/api:orders", used) == "POST_api_orders"
    long_name = "x" * 40
    assert len(clean_sheet_name(long_name, used)) == 31


def test_clean_sheet_name_avoids_reserved():
    used = set()
    assert clean_sheet_name("Cover", used) == "Cover_M"


def test_clean_sheet_name_deduplicates():
    used = set()
    first = clean_sheet_name("Sheet", used)
    second = clean_sheet_name("Sheet", used)
    assert first != second


def test_write_xlsx_creates_readable_file(ssot, tmp_path):
    path = write_xlsx(ssot, tmp_path / "out.xlsx")
    assert path.exists()
    wb = load_workbook(path)
    assert len(wb.sheetnames) == 5


# --- markdown ------------------------------------------------------------


def test_markdown_one_file_per_module(ssot, tmp_path):
    files = write_markdown(ssot, tmp_path / "docs")
    names = {f.name for f in files}
    assert "POST_api_v1_resource1.md" in names
    assert "POST_api_v1_resource2.md" in names
    assert "index.md" in names


def test_markdown_has_sixteen_column_table(ssot):
    module = ssot["modules"][0]
    text = build_module_md(ssot, module, module["methods"][0])

    assert "| " + " | ".join(DETAIL_HEADERS) + " |" in text
    assert text.count("|") > 16


def test_markdown_traceability_lists_all_rules(ssot):
    module = ssot["modules"][0]
    method = module["methods"][0]
    text = build_module_md(ssot, module, method)
    rules, _ = trace_rows(method)

    assert "Traceability Matrix" in text
    for rule in rules:
        assert rule["id"] in text


def test_markdown_marks_uncovered_rule(ssot):
    module = ssot["modules"][0]
    method = dict(module["methods"][0])
    method = json.loads(json.dumps(method))
    method["api"]["rules"].append({"id": "BR-99", "text": "chưa có case", "source": ""})
    method["test_cases"] = [
        {**case, "rule_refs": [r for r in case["rule_refs"] if r != "BR-99"]}
        for case in method["test_cases"]
    ]

    text = build_module_md(ssot, module, method)
    assert "BR-99" in text
    assert "NO - cần bổ sung TC" in text


def test_markdown_matches_xlsx_case_count(ssot, tmp_path):
    write_markdown(ssot, tmp_path / "docs")
    workbook = build_workbook(ssot)

    for module in ssot["modules"]:
        sheet = workbook[module["sheet_name"]]
        ids_in_xlsx = [
            sheet.cell(row=r, column=1).value
            for r in range(12, sheet.max_row + 1)
            if str(sheet.cell(row=r, column=1).value or "").startswith("UTC")
        ]
        slug = module["sheet_name"].replace("POST_api_", "POST_api_v1_resource")
        text = (tmp_path / "docs" / f"{slug}.md").read_text(encoding="utf-8")
        for case_id in ids_in_xlsx:
            assert case_id in text, f"{module['sheet_name']}: {case_id} thiếu trong md"


def test_index_lists_every_module(ssot, tmp_path):
    write_markdown(ssot, tmp_path / "docs")
    index = (tmp_path / "docs" / "index.md").read_text(encoding="utf-8")

    for module in ssot["modules"]:
        assert module["sheet_name"] in index
    assert "**Total**" in index


def test_markdown_escapes_pipe_and_angle(ssot):
    module = ssot["modules"][0]
    method = json.loads(json.dumps(module["methods"][0]))
    method["test_cases"][0]["input"] = "a=<x> | b=y"
    text = build_module_md(ssot, module, method)

    assert "&lt;x&gt;" in text
    assert "\\|" in text
