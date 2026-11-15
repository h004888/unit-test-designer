"""utd.canonical - Canonical IR 2.0 và validator.

Mọi adapter ingest phải sinh ra đúng một hình dạng dữ liệu (Canonical IR).
Các stage sau chỉ đọc hình dạng này, không đọc lại định dạng nguồn.

Ràng buộc cốt lõi:
  - `constraints` là đối tượng có cấu trúc {min, max, pattern, enum}, không
    phải chuỗi mô tả. Không stage nào phải parse chuỗi để tìm biên.
  - `flags` có 6 khoá; mỗi khoá mang nhãn nguồn gốc: `inferred` (máy suy),
    `user` (người dùng xác nhận), hoặc `default` (mặc định chưa hỏi).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_VERSION = "2.0"

FLAG_NAMES = (
    "has_status_field",
    "has_quota",
    "has_dependencies",
    "is_multi_tenant",
    "has_unique_field",
    "has_currency",
)

# Ba cờ được phép suy tự động từ dữ liệu spec (nhãn `inferred`).
INFERABLE_FLAGS = ("has_status_field", "is_multi_tenant", "has_currency")

# Ba cờ còn lại bắt buộc hỏi người dùng (nhãn `user` sau khi xác nhận).
USER_ONLY_FLAGS = ("has_quota", "has_dependencies", "has_unique_field")

FLAG_SOURCES = ("inferred", "user", "default")

VALID_PARAM_LOCATIONS = ("body", "query", "path", "header", "formData")
VALID_MODULE_KINDS = ("http", "function")
VALID_ENDPOINT_KINDS = ("http", "function")
VALID_TEST_TYPES = ("Normal", "Abnormal", "Boundary")


@dataclass
class Constraints:
    min: Any = None
    max: Any = None
    pattern: str | None = None
    enum: list[Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": self.min,
            "max": self.max,
            "pattern": self.pattern,
            "enum": self.enum,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Constraints":
        if not isinstance(data, dict):
            return cls()
        return cls(
            min=data.get("min"),
            max=data.get("max"),
            pattern=data.get("pattern"),
            enum=data.get("enum"),
        )

    def is_empty(self) -> bool:
        return self.min is None and self.max is None and self.pattern is None and self.enum is None

    def has_bounds(self) -> bool:
        return isinstance(self.min, (int, float)) and isinstance(self.max, (int, float))


@dataclass
class Param:
    name: str = ""
    in_: str = "body"
    type: str = "string"
    required: bool = False
    format: str | None = None
    enum: list[Any] | None = None
    default: Any = None
    constraints: Constraints = field(default_factory=Constraints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "in": self.in_,
            "type": self.type,
            "required": self.required,
            "format": self.format,
            "enum": self.enum,
            "default": self.default,
            "constraints": self.constraints.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Param":
        return cls(
            name=str(data.get("name", "")),
            in_=str(data.get("in", "body")),
            type=str(data.get("type", "string")),
            required=bool(data.get("required", False)),
            format=data.get("format"),
            enum=data.get("enum") if isinstance(data.get("enum"), list) else data.get("enum"),
            default=data.get("default"),
            constraints=Constraints.from_dict(data.get("constraints")),
        )


@dataclass
class Auth:
    type: str = "none"
    roles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "roles": self.roles}

    @classmethod
    def from_dict(cls, data: Any) -> "Auth":
        if isinstance(data, str):
            return cls(type=data or "none")
        if not isinstance(data, dict):
            return cls()
        roles = data.get("roles") or []
        if isinstance(roles, str):
            roles = [roles]
        return cls(type=str(data.get("type", "none")), roles=list(roles))

    def is_protected(self) -> bool:
        return self.type not in ("", "none", "public")


@dataclass
class Response:
    status: int = 200
    error_code: str | None = None
    condition: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "condition": self.condition,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Response":
        status = data.get("status", 200)
        try:
            status_int = int(status)
        except (TypeError, ValueError):
            status_int = 200
        return cls(
            status=status_int,
            error_code=data.get("error_code"),
            condition=data.get("condition"),
        )


@dataclass
class Rule:
    id: str = ""
    text: str = ""
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "source": self.source}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            id=str(data.get("id", "")),
            text=str(data.get("text", "")),
            source=data.get("source"),
        )


@dataclass
class Endpoint:
    id: str = ""
    http_method: str = "GET"
    path: str = ""
    kind: str = "http"
    summary: str = ""
    auth: Auth = field(default_factory=Auth)
    params: list[Param] = field(default_factory=list)
    responses: list[Response] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "http_method": self.http_method,
            "path": self.path,
            "kind": self.kind,
            "summary": self.summary,
            "auth": self.auth.to_dict(),
            "params": [p.to_dict() for p in self.params],
            "responses": [r.to_dict() for r in self.responses],
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Endpoint":
        return cls(
            id=str(data.get("id", "")),
            http_method=str(data.get("http_method", "GET")).upper(),
            path=str(data.get("path", "")),
            kind=str(data.get("kind", "http")),
            summary=str(data.get("summary", "")),
            auth=Auth.from_dict(data.get("auth")),
            params=[Param.from_dict(p) for p in data.get("params", []) if isinstance(p, dict)],
            responses=[
                Response.from_dict(r) for r in data.get("responses", []) if isinstance(r, dict)
            ],
            rules=[Rule.from_dict(r) for r in data.get("rules", []) if isinstance(r, dict)],
        )


@dataclass
class Flags:
    values: dict[str, bool] = field(default_factory=dict)
    sources: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in FLAG_NAMES:
            self.values.setdefault(name, False)
            self.sources.setdefault(name, "default")

    def set(self, name: str, value: bool, source: str = "inferred") -> None:
        if name not in FLAG_NAMES:
            raise ValueError(f"Cờ không hợp lệ: {name}")
        if source not in FLAG_SOURCES:
            raise ValueError(f"Nguồn cờ không hợp lệ: {source}")
        self.values[name] = bool(value)
        self.sources[name] = source

    def get(self, name: str) -> bool:
        return bool(self.values.get(name, False))

    def source(self, name: str) -> str:
        return self.sources.get(name, "default")

    def pending_user_confirmation(self) -> list[str]:
        """Cờ chưa được người dùng xác nhận (nguồn khác `user`)."""
        return [n for n in FLAG_NAMES if self.sources.get(n) != "user"]

    def to_dict(self) -> dict[str, Any]:
        return {"values": dict(self.values), "sources": dict(self.sources)}

    @classmethod
    def from_dict(cls, data: Any) -> "Flags":
        if isinstance(data, dict) and "values" in data:
            flags = cls()
            for name, value in (data.get("values") or {}).items():
                flags.values[name] = bool(value)
            for name, src in (data.get("sources") or {}).items():
                flags.sources[name] = str(src)
            return flags
        flags = cls()
        if isinstance(data, dict):
            # Hình dạng phẳng: {"has_currency": true, ...}
            for name, value in data.items():
                if name in FLAG_NAMES:
                    flags.values[name] = bool(value)
        return flags


@dataclass
class Module:
    id: str = ""
    module_name: str = ""
    sheet_name: str = ""
    kind: str = "http"
    description: str = ""
    pre_condition: str = ""
    source_doc: str = ""
    flags: Flags = field(default_factory=Flags)
    endpoints: list[Endpoint] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "module_name": self.module_name,
            "sheet_name": self.sheet_name,
            "kind": self.kind,
            "description": self.description,
            "pre_condition": self.pre_condition,
            "source_doc": self.source_doc,
            "flags": self.flags.to_dict(),
            "endpoints": [e.to_dict() for e in self.endpoints],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Module":
        return cls(
            id=str(data.get("id", "")),
            module_name=str(data.get("module_name", "")),
            sheet_name=str(data.get("sheet_name", "")),
            kind=str(data.get("kind", "http")),
            description=str(data.get("description", "")),
            pre_condition=str(data.get("pre_condition", "")),
            source_doc=str(data.get("source_doc", "")),
            flags=Flags.from_dict(data.get("flags")),
            endpoints=[
                Endpoint.from_dict(e) for e in data.get("endpoints", []) if isinstance(e, dict)
            ],
        )


@dataclass
class Project:
    name: str = ""
    code: str = ""
    creator: str = ""
    reviewer: str = ""
    version: str = "v1.0"
    issue_date: str = ""
    reference: str = ""
    environment: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "code": self.code,
            "creator": self.creator,
            "reviewer": self.reviewer,
            "version": self.version,
            "issue_date": self.issue_date,
            "reference": self.reference,
            "environment": self.environment,
        }

    @classmethod
    def from_dict(cls, data: Any) -> "Project":
        if not isinstance(data, dict):
            return cls()
        return cls(
            name=str(data.get("name", "")),
            code=str(data.get("code", "")),
            creator=str(data.get("creator", "")),
            reviewer=str(data.get("reviewer", "")),
            version=str(data.get("version", "v1.0")),
            issue_date=str(data.get("issue_date", "")),
            reference=str(data.get("reference", "")),
            environment=str(data.get("environment", "")),
        )


@dataclass
class CanonicalSpec:
    schema_version: str = SCHEMA_VERSION
    project: Project = field(default_factory=Project)
    auth_global: Auth = field(default_factory=Auth)
    modules: list[Module] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project": self.project.to_dict(),
            "auth_global": self.auth_global.to_dict(),
            "modules": [m.to_dict() for m in self.modules],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "CanonicalSpec":
        if not isinstance(data, dict):
            return cls()
        return cls(
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            project=Project.from_dict(data.get("project")),
            auth_global=Auth.from_dict(data.get("auth_global")),
            modules=[Module.from_dict(m) for m in data.get("modules", []) if isinstance(m, dict)],
        )

    def endpoint_count(self) -> int:
        return sum(len(m.endpoints) for m in self.modules)


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    missing_info: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.missing_info

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def add_missing(self, message: str) -> None:
        self.missing_info.append(message)


def validate(spec: CanonicalSpec) -> ValidationResult:
    """Kiểm tra cấu trúc Canonical IR.

    `errors`   -> exit 2 (đầu vào không hợp lệ về cấu trúc)
    `missing_info` -> exit 3 (hợp lệ nhưng thiếu thông tin không suy được)
    """
    result = ValidationResult()

    if spec.schema_version != SCHEMA_VERSION:
        result.add_error(
            f"schema_version phải là '{SCHEMA_VERSION}', nhận '{spec.schema_version}'"
        )

    if not spec.modules:
        result.add_error("spec không có module nào (modules rỗng)")
        return result

    seen_module_ids: set[str] = set()
    seen_sheet_names: set[str] = set()

    for idx, module in enumerate(spec.modules):
        label = module.module_name or module.id or f"modules[{idx}]"

        if not module.sheet_name.strip():
            result.add_error(f"[{label}] thiếu 'sheet_name'")
        elif module.sheet_name in seen_sheet_names:
            result.add_error(f"[{label}] 'sheet_name' trùng: {module.sheet_name}")
        else:
            seen_sheet_names.add(module.sheet_name)

        if module.id:
            if module.id in seen_module_ids:
                result.add_error(f"[{label}] 'id' module trùng: {module.id}")
            seen_module_ids.add(module.id)

        if module.kind not in VALID_MODULE_KINDS:
            result.add_error(f"[{label}] 'kind' module không hợp lệ: {module.kind}")

        if not module.endpoints:
            result.add_error(f"[{label}] không có endpoint nào")

        for j, endpoint in enumerate(module.endpoints):
            ep_label = f"[{label} :: {endpoint.id or f'endpoints[{j}]'}]"

            if endpoint.kind not in VALID_ENDPOINT_KINDS:
                result.add_error(f"{ep_label} 'kind' không hợp lệ: {endpoint.kind}")

            if endpoint.kind == "http":
                if not endpoint.path.strip():
                    result.add_error(f"{ep_label} endpoint HTTP thiếu 'path'")
                if endpoint.http_method not in (
                    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"
                ):
                    result.add_error(
                        f"{ep_label} 'http_method' không hợp lệ: {endpoint.http_method}"
                    )

            seen_param_names: set[tuple[str, str]] = set()
            for k, param in enumerate(endpoint.params):
                p_label = f"{ep_label} params[{k}]"
                if not param.name.strip():
                    result.add_error(f"{p_label} thiếu 'name'")
                    continue
                key = (param.name, param.in_)
                if key in seen_param_names:
                    result.add_error(
                        f"{p_label} tham số trùng: {param.name} (in={param.in_})"
                    )
                seen_param_names.add(key)

                if param.in_ not in VALID_PARAM_LOCATIONS:
                    result.add_error(f"{p_label} 'in' không hợp lệ: {param.in_}")

                bounds = param.constraints.has_bounds()
                if bounds and param.constraints.min > param.constraints.max:
                    result.add_error(
                        f"{p_label} constraints.min ({param.constraints.min}) "
                        f"lớn hơn constraints.max ({param.constraints.max})"
                    )

                if param.required and param.constraints.is_empty() and param.type in (
                    "string", "integer", "number"
                ):
                    result.add_missing(
                        f"{p_label} tham số required '{param.name}' chưa có ràng buộc "
                        f"(min/max/pattern/enum) — cần hỏi người dùng"
                    )

    return result


def parse(data: Any) -> CanonicalSpec:
    return CanonicalSpec.from_dict(data)


def dump(spec: CanonicalSpec) -> dict[str, Any]:
    return spec.to_dict()
