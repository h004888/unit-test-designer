"""Adapter `utd-v1`: đọc spec JSON do bản cũ sinh ra.

Bản cũ có dạng:
    modules[].methods[].api{http_method, path, auth, request[], responses[], rules[]}
    params có `constraints` là chuỗi tự do ("1..100", "Bearer <JWT hợp lệ>")

Adapter này làm phẳng `methods` thành `endpoints` và chuẩn hoá `constraints`.
Test case cũ KHÔNG được đọc — `generate` sinh lại toàn bộ.
"""

from __future__ import annotations

from typing import Any

from ..canonical import (
    Auth,
    CanonicalSpec,
    Endpoint,
    Module,
    Param,
    Project,
    Response,
    Rule,
)
from .constraints import parse_constraints
from .flags import apply_inferred_flags


def _slug(text: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in text.lower())
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")


def _method_to_sheet_name(method: dict[str, Any], module_name: str) -> str:
    api = method.get("api") or {}
    http_method = str(api.get("http_method", "")).upper()
    path = str(api.get("path", "")).strip()
    if http_method and path:
        # /api/orders/{id} -> GET_api_orders_id
        flat = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
        flat = flat.replace("-", "_")
        return f"{http_method}_{flat}"[:31]
    return _slug(method.get("name", module_name) or module_name)[:31] or "Sheet"


def _normalise_auth(raw: Any) -> Auth:
    if isinstance(raw, dict):
        return Auth.from_dict(raw)
    text = str(raw or "").strip()
    if not text or text.lower() in ("none", "public", "n/a"):
        return Auth(type="none", roles=[])
    lowered = text.lower()
    if "oauth" in lowered:
        auth_type = "oauth"
    elif "jwt" in lowered or "bearer" in lowered:
        auth_type = "jwt"
    elif "api" in lowered and "key" in lowered:
        auth_type = "api_key"
    else:
        auth_type = "other"
    return Auth(type=auth_type, roles=[])


def _endpoint_id(module_index: int, endpoint_index: int) -> str:
    return f"ep-{module_index + 1:03d}-{endpoint_index + 1:03d}"


def _convert_param(raw: dict[str, Any]) -> Param:
    return Param(
        name=str(raw.get("name", "")),
        in_=str(raw.get("in", "body")),
        type=str(raw.get("type", "string")),
        required=bool(raw.get("required", False)),
        format=raw.get("format"),
        enum=raw.get("enum") if isinstance(raw.get("enum"), list) else None,
        default=raw.get("default"),
        constraints=parse_constraints(raw.get("constraints")),
    )


def _convert_response(raw: dict[str, Any]) -> Response:
    return Response(
        status=int(raw.get("status", 200) or 200),
        error_code=raw.get("error_code"),
        condition=raw.get("description") or raw.get("condition"),
    )


def _convert_rule(raw: dict[str, Any]) -> Rule:
    return Rule(
        id=str(raw.get("id", "")),
        text=str(raw.get("text", "")),
        source=raw.get("source"),
    )


def convert(data: Any) -> CanonicalSpec:
    if not isinstance(data, dict):
        raise ValueError("spec JSON phải là một object")

    project = Project.from_dict(data.get("project"))

    legacy_modules = data.get("modules")
    if not isinstance(legacy_modules, list) or not legacy_modules:
        raise ValueError("spec thiếu mảng 'modules' hoặc rỗng")

    auth_global = Auth.from_dict(data.get("auth_global"))

    modules: list[Module] = []
    for m_index, legacy_module in enumerate(legacy_modules):
        if not isinstance(legacy_module, dict):
            continue

        module_name = str(legacy_module.get("module_name") or legacy_module.get("name") or "")
        base_sheet = str(legacy_module.get("sheet_name") or "").strip()
        methods = legacy_module.get("methods") or []

        module = Module(
            id=str(legacy_module.get("id") or f"mod-{m_index + 1:03d}"),
            module_name=module_name,
            sheet_name=base_sheet,
            kind=str(legacy_module.get("kind", "http")),
            description=str(legacy_module.get("description", "")),
            pre_condition=str(legacy_module.get("pre_condition", "")),
            source_doc=str(legacy_module.get("source_doc", "")),
        )

        if not isinstance(methods, list) or not methods:
            modules.append(module)
            continue

        # Mỗi method có `api` -> 1 sheet riêng (1 API = 1 sheet).
        multi_api = sum(1 for meth in methods if isinstance(meth, dict) and meth.get("api")) > 1

        for e_index, method in enumerate(methods):
            if not isinstance(method, dict):
                continue
            api = method.get("api")
            if not isinstance(api, dict):
                # Hàm thường không có block api: vẫn tạo endpoint kind=function.
                endpoint = Endpoint(
                    id=_endpoint_id(m_index, e_index),
                    kind="function",
                    http_method="CALL",
                    path=str(method.get("name", "")),
                    summary=str(method.get("name", "")),
                    auth=Auth(type="none"),
                )
            else:
                endpoint = Endpoint(
                    id=_endpoint_id(m_index, e_index),
                    kind="http",
                    http_method=str(api.get("http_method", "GET")).upper(),
                    path=str(api.get("path", "")),
                    summary=str(api.get("summary", "")),
                    auth=_normalise_auth(api.get("auth")),
                    params=[
                        _convert_param(p)
                        for p in api.get("request", [])
                        if isinstance(p, dict)
                    ],
                    responses=[
                        _convert_response(r)
                        for r in api.get("responses", [])
                        if isinstance(r, dict)
                    ],
                    rules=[
                        _convert_rule(r)
                        for r in api.get("rules", [])
                        if isinstance(r, dict)
                    ],
                )
                if not module.source_doc:
                    module.source_doc = str(api.get("source", ""))

            if multi_api:
                sheet = _method_to_sheet_name(method, module_name)
                if not module.sheet_name:
                    module.sheet_name = sheet
                # Nhiều API trong 1 module cũ -> tách thành module riêng, 1 API 1 sheet.
                split = Module(
                    id=f"{module.id}-{e_index + 1:02d}",
                    module_name=module_name,
                    sheet_name=sheet,
                    kind=module.kind,
                    description=module.description,
                    pre_condition=module.pre_condition,
                    source_doc=module.source_doc,
                    endpoints=[endpoint],
                )
                apply_inferred_flags(split)
                modules.append(split)
            else:
                module.endpoints.append(endpoint)

        if not multi_api:
            if not module.sheet_name:
                label = module_name or module.id
                first_ep = module.endpoints[0] if module.endpoints else None
                if first_ep:
                    module.sheet_name = _method_to_sheet_name(
                        {"name": first_ep.path, "api": first_ep.to_dict()}, label
                    )
                else:
                    module.sheet_name = _slug(label)[:31] or "Sheet"
            apply_inferred_flags(module)
            modules.append(module)

    return CanonicalSpec(
        project=project,
        auth_global=auth_global,
        modules=modules,
    )
