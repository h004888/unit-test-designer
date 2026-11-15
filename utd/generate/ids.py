"""utd.generate.ids - Cấp mã UTC ổn định trong từng sheet.

Ràng buộc:
  - `UTC001`, `UTC002` … đánh liên tục trong phạm vi 1 sheet.
  - Case cũ giữ mã khi chạy lại; case mới nhận mã ở cuối dải.
  - Không dồn mã khi chèn vào giữa danh sách.
"""

from __future__ import annotations

import re
from typing import Any

UTC_PATTERN = re.compile(r"UTC(\d{3,})")


def _max_utc(test_cases: list[dict[str, Any]]) -> int:
    highest = 0
    for case in test_cases:
        match = UTC_PATTERN.search(str(case.get("id", "")))
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def assign_ids(test_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gán mã UTC cho MỌI sheet trong SSOT, giữ nguyên mã đã có."""
    for module in test_cases:
        for method in module.get("methods", []):
            cases = method.get("test_cases", [])
            next_number = _max_utc(cases) + 1
            for case in cases:
                if case.get("id"):
                    continue
                case["id"] = f"UTC{next_number:03d}"
                next_number += 1
    return test_cases


def next_id(sheet_cases: list[dict[str, Any]]) -> str:
    return f"UTC{_max_utc(sheet_cases) + 1:03d}"
