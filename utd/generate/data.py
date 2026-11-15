"""utd.generate.data - Cấp dữ liệu từ kho thực tế + biến dị lỗi con người.

Ràng buộc từ spec `test-case-generation`:
  - Không tự sinh giá trị mẫu ("Nguyen Van A", "P001", "1111111111").
  - Kho thiếu danh mục -> báo lỗi và dừng, không rơi về giá trị mẫu.
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from importlib.resources import files as _pkg_files

DEFAULT_DATA_DIR = _pkg_files("utd") / "_data" / "data"

SLOP_PATTERNS = (
    r"^(john|jane)\s+doe$",
    r"^test@example\.com$",
    r"^123\s+main\s+st(reet)?$",
    r"^1{6,}$",
    r"^P\d{3}$",
    r"^orderId\s*=\s*1$",
    r"^productId\s*=\s*P\d+$",
)

# Từ khoá tên tham số -> danh mục dữ liệu tương ứng trong kho.
# Thứ tự quan trọng: kiểm tra từ khoá cụ thể trước, chung chung sau.
CATEGORY_HINTS: tuple[tuple[str, str], ...] = (
    ("email", "email"),
    ("phone", "phone"),
    ("mobile", "phone"),
    ("tel", "phone"),
    ("address", "address"),
    ("citizen_id", "citizen_id"),
    ("cccd", "citizen_id"),
    ("fullname", "name"),
    ("name", "name"),
)

# Danh mục dự phòng theo kiểu dữ liệu khi không khớp từ khoá nào.
# Kiểu số không dùng kho (kho không có số thật) — matrix tự sinh số hợp lệ.
TYPE_FALLBACK_CATEGORY = {
    "string": "name",
}


class DataUnavailableError(Exception):
    """Kho dữ liệu thiếu danh mục yêu cầu."""

    def __init__(self, category: str, message: str = ""):
        self.category = category
        super().__init__(message or f"Kho dữ liệu thiếu danh mục '{category}'")


@dataclass
class DataProvider:
    records: list[dict[str, Any]]
    payloads: list[dict[str, Any]]
    seed: int | None = None

    @classmethod
    def load(cls, data_dir: str | Path | None = None, seed: int | None = None) -> "DataProvider":
        target = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
        realistic = json.loads((target / "realistic.json").read_text(encoding="utf-8"))
        payload_file = json.loads((target / "payloads.json").read_text(encoding="utf-8"))
        return cls(
            records=list(realistic.get("records", [])),
            payloads=list(payload_file.get("records", [])),
            seed=seed,
        )

    def categories(self, locale: str | None = None) -> set[str]:
        return {
            str(r.get("category"))
            for r in self.records
            if locale is None or r.get("locale") in (locale, "all")
        }

    def get(self, category: str | None = None, locale: str | None = None,
            count: int = 1, quirk_type: str | None = None) -> list[str]:
        """Lấy `count` giá trị từ kho; thiếu danh mục -> DataUnavailableError."""
        candidates = self.records
        if category:
            candidates = [r for r in candidates if r.get("category") == category]
            if not candidates:
                raise DataUnavailableError(
                    category,
                    f"Kho dữ liệu thiếu danh mục '{category}' "
                    f"(hiện có: {', '.join(sorted(self.categories()))})",
                )
        if locale and locale != "all":
            candidates = [
                r for r in candidates
                if r.get("locale") in (locale, "all")
            ]
        if quirk_type and quirk_type != "all":
            candidates = [r for r in candidates if r.get("quirk_type") == quirk_type]

        if not candidates:
            raise DataUnavailableError(
                category or "(mọi danh mục)",
                "Không có bản ghi nào khớp điều kiện lọc"
            )

        rng = random.Random(self.seed) if self.seed is not None else random.Random()
        chosen: list[str] = []
        pool = list(candidates)
        for _ in range(max(1, count)):
            if not pool:
                pool = list(candidates)
            record = rng.choice(pool)
            pool.remove(record)
            chosen.append(str(record.get("payload_value", "")))
        return chosen

    def get_payloads(self, target_type: str | None = None,
                     category: str | None = None, limit: int = 5) -> list[str]:
        candidates = self.payloads
        if target_type:
            candidates = [p for p in candidates if p.get("target_type") == target_type]
        if category:
            candidates = [p for p in candidates if p.get("category") == category]
        return [str(p.get("payload_value", "")) for p in candidates[:limit]]


def infer_category(param_name: str, param_type: str = "string") -> str | None:
    lowered = param_name.lower()
    for hint, category in CATEGORY_HINTS:
        if hint in lowered:
            return category
    return TYPE_FALLBACK_CATEGORY.get(param_type)


def normalize_case(value: str) -> str:
    """Kho dữ liệu có giá trị ngẫu nhiên hoa/thường; chuẩn hoá về chữ thường."""
    return str(value).lower()


def is_slop(value: str) -> bool:
    text = str(value).strip().lower()
    for pattern in SLOP_PATTERNS:
        if re.match(pattern, text, re.IGNORECASE):
            return True
    return False


# --- biến dị lỗi con người -------------------------------------------------

QWERTY_NEIGHBOURS = {
    "q": "w", "w": "e", "e": "r", "r": "t", "t": "y",
    "a": "s", "s": "d", "d": "f", "f": "g",
    "z": "x", "x": "c", "c": "v", "v": "b",
}


def mutate_fat_finger(text: str, seed: int | None = None) -> str:
    """Gõ trượt phím: thay một ký tự bằng phím kề bên."""
    if not text:
        return text
    rng = random.Random(seed) if seed is not None else random.Random()
    positions = [i for i, ch in enumerate(text) if ch.lower() in QWERTY_NEIGHBOURS]
    if not positions:
        return text
    index = rng.choice(positions)
    replacement = QWERTY_NEIGHBOURS[text[index].lower()]
    if text[index].isupper():
        replacement = replacement.upper()
    return text[:index] + replacement + text[index + 1:]


def mutate_letter_o(text: str) -> str:
    """Gõ nhầm chữ O thay vì số 0 (phổ biến với số điện thoại)."""
    return text.replace("0", "O", 1) if "0" in text else text.replace("1", "l", 1)


def mutate_zero_width(text: str, marker: str = "​") -> str:
    """Chèn ký tự Zero-Width Space (dấu vết copy-paste)."""
    if not text:
        return marker
    index = max(1, len(text) // 2)
    return text[:index] + marker + text[index:]


def mutate_smart_quote(text: str) -> str:
    """Thay dấu nháy thẳng bằng nháy cong (smart quotes)."""
    if "'" in text:
        return text.replace("'", "’", 1)
    if '"' in text:
        return text.replace('"', "”", 1)
    return "“" + text + "”"


def mutate_trailing_space(text: str) -> str:
    return text + " "


def mutate_telex(text: str) -> str:
    """Lỗi gõ Telex: bỏ dấu tiếng Việt kiểu gõ nhầm."""
    mapping = {
        "á": "a1", "à": "a2", "ả": "a3", "ã": "a4", "ạ": "a5",
        "ế": "e1", "ệ": "e5", "ố": "o1", "ộ": "o5",
    }
    result = text
    for accented, telex in mapping.items():
        if accented in result:
            return result.replace(accented, telex, 1)
    return result


QUIRKS = {
    "fat_finger": mutate_fat_finger,
    "letter_o": mutate_letter_o,
    "zero_width": mutate_zero_width,
    "smart_quote": mutate_smart_quote,
    "trailing_space": mutate_trailing_space,
    "telex": mutate_telex,
}


def mutate(text: str, quirk: str) -> str:
    if quirk not in QUIRKS:
        raise ValueError(
            f"Quirk không hỗ trợ: '{quirk}' (hỗ trợ: {', '.join(sorted(QUIRKS))})"
        )
    return QUIRKS[quirk](text)
