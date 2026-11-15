"""utd.emit.layout - Hằng số bố cục báo cáo, đối chiếu `references/layout-xlsx.md`.

Giữ nguyên mọi giá trị của bản cũ để tài liệu xuất ra không đổi hình thức.
"""

from __future__ import annotations

FONT_NAME = "Tahoma"

NAVY = "000080"
INDIGO = "333399"
GREEN = "339966"
AQUA = "CCFFFF"
BROWN = "993300"
LINK_GREEN = "008000"
LINK_BLUE = "0000FF"
WHITE = "FFFFFF"

VALID_TYPES = ("Normal", "Abnormal", "Boundary")
RESULT_LIST = ("Passed", "Failed", "Pending", "N/A")
RESERVED_SHEETS = {"cover", "test cases", "test statistics"}

DETAIL_HEADERS = [
    "Test Case ID", "Pre-conditions", "Input parameters", "Expected Results", "Type",
    "Round 1", "Test date", "Tester",
    "Round 2", "Test date", "Tester",
    "Round 3", "Test date", "Tester",
    "Defect IDs", "Note",
]
DETAIL_WIDTHS = [17, 14.1, 22, 36, 10.5, 10, 10.5, 10.5, 10, 10.5, 10.5, 10, 10.5, 10.5, 20.4, 30]
ROUND_RESULT_COLS = {1: "F", 2: "I", 3: "L"}
FIRST_GROUP_ROW = 12
DETAIL_HEADER_ROW = 11

COVER_WIDTHS = [28.1, 10, 14.3, 8, 38, 48.1]
TEST_CASES_WIDTHS = [1.3, 11.8, 26.5, 24, 34, 34]
STATISTICS_WIDTHS = [17.5, 26.7, 12.1, 11, 12, 6, 6, 6, 21]

SHEET_COVER = "Cover"
SHEET_TEST_CASES = "Test Cases"
SHEET_STATISTICS = "Test Statistics"


def clean_sheet_name(name: str, used: set[str]) -> str:
    """Tên sheet hợp lệ: ≤31 ký tự, không chứa [ ] : * ? / \\, không trùng."""
    import re

    base = re.sub(r"[\[\]:*?/\\]", "_", str(name)).strip()[:31] or "Module"
    if base.lower() in RESERVED_SHEETS:
        base = (base + "_M")[:31]
    candidate, index = base, 2
    while candidate.lower() in used:
        suffix = f"_{index}"
        candidate = base[: 31 - len(suffix)] + suffix
        index += 1
    used.add(candidate.lower())
    return candidate
