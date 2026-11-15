"""utd.emit.xlsx - Sinh file .xlsx tổng thể theo `references/layout-xlsx.md`.

Bốn sheet hệ thống: Cover | Test Cases | Test Statistics | mỗi API một sheet.

Hai điểm sửa so với bản cũ:
  1. Công thức phần trăm đã bọc `IF(Total=0,0,...)` — bản cũ có nhưng không có test.
  2. Dropdown kết quả có đủ 4 giá trị (bản gốc thiếu `Failed`).
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.hyperlink import Hyperlink

from .formatting import (
    al,
    box,
    est_lines,
    fill,
    fmt_expected,
    fmt_input,
    fnt,
    put,
    q,
    style_range,
    tc_note,
)
from .layout import (
    AQUA,
    BROWN,
    COVER_WIDTHS,
    DETAIL_HEADER_ROW,
    DETAIL_HEADERS,
    DETAIL_WIDTHS,
    FIRST_GROUP_ROW,
    GREEN,
    INDIGO,
    LINK_BLUE,
    LINK_GREEN,
    NAVY,
    RESULT_LIST,
    ROUND_RESULT_COLS,
    SHEET_COVER,
    SHEET_STATISTICS,
    SHEET_TEST_CASES,
    STATISTICS_WIDTHS,
    TEST_CASES_WIDTHS,
    VALID_TYPES,
    WHITE,
    clean_sheet_name,
)
from .formatting import HAIR, MEDIUM, THIN


def _prepare_modules(ssot: dict) -> list[dict]:
    """Chuẩn hoá: 1 API = 1 sheet, tên sheet hợp lệ và duy nhất."""
    used: set[str] = set()
    result = []
    for module in ssot.get("modules", []):
        copy = dict(module)
        copy["sheet_name"] = clean_sheet_name(module.get("sheet_name") or "Module", used)
        result.append(copy)
    return result


def build_cover(wb: Workbook, ssot: dict) -> None:
    ws = wb.active
    ws.title = SHEET_COVER
    ws.sheet_view.showGridLines = False
    project = ssot["project"]

    for col, width in zip("ABCDEF", COVER_WIDTHS):
        ws.column_dimensions[col].width = width

    ws.row_dimensions[2].height = 75.75
    put(ws, "B2", "UNIT TEST DOCUMENT", fnt(20, True, color="000000"),
        border=box(THIN), align=al("center", "center", False), merge="B2:F2")

    label = dict(font=fnt(bold=True), fill_=fill(WHITE), border=box(THIN),
                 align=al("left", "center", False))
    value = dict(font=fnt(), border=box(THIN), align=al("left", "center", False))

    put(ws, "A4", "Project Name", **label)
    put(ws, "B4", project["name"], merge="B4:D4", **value)
    put(ws, "E4", "Creator", **label)
    put(ws, "F4", project["creator"], **value)
    put(ws, "A5", "Project Code", **label)
    put(ws, "B5", project["code"], merge="B5:D5", **value)
    put(ws, "E5", "Issue Date", **label)
    put(ws, "F5", project["issue_date"], **value)
    put(ws, "A6", "Document Code", **label)
    put(ws, "B6", '=B5&"_UnitTest_"&F6', merge="B6:D6", **value)
    put(ws, "E6", "Version", **label)
    put(ws, "F6", project["version"], **value)
    for row in (4, 5, 6):
        ws.row_dimensions[row].height = 18

    put(ws, "A9", "Record of change", fnt(bold=True), align=al("left", "bottom", False))
    headers = ["Effective Date", "Version", "Change Item", "*A,D,M",
               "Change description", "Reference"]
    for col, header in zip("ABCDEF", headers):
        put(ws, f"{col}10", header, fnt(bold=True, color=WHITE), fill(NAVY), box(HAIR),
            al("center", "center", False))

    changes = ssot.get("changes") or [{
        "date": project["issue_date"], "version": project["version"], "item": "All",
        "type": "A", "description": "Khởi tạo tài liệu thiết kế Unit Test",
        "reference": project["reference"],
    }]
    for index, change in enumerate(changes):
        row = 11 + index
        values = [change.get("date", ""), change.get("version", ""), change.get("item", ""),
                  change.get("type", ""), change.get("description", ""),
                  change.get("reference", "")]
        for col, val in zip("ABCDEF", values):
            put(ws, f"{col}{row}", val, fnt(), border=box(HAIR), align=al("left", "top"))
        ws.row_dimensions[row].height = max(26.25, 12.75 * est_lines(values[4], 38))


def build_test_cases_list(wb: Workbook, ssot: dict) -> None:
    ws = wb.create_sheet(SHEET_TEST_CASES)
    ws.sheet_view.showGridLines = False
    for col, width in zip("ABCDEF", TEST_CASES_WIDTHS):
        ws.column_dimensions[col].width = width

    ws.row_dimensions[1].height = 24.4
    put(ws, "D1", "TEST CASE LIST", fnt(20, True, color="000000"),
        align=al("left", "bottom", False))

    label = dict(font=fnt(bold=True, color=BROWN), fill_=fill(WHITE), border=box(THIN),
                 align=al("left", "center", False))
    link = dict(font=fnt(italic=True, color=LINK_GREEN), fill_=fill(WHITE),
                border=box(THIN), align=al("left", "center", False))

    put(ws, "B3", "Project Name", merge="B3:C3", **label)
    put(ws, "D3", "=Cover!B4", merge="D3:F3", **link)
    put(ws, "B4", "Project Code", merge="B4:C4", **label)
    put(ws, "D4", "=Cover!B5", merge="D4:F4", **link)

    env = ssot["project"]["environment"] or (
        "<Liệt kê môi trường cần thiết>\n1. Ngôn ngữ/Runtime\n2. Framework test\n"
        "3. Công cụ mock/coverage"
    )
    put(ws, "B5", "Test Environment Setup Description", merge="B5:C5",
        **{**label, "align": al("left", "center", True)})
    put(ws, "D5", env, fnt(), fill(WHITE), box(THIN), al("left", "top", True),
        merge="D5:F5")
    ws.row_dimensions[5].height = max(45, 12.75 * est_lines(env, 90) + 6)

    for col, header in zip("BCDEF", ["No", "Module Name", "Sheet Name", "Description",
                                     "Pre-Condition"]):
        put(ws, f"{col}8", header, fnt(bold=True, color=WHITE), fill(INDIGO), box(THIN),
            al("center", "center", False))
    ws.row_dimensions[8].height = 21

    for index, module in enumerate(ssot["modules"]):
        row = 9 + index
        put(ws, f"B{row}", index + 1, fnt(), fill(WHITE), box(THIN),
            al("center", "top", False))
        put(ws, f"C{row}", module["module_name"], fnt(), fill(WHITE), box(HAIR),
            al("left", "top", True))
        cell = put(ws, f"D{row}", module["sheet_name"],
                   fnt(color=LINK_BLUE), fill(WHITE), box(HAIR), al("left", "top", True))
        cell.font = fnt(color=LINK_BLUE, underline="single")
        cell.hyperlink = Hyperlink(
            ref=cell.coordinate,
            location=f"{q(module['sheet_name'])}!A1",
            display=module["sheet_name"],
        )
        put(ws, f"E{row}", module.get("description", ""), fnt(), fill(WHITE), box(HAIR),
            al("left", "top", True))
        put(ws, f"F{row}", module.get("pre_condition", ""), fnt(), fill(WHITE),
            box(HAIR), al("left", "top", True))
        ws.row_dimensions[row].height = max(
            15,
            12.75 * max(
                est_lines(module.get("description", ""), 34),
                est_lines(module.get("pre_condition", ""), 34),
                est_lines(module["module_name"], 26.5),
            ),
        )


def build_statistics(wb: Workbook, ssot: dict) -> None:
    ws = wb.create_sheet(SHEET_STATISTICS)
    ws.sheet_view.showGridLines = False
    project = ssot["project"]

    for col, width in zip("ABCDEFGHI", STATISTICS_WIDTHS):
        ws.column_dimensions[col].width = width

    ws.row_dimensions[2].height = 25.5
    put(ws, "A2", "UNIT TEST STATISTICS", fnt(20, True, color="000000"),
        align=al("center", "bottom", False), merge="A2:I2")

    label = dict(font=fnt(bold=True), fill_=fill(WHITE), border=box(THIN),
                 align=al("left", "center", False))
    value = dict(font=fnt(italic=True), fill_=fill(WHITE), border=box(THIN),
                 align=al("left", "center", False))

    put(ws, "A4", "Project Name", **label)
    put(ws, "B4", "=Cover!B4", merge="B4:C4", **value)
    put(ws, "D4", "Creator", merge="D4:E4", **label)
    put(ws, "F4", "=Cover!F4", merge="F4:I4", **value)
    put(ws, "A5", "Project Code", **label)
    put(ws, "B5", "=Cover!B5", merge="B5:C5", **value)
    put(ws, "D5", "Reviewer/Approver", merge="D5:E5", **label)
    put(ws, "F5", project["reviewer"], merge="F5:I5", **value)
    put(ws, "A6", "Document Code", **label)
    put(ws, "B6", '=B5&"_Test Report_"&Cover!F6', merge="B6:C6", **value)
    put(ws, "D6", "Issue Date", merge="D6:E6", **label)
    put(ws, "F6", "=Cover!F5", merge="F6:I6", **value)

    names = ", ".join(module["module_name"] for module in ssot["modules"])
    notes = ssot.get("notes") or f"Release gồm {len(ssot['modules'])} module: {names}"
    put(ws, "A7", "Notes", **label)
    put(ws, "B7", notes, fnt(italic=True), fill(WHITE), box(THIN), al("left", "top", True),
        merge="B7:I7")
    ws.row_dimensions[7].height = max(15.75, 12.75 * est_lines(notes, 90))

    headers = ["No", "Function code", "Passed", "Failed", "Untested",
               "N", "A", "B", "Total Test Cases"]
    for col, header in zip("ABCDEFGHI", headers):
        put(ws, f"{col}11", header, fnt(bold=True, color=WHITE), fill(NAVY), box(HAIR),
            al("center", "center", True))
    ws.row_dimensions[11].height = 14.25

    round_row = 4 + int(ssot.get("stats_round", 3))
    first = 12
    for index, module in enumerate(ssot["modules"]):
        row = first + index
        sheet_ref = q(module["sheet_name"])
        put(ws, f"A{row}", index + 1, fnt(), fill(WHITE), box(HAIR),
            al("center", "bottom", False))
        cell = put(ws, f"B{row}", module["sheet_name"], fnt(color=LINK_BLUE),
                   fill(WHITE), box(HAIR), al("left", "center", False))
        cell.font = fnt(color=LINK_BLUE, underline="single")
        cell.hyperlink = Hyperlink(ref=cell.coordinate,
                                   location=f"{sheet_ref}!A1",
                                   display=module["sheet_name"])
        formulas = {
            "C": f"={sheet_ref}!B{round_row}",
            "D": f"={sheet_ref}!C{round_row}",
            "E": f"={sheet_ref}!D{round_row}",
            "F": f"={sheet_ref}!B9",
            "G": f"={sheet_ref}!C9",
            "H": f"={sheet_ref}!D9",
            "I": f"={sheet_ref}!B3",
        }
        for col, formula in formulas.items():
            put(ws, f"{col}{row}", formula, fnt(color=LINK_GREEN), fill(WHITE), box(HAIR),
                al("center", "bottom", False))
    last = first + len(ssot["modules"]) - 1

    subtotal = last + 1
    put(ws, f"B{subtotal}", "Sub total", fnt(11, True, color=WHITE), fill(NAVY),
        align=al("left", "center", False))
    for col in "CDEFGHI":
        put(ws, f"{col}{subtotal}", f"=SUM({col}{first}:{col}{last})",
            fnt(bold=True, color=WHITE), fill(NAVY), box(HAIR), al("center", "bottom", False))

    total_cell = subtotal
    metrics = [
        ("Test coverage", f"=IF(I{total_cell}=0,0,(C{total_cell}+D{total_cell})*100/I{total_cell})"),
        ("Test successful coverage", f"=IF(I{total_cell}=0,0,C{total_cell}*100/I{total_cell})"),
        ("Normal case", f"=IF(I{total_cell}=0,0,F{total_cell}*100/I{total_cell})"),
        ("Abnormal case", f"=IF(I{total_cell}=0,0,G{total_cell}*100/I{total_cell})"),
        ("Boundary case", f"=IF(I{total_cell}=0,0,H{total_cell}*100/I{total_cell})"),
    ]
    for index, (name, formula) in enumerate(metrics):
        row = subtotal + 2 + index
        put(ws, f"B{row}", name, fnt(bold=True), align=al("left", "bottom", False))
        put(ws, f"D{row}", formula, fnt(bold=True), align=al("right", "bottom", False),
            nf="0.00")
        put(ws, f"E{row}", "%", fnt(), align=al("left", "bottom", False))

    put(ws, f"B{subtotal + 8}",
        f"* Số liệu Passed/Failed/Untested lấy theo Round {ssot.get('stats_round', 3)}. "
        "Test coverage = (Passed+Failed)/Total; Successful coverage = Passed/Total.",
        fnt(8, italic=True, color="808080"), align=al("left", "top", False))


def build_module_sheet(wb: Workbook, module: dict) -> None:
    ws = wb.create_sheet(module["sheet_name"])
    ws.sheet_view.showGridLines = False

    for index, width in enumerate(DETAIL_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(index)].width = width

    for col in "GHJKMN":
        ws.column_dimensions[col].outlineLevel = 1
    for col in "JKMN":
        ws.column_dimensions[col].hidden = True
    ws.column_dimensions["T"].width = 9
    ws.column_dimensions["T"].hidden = True
    ws.sheet_format.outlineLevelCol = 1

    label = dict(font=fnt(bold=True), border=box(MEDIUM), align=al("center", "top", True),
                 fill_=fill(WHITE))
    label_italic = dict(label, font=fnt(bold=True, italic=True))
    cell = dict(font=fnt(), border=box(THIN), align=al("center", "top", True),
                fill_=fill(WHITE))
    cell_italic = dict(cell, font=fnt(bold=True, italic=True))

    put(ws, "A2", "Code Module", **label)
    put(ws, "B2", module["sheet_name"], fnt(), fill(WHITE), box(THIN),
        al("left", "top", True), merge="B2:D2")
    put(ws, "A3", "Number of TCs", **label)
    put(ws, "B3", '=COUNTIF(A12:A1005,"UTC*")', **cell)

    put(ws, "A4", "Testing Round", **label_italic)
    for col, header in zip("BCD", ["Passed", "Failed", "Pending"]):
        put(ws, f"{col}4", header, **cell_italic)
    for round_number, col in ROUND_RESULT_COLS.items():
        row = 4 + round_number
        put(ws, f"A{row}", f"Round {round_number}", **label_italic)
        for c in "BCD":
            put(ws, f"{c}{row}", f"=COUNTIF(${col}$12:${col}$1003,{c}$4)", **cell)

    put(ws, "A8", "Testing Type", **label_italic)
    for col, header in zip("BCD", VALID_TYPES):
        put(ws, f"{col}8", header, **cell_italic)
    put(ws, "A9", "Count", **label_italic)
    for c in "BCD":
        put(ws, f"{c}9", f"=COUNTIF($E$12:$E$1003,{c}$8)", **cell)

    put(ws, "T1", "List", fnt(8, italic=True, color="808080"))
    for index, value in enumerate(RESULT_LIST):
        put(ws, f"T{2 + index}", value, fnt(color="000000"))

    ws.row_dimensions[DETAIL_HEADER_ROW].height = 25.5
    for index, header in enumerate(DETAIL_HEADERS, start=1):
        put(ws, f"{get_column_letter(index)}{DETAIL_HEADER_ROW}", header,
            fnt(bold=True, color=WHITE), fill(GREEN), box(THIN),
            al("center", "center", True))

    body = dict(font=fnt(), fill_=fill(WHITE), border=box(THIN),
                align=al("left", "top", True))
    row = FIRST_GROUP_ROW

    for method in module.get("methods", []):
        style_range(ws, f"A{row}:P{row}", fnt(bold=True), fill(AQUA), box(THIN),
                    al("left", "center", False))
        ws[f"A{row}"].value = method["name"]
        ws.row_dimensions[row].height = 15.75
        row += 1

        for case in method.get("test_cases", []):
            expected = fmt_expected(case)
            input_text = fmt_input(case.get("input"))
            pre = case.get("pre") or case.get("pre_conditions") or "N/A"
            note = tc_note(case)
            values = {
                "A": case.get("id", ""),
                "B": pre,
                "C": input_text,
                "D": expected,
                "E": case.get("type", ""),
                "F": "Pending",
                "I": "Pending",
                "L": "Pending",
                "O": case.get("defect_ids", ""),
                "P": note,
            }
            for index in range(1, 17):
                col = get_column_letter(index)
                put(ws, f"{col}{row}", values.get(col), **body)

            lines = max(
                3,
                est_lines(expected, DETAIL_WIDTHS[3]),
                est_lines(input_text, DETAIL_WIDTHS[2]),
                est_lines(pre, DETAIL_WIDTHS[1]),
                est_lines(note, DETAIL_WIDTHS[15]),
            )
            ws.row_dimensions[row].height = 12.75 * lines + 2
            for col in "GJM":
                ws[f"{col}{row}"].number_format = "dd/mm/yyyy"
            row += 1

    last_row = max(row - 1, FIRST_GROUP_ROW) + 100
    result_validation = DataValidation(type="list", formula1="=$T$2:$T$5", allow_blank=True)
    type_validation = DataValidation(type="list",
                                     formula1='"Normal,Abnormal,Boundary"',
                                     allow_blank=False)
    ws.add_data_validation(result_validation)
    ws.add_data_validation(type_validation)
    for col in ROUND_RESULT_COLS.values():
        result_validation.add(f"{col}{FIRST_GROUP_ROW}:{col}{last_row}")
    type_validation.add(f"E{FIRST_GROUP_ROW}:E{last_row}")


def build_workbook(ssot: dict) -> Workbook:
    """Dựng Workbook đầy đủ từ SSOT."""
    prepared = dict(ssot)
    prepared["modules"] = _prepare_modules(ssot)

    workbook = Workbook()
    build_cover(workbook, prepared)
    build_test_cases_list(workbook, prepared)
    build_statistics(workbook, prepared)
    for module in prepared["modules"]:
        build_module_sheet(workbook, module)
    return workbook


def write_xlsx(ssot: dict, out_path: str | Path) -> Path:
    """Ghi .xlsx qua file tạm rồi thay thế nguyên tử."""
    from ..io import atomic_write_bytes
    import io as _io

    workbook = build_workbook(ssot)
    buffer = _io.BytesIO()
    workbook.save(buffer)
    return atomic_write_bytes(out_path, buffer.getvalue())
