"""Adapter `draft`: nhận JSON do LLM viết từ SRS/mô tả và kiểm tra đủ trường.

Khác với các adapter khác, `draft` KHÔNG chuyển đổi gì — nó chỉ validate phần
tối thiểu mà LLM phải cung cấp và báo chính xác trường còn thiếu (exit 3).

Lý do tồn tại: với văn xuôi, LLM phải viết draft theo template; máy không thể
tự đoán endpoint/param từ đoạn văn. Adapter này là hợp đồng cho bước đó.

Draft tối thiểu:
    {
      "project": {...},
      "modules": [{
        "module_name": "...", "sheet_name": "...",
        "endpoints": [{"http_method": "POST", "path": "/x", "params": [...]}]
      }]
    }
"""

from __future__ import annotations

from typing import Any

from ..canonical import CanonicalSpec
from .rawjson import convert as convert_legacy


REQUIRED_MODULE_FIELDS = ("module_name", "endpoints")
REQUIRED_ENDPOINT_FIELDS = ("http_method", "path", "params")


def missing_fields(data: Any) -> list[str]:
    """Trả danh sách đường dẫn trường bắt buộc còn thiếu."""
    problems: list[str] = []

    if not isinstance(data, dict):
        return ["<root> phải là object"]

    modules = data.get("modules")
    if not isinstance(modules, list) or not modules:
        problems.append("modules: thiếu hoặc rỗng")
        return problems

    for m_index, module in enumerate(modules):
        prefix = f"modules[{m_index}]"
        if not isinstance(module, dict):
            problems.append(f"{prefix}: phải là object")
            continue
        for field in REQUIRED_MODULE_FIELDS:
            if field not in module or not module.get(field):
                problems.append(f"{prefix}.{field}: thiếu")
        if "sheet_name" not in module:
            problems.append(f"{prefix}.sheet_name: thiếu")

        endpoints = module.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            problems.append(f"{prefix}.endpoints: thiếu hoặc rỗng")
            continue

        for e_index, endpoint in enumerate(endpoints):
            ep_prefix = f"{prefix}.endpoints[{e_index}]"
            if not isinstance(endpoint, dict):
                problems.append(f"{ep_prefix}: phải là object")
                continue
            for field in REQUIRED_ENDPOINT_FIELDS:
                if field not in endpoint:
                    problems.append(f"{ep_prefix}.{field}: thiếu")
            params = endpoint.get("params")
            if isinstance(params, list):
                for p_index, param in enumerate(params):
                    if not isinstance(param, dict):
                        problems.append(f"{ep_prefix}.params[{p_index}]: phải là object")
                        continue
                    if not param.get("name"):
                        problems.append(f"{ep_prefix}.params[{p_index}].name: thiếu")
                    if "type" not in param:
                        problems.append(f"{ep_prefix}.params[{p_index}].type: thiếu")

    return problems


def convert(data: Any) -> CanonicalSpec:
    """Chỉ chuyển sau khi `missing_fields` rỗng; ngược lại raise ValueError."""
    problems = missing_fields(data)
    if problems:
        raise ValueError("draft thiếu trường bắt buộc: " + "; ".join(problems))
    # Draft dùng đúng hình dạng Canonical IR; tận dụng adapter legacy để chuẩn hoá
    # constraints và suy cờ (nó chấp nhận `endpoints` sẵn ở dạng module).
    return _convert_draft(data)


def _convert_draft(data: dict[str, Any]) -> CanonicalSpec:
    from ..canonical import parse

    spec = parse(data)
    from .flags import apply_inferred_flags

    for module in spec.modules:
        apply_inferred_flags(module)
    return spec


__all__ = ["convert", "missing_fields", "convert_legacy"]
