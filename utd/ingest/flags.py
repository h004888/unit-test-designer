"""Suy 3 cờ nghiệp vụ được phép tự động: has_status_field, is_multi_tenant, has_currency.

Ba cờ còn lại (has_quota, has_dependencies, has_unique_field) KHÔNG suy đoán được
và bắt buộc lấy từ câu trả lời người dùng ở stage interview.

Các cờ suy tự động ở đây mang nhãn `inferred` và phải xuất hiện trong checklist
để người dùng xác nhận.
"""

from __future__ import annotations

import re

from ..canonical import Flags, Module

CURRENCY_HINTS = re.compile(
    r"(currency|currenc|tiền tệ|vnd|usd|eur|jpy|amount|price|total|cost|fee|balance)",
    re.IGNORECASE,
)
TENANT_HINTS = re.compile(r"(tenant|organization|org_id|workspace|account_id)", re.IGNORECASE)
STATUS_HINTS = re.compile(r"(status|state|trạng thái|lifecycle)", re.IGNORECASE)

STATUS_VALUES = re.compile(
    r"(pending|approved|rejected|cancelled|canceled|active|inactive|draft|published|"
    r"shipped|delivered|refunded|expired|completed|failed)",
    re.IGNORECASE,
)


def _param_names(module: Module) -> list[str]:
    return [p.name for ep in module.endpoints for p in ep.params]


def _response_blobs(module: Module) -> list[str]:
    blobs: list[str] = []
    for ep in module.endpoints:
        for response in ep.responses:
            blobs.append(f"{response.error_code or ''} {response.condition or ''}")
    return blobs


def infer_has_currency(module: Module) -> bool:
    return any(CURRENCY_HINTS.search(name) for name in _param_names(module))


def infer_is_multi_tenant(module: Module) -> bool:
    return any(TENANT_HINTS.search(name) for name in _param_names(module))


def infer_has_status_field(module: Module) -> bool:
    if any(STATUS_HINTS.search(name) for name in _param_names(module)):
        return True
    return any(STATUS_VALUES.search(blob) for blob in _response_blobs(module))


def apply_inferred_flags(module: Module) -> Flags:
    """Đặt 3 cờ suy tự động với nguồn `inferred`. Không động vào 3 cờ còn lại."""
    module.flags.set("has_currency", infer_has_currency(module), source="inferred")
    module.flags.set("is_multi_tenant", infer_is_multi_tenant(module), source="inferred")
    module.flags.set("has_status_field", infer_has_status_field(module), source="inferred")
    return module.flags
