"""utd.emit.formatting - Định dạng ô, ước lượng dòng, escape Markdown.

Bản port từ `build_unit_test_doc.py` (phần đã đúng), giữ nguyên hành vi.
"""

from __future__ import annotations

import math
import re

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .layout import FONT_NAME

THIN = Side(style="thin")
HAIR = Side(style="hair")
MEDIUM = Side(style="medium")


def fnt(size: int = 10, bold: bool = False, italic: bool = False,
        color: str | None = None, underline: str | None = None) -> Font:
    kwargs = dict(name=FONT_NAME, size=size, bold=bold, italic=italic)
    if color:
        kwargs["color"] = color
    if underline:
        kwargs["underline"] = underline
    return Font(**kwargs)


def fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def box(side: Side) -> Border:
    return Border(left=side, right=side, top=side, bottom=side)


def al(horizontal: str = "left", vertical: str = "top", wrap: bool = True) -> Alignment:
    return Alignment(horizontal=horizontal, vertical=vertical, wrap_text=wrap)


def style_range(ws, rng, font=None, fill_=None, border=None, align=None, nf=None) -> None:
    target = ws[rng]
    if not isinstance(target, tuple):
        target = ((target,),)
    elif target and not isinstance(target[0], tuple):
        target = (target,)
    for row in target:
        for cell in row:
            if font:
                cell.font = font
            if fill_:
                cell.fill = fill_
            if border:
                cell.border = border
            if align:
                cell.alignment = align
            if nf:
                cell.number_format = nf


def put(ws, ref, value=None, font=None, fill_=None, border=None, align=None,
        nf=None, merge=None):
    rng = merge or ref
    if merge:
        ws.merge_cells(merge)
    style_range(ws, rng, font, fill_, border, align, nf)
    ws[ref].value = value
    return ws[ref]


def est_lines(text, width: float) -> int:
    """Ước lượng số dòng hiển thị của text trong ô rộng `width` (đơn vị Excel)."""
    if text is None:
        return 1
    chars = max(int(width * 1.05), 4)
    return sum(max(1, math.ceil(len(part) / chars)) for part in str(text).split("\n"))


def q(sheet_name: str) -> str:
    """Quote tên sheet dùng trong công thức Excel."""
    return "'" + sheet_name.replace("'", "''") + "'"


# --- định dạng nội dung test case -----------------------------------------


def fmt_input(value) -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, dict):
        return "; ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "\n".join(str(x) for x in value)
    return str(value)


def fmt_expected(case: dict) -> str:
    expected = case.get("expected")
    if isinstance(expected, str):
        return expected
    expected = expected or {}
    ret = expected.get("return", case.get("return", "N/A"))
    exc = expected.get("exception", case.get("exception", "N/A"))
    log = expected.get("log", case.get("log", "N/A"))
    return f"Return: {ret}\nException: {exc}\nLog Message: {log}"


def tc_note(case: dict) -> str:
    note = case.get("note", "") or ""
    refs = case.get("rule_refs") or []
    if isinstance(refs, str):
        refs = [refs]
    if refs:
        note = (note + " | " if note else "") + "Ref: " + ", ".join(refs)
    return note


# --- Markdown -------------------------------------------------------------


def md_cell(value) -> str:
    """Escape ô bảng Markdown: newline -> <br>, | -> \\|, escape < > &."""
    if value is None:
        return ""
    text = (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return text.replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def md_row(cells) -> str:
    return "| " + " | ".join(md_cell(c) for c in cells) + " |"


def slugify(text) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_")
    return cleaned[:60] or "api"
