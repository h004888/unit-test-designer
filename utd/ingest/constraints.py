"""Chuyển ràng buộc dạng chuỗi tự do sang `Constraints` cấu trúc.

Đây là điểm DUY NHẤT trong v2 được phép đọc chuỗi mô tả ràng buộc. Sau ingest,
mọi stage khác chỉ đọc `constraints.min/max/pattern/enum`.

Chuỗi đầu vào có thể là mô tả tự do ("1..100", "tối đa 100", "Bearer <JWT>",
"<= 50 ký tự"...). Nếu không trích được số, trả Constraints rỗng — KHÔNG đoán.
"""

from __future__ import annotations

import re

from ..canonical import Constraints

# Khoảng dạng `a..b`, `a - b`, `từ a đến b`
_RANGE = re.compile(r"(\d+)\s*(?:\.\.|->|-|đến)\s*(\d+)", re.IGNORECASE)

# Khoảng dạng `a <= name <= b` hoặc `a ≤ name ≤ b`
_RANGE_INEQ = re.compile(
    r"(\d+)\s*(?:<=|≤|<)\s*[^<=>≤≥]+\s*(?:<=|≤|<)\s*(\d+)", re.IGNORECASE
)

# `>= a và <= b` / `a và <= b` (cận dưới + cận trên cùng chuỗi)
_RANGE_AND = re.compile(
    r"(?:>=|≥|từ)\s*(\d+)[\s\S]*(?:<=|≤|đến)\s*(\d+)", re.IGNORECASE
)
# Hoặc thứ tự ngược: `<= b và >= a`
_RANGE_AND_REV = re.compile(
    r"(?:<=|≤)\s*(\d+)[\s\S]*(?:>=|≥)\s*(\d+)", re.IGNORECASE
)

# Các từ khoá chỉ định cận dưới / cận trên
_MIN = re.compile(r"(?:>=|≥|min\s*[=:]?\s*|tối thiểu\s*|ít nhất\s*)(\d+)", re.IGNORECASE)
_MAX = re.compile(r"(?:<=|≤|max\s*[=:]?\s*|tối đa\s*|nhiều nhất\s*)(\d+)", re.IGNORECASE)

# Số trần trụi đứng riêng: "100 ký tự", "không quá 100"
_MAX_BARE = re.compile(r"(\d+)\s*(?:ký tự|char|chars|characters|đơn vị|items?|phần tử)", re.IGNORECASE)

# Enum dạng "[A|B|C]" hoặc "A, B, C"
_ENUM_BRACKETS = re.compile(r"\[([^\[\]]+)\]")
_ENUM_VALUES = re.compile(r"'([^']+)'|\"([^\"]+)\"")


def _strip_bearer(text: str) -> bool:
    lowered = text.lower()
    return "bearer" in lowered or "jwt" in lowered or "api key" in lowered


def parse_constraints(raw: object) -> Constraints:
    """Trả Constraints từ chuỗi mô tả. Không nhận diện được thì trả rỗng."""
    if raw is None:
        return Constraints()
    if isinstance(raw, dict):
        return Constraints.from_dict(raw)
    if not isinstance(raw, str):
        return Constraints()

    text = raw.strip()
    if not text:
        return Constraints()

    # Chuỗi kiểu "Bearer <JWT hợp lệ>" không phải ràng buộc số.
    if _strip_bearer(text):
        return Constraints()

    min_value = None
    max_value = None

    range_match = _RANGE.search(text) or _RANGE_INEQ.search(text)
    if range_match:
        min_value = int(range_match.group(1))
        max_value = int(range_match.group(2))
    else:
        and_match = _RANGE_AND.search(text)
        if and_match:
            min_value = int(and_match.group(1))
            max_value = int(and_match.group(2))
        else:
            # `<= b và >= a`: nhóm 1 là max, nhóm 2 là min
            rev_match = _RANGE_AND_REV.search(text)
            if rev_match:
                max_value = int(rev_match.group(1))
                min_value = int(rev_match.group(2))

        if min_value is None and max_value is None:
            min_match = _MIN.search(text)
            if min_match:
                min_value = int(min_match.group(1))
            max_match = _MAX.search(text)
            if max_match:
                max_value = int(max_match.group(1))
            elif not min_match:
                bare = _MAX_BARE.search(text)
                if bare:
                    max_value = int(bare.group(1))

    if min_value is not None and max_value is not None and min_value > max_value:
        min_value, max_value = max_value, min_value

    pattern = text if text.startswith("/") and text.endswith("/") else None
    enum = _parse_enum(text)

    return Constraints(min=min_value, max=max_value, pattern=pattern, enum=enum)


def _parse_enum(text: str) -> list[str] | None:
    bracket = _ENUM_BRACKETS.search(text)
    if bracket:
        body = bracket.group(1)
        if "|" in body:
            values = [v.strip() for v in body.split("|") if v.strip()]
            return values or None
        if "," in body:
            values = [v.strip() for v in body.split(",") if v.strip()]
            return values or None
        return None

    if "một trong" in text.lower() or "enum" in text.lower():
        quoted = _ENUM_VALUES.findall(text)
        values = [a or b for a, b in quoted if (a or b)]
        return values or None

    return None
