"""utd.ingest - Adapter chuẩn hoá các định dạng đầu vào về Canonical IR 2.0."""

from __future__ import annotations

from typing import Any

from ..canonical import CanonicalSpec
from . import drafts, openapi, rawjson, swagger

ADAPTERS = {
    "utd-v1": rawjson.convert,
    "openapi": openapi.convert,
    "swagger": swagger.convert,
    "draft": drafts.convert,
}


class IngestError(Exception):
    """Lỗi ingest kèm mã exit: 2 = cấu trúc, 3 = thiếu thông tin."""

    def __init__(self, message: str, exit_code: int, details: list[str] | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.details = details or []


def convert(source_kind: str, data: Any) -> CanonicalSpec:
    if source_kind not in ADAPTERS:
        raise IngestError(
            f"Loại nguồn không hỗ trợ: {source_kind}",
            exit_code=2,
            details=[f"hỗ trợ: {', '.join(sorted(ADAPTERS))}"],
        )
    return ADAPTERS[source_kind](data)
