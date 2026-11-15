"""utd.match.tier - Gán CRITICAL / STANDARD từ dữ liệu, không hardcode id.

Bản cũ hardcode danh sách `critical_ids` 18 phần tử trong mã. Hệ quả: thêm rule
mới vào JSON thì phải sửa Python, và rule mới mặc định thành STANDARD dù bản
chất là nghiệp vụ.

Bản mới đọc `data/tiers.json`, nơi chứa:
  - critical_if_strictness: nhóm strictness bắt buộc hỏi trực tiếp
  - critical_dimensions: phân hệ domain thuộc nghiệp vụ
  - critical_category_keywords: từ khoá trong `category` cũng buộc CRITICAL
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from importlib.resources import files as _pkg_files

DEFAULT_TIERS_PATH = _pkg_files("utd") / "_data" / "data" / "tiers.json"

CRITICAL = "CRITICAL"
STANDARD = "STANDARD"


def load_tier_config(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else DEFAULT_TIERS_PATH
    with target.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {
        "critical_if_strictness": set(data.get("critical_if_strictness") or ["MANDATORY"]),
        "critical_dimensions": set(data.get("critical_dimensions") or []),
        "critical_category_keywords": [
            str(k).lower() for k in (data.get("critical_category_keywords") or [])
        ],
        "standard_dimensions": set(data.get("standard_dimensions") or []),
    }


def determine_tier(rule: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    """Trả 'CRITICAL' hoặc 'STANDARD' cho một rule."""
    if config is None:
        config = load_tier_config()

    dimension = str(rule.get("dimension", ""))
    category = str(rule.get("category", "")).lower()
    strictness = str(rule.get("strictness", "")).upper()

    if dimension in config["standard_dimensions"]:
        return STANDARD

    if dimension in config["critical_dimensions"]:
        return CRITICAL

    if strictness in config["critical_if_strictness"]:
        return CRITICAL

    if any(keyword in category for keyword in config["critical_category_keywords"]):
        return CRITICAL

    return STANDARD


def describe_tier_decision(rule: dict[str, Any], config: dict[str, Any] | None = None) -> str:
    """Giải thích vì sao rule nhận tier đó (dùng cho báo cáo)."""
    if config is None:
        config = load_tier_config()

    dimension = str(rule.get("dimension", ""))
    category = str(rule.get("category", "")).lower()
    strictness = str(rule.get("strictness", "")).upper()

    if dimension in config["standard_dimensions"]:
        return f"dimension '{dimension}' thuộc nhóm chuẩn kỹ thuật"
    if dimension in config["critical_dimensions"]:
        return f"dimension '{dimension}' thuộc nhóm nghiệp vụ"
    if strictness in config["critical_if_strictness"]:
        return f"strictness '{strictness}' bắt buộc hỏi trực tiếp"

    matched = [k for k in config["critical_category_keywords"] if k in category]
    if matched:
        return f"category chứa từ khoá nghiệp vụ: {', '.join(matched)}"

    return "không có dấu hiệu nghiệp vụ -> chuẩn kỹ thuật"
