"""Adapter `swagger`: Swagger 2.0 -> Canonical IR.

Swagger 2.0 khác OpenAPI 3.x ở các điểm:
  - `definitions` thay cho `components.schemas`
  - `parameters` + `body` parameter thay cho `requestBody`
  - `securityDefinitions` thay cho `securitySchemes`
  - `consumes` / `produces` ở cấp operation
"""

from __future__ import annotations

from typing import Any

from ..canonical import Auth, CanonicalSpec, Endpoint, Module, Param, Project, Response, Rule
from .flags import apply_inferred_flags
from .openapi import (
    HTTP_METHODS,
    _constraints_from_schema,
    _param_from_schema,
    _sheet_name,
    _resolve_ref as _resolve_in,
)


def _resolve(document: dict[str, Any], node: Any) -> Any:
    """`$ref` trong Swagger 2.0 trỏ tới `#/definitions/...`."""
    return _resolve_in(document, node)


def _auth_from(document: dict[str, Any], security: Any) -> Auth:
    if not security:
        return Auth(type="none", roles=[])
    definitions = document.get("securityDefinitions") or {}
    for requirement in security if isinstance(security, list) else []:
        for name, scopes in (requirement or {}).items():
            definition = definitions.get(name) or {}
            scheme_type = str(definition.get("type", "")).lower()
            if scheme_type == "oauth2":
                return Auth(type="oauth", roles=list(scopes or []))
            if scheme_type == "apiKey":
                return Auth(type="api_key", roles=list(scopes or []))
            if scheme_type == "basic":
                return Auth(type="basic", roles=list(scopes or []))
            return Auth(type="other", roles=list(scopes or []))
    return Auth(type="other", roles=[])


def _params_from_operation(document: dict[str, Any],
                           operation: dict[str, Any]) -> list[Param]:
    params: list[Param] = []

    for raw in operation.get("parameters") or []:
        raw = _resolve(document, raw)
        if not isinstance(raw, dict):
            continue
        location = str(raw.get("in", "query"))
        if location == "body":
            schema = _resolve(document, raw.get("schema") or {})
            if not isinstance(schema, dict):
                continue
            properties = schema.get("properties") or {}
            required_list = schema.get("required") or []
            for prop_name, prop_schema in properties.items():
                prop_schema = _resolve(document, prop_schema)
                if not isinstance(prop_schema, dict):
                    prop_schema = {}
                params.append(
                    _param_from_schema(
                        str(prop_name),
                        prop_schema,
                        "body",
                        prop_name in required_list or bool(raw.get("required", False)),
                    )
                )
            continue

        schema = raw.get("schema") if isinstance(raw.get("schema"), dict) else {}
        if not schema:
            # Swagger 2.0 khai trực tiếp trên parameter: {type, format, enum, minimum...}
            schema = {
                k: raw[k]
                for k in ("type", "format", "enum", "minimum", "maximum",
                          "minLength", "maxLength", "pattern", "default")
                if k in raw
            }
        params.append(
            _param_from_schema(
                str(raw.get("name", "")),
                schema,
                location if location in ("query", "path", "header", "formData") else "query",
                bool(raw.get("required", False)),
            )
        )

    return params


def _responses_from_operation(operation: dict[str, Any]) -> list[Response]:
    responses: list[Response] = []
    for status, raw in (operation.get("responses") or {}).items():
        if not isinstance(raw, dict):
            raw = {}
        try:
            status_int = int(str(status))
        except ValueError:
            status_int = 200
        responses.append(
            Response(
                status=status_int,
                error_code=raw.get("x-error-code"),
                condition=str(raw.get("description", "")) or None,
            )
        )
    return responses


def _rules_from_operation(operation: dict[str, Any]) -> list[Rule]:
    rules: list[Rule] = []
    for raw in operation.get("x-business-rules") or []:
        if isinstance(raw, dict):
            rules.append(
                Rule(
                    id=str(raw.get("id", "")),
                    text=str(raw.get("text", "")),
                    source=raw.get("source"),
                )
            )
    return rules


def convert(data: Any) -> CanonicalSpec:
    if not isinstance(data, dict):
        raise ValueError("Swagger document phải là một object")

    if "swagger" not in data:
        raise ValueError("thiếu trường 'swagger' — không phải Swagger 2.0")
    if not str(data.get("swagger", "")).startswith("2."):
        raise ValueError(f"phiên bản Swagger không hỗ trợ: {data.get('swagger')}")

    info = data.get("info") or {}
    project = Project(
        name=str(info.get("title", "")),
        code=str(info.get("x-project-code", "")),
        version=str(info.get("version", "v1.0")),
        issue_date=str(info.get("x-issue-date", "")),
        environment=str(data.get("host", "")),
    )

    paths = data.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("Swagger document không có 'paths' hoặc rỗng")

    modules: list[Module] = []
    counter = 0

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            counter += 1
            endpoint = Endpoint(
                id=f"ep-{counter:03d}",
                http_method=method.upper(),
                path=str(path),
                kind="http",
                summary=str(operation.get("summary", "")),
                auth=_auth_from(data, operation.get("security", data.get("security"))),
                params=_params_from_operation(data, operation),
                responses=_responses_from_operation(operation),
                rules=_rules_from_operation(operation),
            )
            module = Module(
                id=f"mod-{counter:03d}",
                module_name=str(operation.get("summary", "") or f"{method.upper()} {path}"),
                sheet_name=_sheet_name(method, path),
                kind="http",
                description=str(operation.get("description", "")),
                source_doc=f"Swagger {path} [{method.upper()}]",
                endpoints=[endpoint],
            )
            apply_inferred_flags(module)
            modules.append(module)

    return CanonicalSpec(project=project, modules=modules)


__all__ = ["convert", "_constraints_from_schema"]
