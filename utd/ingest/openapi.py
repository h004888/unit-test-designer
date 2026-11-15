"""Adapter `openapi`: OpenAPI 3.x -> Canonical IR.

Quy tắc ánh xạ:
  paths[path][method]            -> Endpoint(http_method, path)
  parameters (in: query/path/header) -> Param
  requestBody.content[*/json].schema -> params cho từng property (in: body)
  responses[status]              -> Response(status, condition=description)
  components.securitySchemes + security -> Auth
  1 path+method                  -> 1 module (1 API = 1 sheet)
"""

from __future__ import annotations

from typing import Any

from ..canonical import (
    Auth,
    CanonicalSpec,
    Constraints,
    Endpoint,
    Module,
    Param,
    Project,
    Response,
    Rule,
)
from .flags import apply_inferred_flags

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")

TYPE_MAP = {
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "array": "array",
    "object": "object",
    "string": "string",
}


def _sheet_name(method: str, path: str) -> str:
    flat = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    flat = flat.replace("-", "_")
    return f"{method.upper()}_{flat}"[:31] or "Sheet"


def _auth_from(api_spec: dict[str, Any], security: Any) -> Auth:
    if not security:
        return Auth(type="none", roles=[])
    schemes = (api_spec.get("components") or {}).get("securitySchemes") or {}

    for requirement in security if isinstance(security, list) else []:
        for name, scopes in (requirement or {}).items():
            scheme = schemes.get(name) or {}
            scheme_type = str(scheme.get("type", "")).lower()
            if scheme_type == "oauth2":
                return Auth(type="oauth", roles=list(scopes or []))
            if scheme_type == "http" and str(scheme.get("scheme", "")).lower() == "bearer":
                return Auth(type="jwt", roles=list(scopes or []))
            if scheme_type == "apiKey":
                return Auth(type="api_key", roles=list(scopes or []))
            return Auth(type="other", roles=list(scopes or []))
    return Auth(type="other", roles=[])


def _constraints_from_schema(schema: dict[str, Any]) -> Constraints:
    enum = schema.get("enum") if isinstance(schema.get("enum"), list) else None
    pattern = schema.get("pattern")
    min_value = schema.get("minimum")
    max_value = schema.get("maximum")
    if min_value is None and isinstance(schema.get("minLength"), int):
        min_value = schema["minLength"]
    if max_value is None and isinstance(schema.get("maxLength"), int):
        max_value = schema["maxLength"]
    if min_value is None and isinstance(schema.get("minItems"), int):
        min_value = schema["minItems"]
    if max_value is None and isinstance(schema.get("maxItems"), int):
        max_value = schema["maxItems"]
    return Constraints(min=min_value, max=max_value, pattern=pattern, enum=enum)


def _param_from_schema(name: str, schema: dict[str, Any], location: str,
                       required: bool) -> Param:
    raw_type = schema.get("type", "string")
    return Param(
        name=name,
        in_=location,
        type=TYPE_MAP.get(str(raw_type), "string"),
        required=required,
        format=schema.get("format"),
        enum=schema.get("enum") if isinstance(schema.get("enum"), list) else None,
        default=schema.get("default"),
        constraints=_constraints_from_schema(schema),
    )


def _resolve_ref(api_spec: dict[str, Any], node: Any) -> Any:
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    pointer: Any = api_spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(pointer, dict) or part not in pointer:
            return node
        pointer = pointer[part]
    return pointer


def _params_from_operation(api_spec: dict[str, Any], operation: dict[str, Any]) -> list[Param]:
    params: list[Param] = []

    for raw in operation.get("parameters") or []:
        raw = _resolve_ref(api_spec, raw)
        if not isinstance(raw, dict):
            continue
        schema = _resolve_ref(api_spec, raw.get("schema") or {})
        if not isinstance(schema, dict):
            schema = {}
        params.append(
            _param_from_schema(
                str(raw.get("name", "")),
                schema,
                str(raw.get("in", "query")),
                bool(raw.get("required", False)),
            )
        )

    body = operation.get("requestBody")
    if isinstance(body, dict):
        body = _resolve_ref(api_spec, body)
        content = (body.get("content") or {})
        json_content = content.get("application/json") or next(
            (v for k, v in content.items() if "json" in k), None
        )
        if isinstance(json_content, dict):
            schema = _resolve_ref(api_spec, json_content.get("schema") or {})
            if isinstance(schema, dict):
                properties = schema.get("properties") or {}
                required_list = schema.get("required") or []
                for prop_name, prop_schema in properties.items():
                    prop_schema = _resolve_ref(api_spec, prop_schema)
                    if not isinstance(prop_schema, dict):
                        prop_schema = {}
                    params.append(
                        _param_from_schema(
                            str(prop_name),
                            prop_schema,
                            "body",
                            bool(body.get("required", False)) and prop_name in required_list
                            or prop_name in required_list,
                        )
                    )

    return params


def _responses_from_operation(api_spec: dict[str, Any], operation: dict[str, Any]) -> list[Response]:
    responses: list[Response] = []
    for status, raw in (operation.get("responses") or {}).items():
        raw = _resolve_ref(api_spec, raw)
        if not isinstance(raw, dict):
            raw = {}
        try:
            status_int = int(str(status))
        except ValueError:
            status_int = 200 if str(status).lower() == "default" else 200
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
    raw_rules = operation.get("x-business-rules") or []
    if isinstance(raw_rules, list):
        for raw in raw_rules:
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
        raise ValueError("OpenAPI document phải là một object")

    if "openapi" not in data:
        raise ValueError("thiếu trường 'openapi' — không phải OpenAPI 3.x")
    if not str(data.get("openapi", "")).startswith("3."):
        raise ValueError(f"phiên bản OpenAPI không hỗ trợ: {data.get('openapi')}")

    info = data.get("info") or {}
    project = Project(
        name=str(info.get("title", "")),
        code=str(info.get("x-project-code", "")),
        version=str(info.get("version", "v1.0")),
        issue_date=str(info.get("x-issue-date", "")),
        environment=str((data.get("servers") or [{}])[0].get("url", "")),
    )

    paths = data.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise ValueError("OpenAPI document không có 'paths' hoặc rỗng")

    modules: list[Module] = []
    counter = 0

    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_item = _resolve_ref(data, path_item)
        for method in HTTP_METHODS:
            operation = path_item.get(method)
            if not isinstance(operation, dict):
                continue
            operation = _resolve_ref(data, operation)
            counter += 1

            endpoint = Endpoint(
                id=f"ep-{counter:03d}",
                http_method=method.upper(),
                path=str(path),
                kind="http",
                summary=str(operation.get("summary", "")),
                auth=_auth_from(data, operation.get("security", data.get("security"))),
                params=_params_from_operation(data, operation),
                responses=_responses_from_operation(data, operation),
                rules=_rules_from_operation(operation),
            )

            module = Module(
                id=f"mod-{counter:03d}",
                module_name=str(operation.get("summary", "") or f"{method.upper()} {path}"),
                sheet_name=_sheet_name(method, path),
                kind="http",
                description=str(operation.get("description", "")),
                source_doc=f"OpenAPI {path} [{method.upper()}]",
                endpoints=[endpoint],
            )
            apply_inferred_flags(module)
            modules.append(module)

    return CanonicalSpec(project=project, modules=modules)
