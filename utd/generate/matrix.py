"""utd.generate.matrix - Sinh test case cho MỌI module từ SSOT đã khoá.

Bản cũ chỉ đọc `modules[0].methods[0]` nên spec 2 module chỉ sinh 1. Đây là
bug nghiêm trọng đã được sửa: vòng lặp chạy qua toàn bộ `modules[]` và
`endpoints[]`.

Đầu ra tuân thủ schema cũ (`build_unit_test_doc.py` dùng) để emit không phải
viết lại: `modules[].methods[].test_cases[]` với expected là dict 3 khoá.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import CanonicalSpec, Endpoint, Module, Param
from .budget import (
    ABNORMAL,
    BOUNDARY,
    NORMAL,
    Budget,
    Slot,
    calculate_budget,
    calculate_budgets,
)
from .data import (
    DataProvider,
    DataUnavailableError,
    infer_category,
    is_slop,
    mutate,
    normalize_case,
)


class GenerateError(Exception):
    """Không thể sinh bộ test case hợp lệ."""

    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class GeneratedCase:
    pre: str
    input: str
    expected: dict[str, str]
    type: str
    rule_refs: list[str]
    note: str
    id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "pre": self.pre,
            "input": self.input,
            "expected": self.expected,
            "type": self.type,
            "rule_refs": self.rule_refs,
            "note": self.note,
        }
        if self.id:
            data["id"] = self.id
        return data


def _base_input(endpoint: Endpoint, provider: DataProvider, locale: str = "vi",
                seed: int | None = None) -> dict[str, str]:
    """Dựng input hợp lệ cho mọi tham số required."""
    values: dict[str, str] = {}
    for param in endpoint.params:
        if not param.required:
            continue
        label = f"header.{param.name}" if param.in_ == "header" else (
            f"body.{param.name}" if param.in_ == "body" else param.name
        )

        if "authorization" in param.name.lower():
            values[label] = "Bearer <valid>"
            continue

        # Kiểu số: sinh số trong dải biên. Với tham số định danh (id/uuid)
        # dùng số có ý nghĩa hơn "1" để không vi phạm G9.
        if param.type == "integer":
            if param.constraints.has_bounds():
                lowest = int(param.constraints.min)
                highest = int(param.constraints.max)
                middle = (lowest + highest) // 2
            elif param.constraints.enum:
                middle = int(param.constraints.enum[0])
            else:
                middle = 4021 if "id" in param.name.lower() else 7
            values[label] = str(middle)
            continue
        if param.type == "number":
            if param.constraints.has_bounds():
                lowest = param.constraints.min
                highest = param.constraints.max
                values[label] = str((lowest + highest) / 2)
            elif param.constraints.enum:
                values[label] = str(param.constraints.enum[0])
            else:
                values[label] = "7.5"
            continue
        if param.type == "boolean":
            values[label] = "true"
            continue
        if param.constraints.enum:
            values[label] = str(param.constraints.enum[0])
            continue

        category = infer_category(param.name, param.type)
        if category:
            try:
                real = provider.get(category=category, locale=locale, count=1)
                values[label] = normalize_case(real[0])
                continue
            except DataUnavailableError as exc:
                raise GenerateError(
                    f"Không có dữ liệu thật cho tham số '{param.name}': {exc}"
                ) from exc

        if param.type == "array":
            filler = provider.get(category="name", locale=locale, count=1)[0]
            values[label] = f"[{normalize_case(filler)}]"
            continue

        # Còn lại: dùng dữ liệu thật. Placeholder '<param>' bị G9 coi là slop.
        try:
            values[label] = normalize_case(
                provider.get(category="name", locale=locale, count=1)[0]
            )
        except DataUnavailableError as exc:
            raise GenerateError(
                f"Không có dữ liệu thật cho tham số '{param.name}': {exc}"
            ) from exc
    return values


def _format_input(values: dict[str, str], override: tuple[str, str] | None = None,
                  drop: str | None = None) -> str:
    parts: list[str] = []
    for key, value in values.items():
        if drop and key.endswith(drop):
            continue
        parts.append(f"{key}={value}")
    if override:
        parts.append(f"{override[0]}={override[1]}")
    return "; ".join(parts)


def _expected_for(slot: Slot, endpoint: Endpoint) -> dict[str, str]:
    if slot.type == NORMAL:
        success = next(
            (r for r in endpoint.responses if 200 <= r.status < 300),
            None,
        )
        status = success.status if success else 200
        code = success.error_code if success else None
        return {
            "return": f"HTTP {status}; body trả về theo đặc tả",
            "exception": code or "N/A",
            "log": f"{slot.note} | rule: {', '.join(slot.rule_refs) or 'N/A'}",
        }

    if slot.type == BOUNDARY:
        return {
            "return": "HTTP 200; giá trị biên được chấp nhận",
            "exception": "N/A",
            "log": f"biên hợp lệ: {slot.technique}",
        }

    failure = next((r for r in endpoint.responses if 400 <= r.status < 500), None)
    status = failure.status if failure else 400
    error_code = failure.error_code if failure else "INVALID_INPUT"
    return {
        "return": f"HTTP {status}; body {{\"error\":\"{error_code}\"}}",
        "exception": error_code,
        "log": f"{slot.technique}",
    }


def generate_for_endpoint(module: Module, endpoint: Endpoint,
                          provider: DataProvider) -> list[GeneratedCase]:
    budget = calculate_budget(module, endpoint)
    base_values = _base_input(endpoint, provider)
    cases: list[GeneratedCase] = []

    for slot in budget.slots:
        param_name = slot.param_name

        if slot.type == NORMAL and slot.target == "endpoint:happy_path":
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền hợp lệ cho {endpoint.path}",
                    input=_format_input(base_values),
                    expected=_expected_for(slot, endpoint),
                    type=NORMAL,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_HappyPath_ReturnsSuccess | EP: happy path",
                )
            )
            continue

        if param_name and slot.param_value is not None:
            # Thay giá trị tham số này bằng giá trị của slot
            label = f"header.{param_name}" if any(
                p.name == param_name and p.in_ == "header" for p in endpoint.params
            ) else (
                f"body.{param_name}"
                if any(p.name == param_name and p.in_ == "body" for p in endpoint.params)
                else param_name
            )
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền hợp lệ cho {endpoint.path}",
                    input=_format_input(base_values, override=(label, str(slot.param_value))),
                    expected=_expected_for(slot, endpoint),
                    type=slot.type,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_{param_name}_{slot.type} | {slot.technique}",
                )
            )
            continue

        if slot.target == "endpoint:auth":
            cases.append(
                GeneratedCase(
                    pre="người dùng chưa đăng nhập",
                    input=_format_input(base_values, drop="Authorization"),
                    expected={
                        "return": 'HTTP 401; body {"error":"UNAUTHORIZED"}',
                        "exception": "UNAUTHORIZED",
                        "log": "Missing Authorization header",
                    },
                    type=ABNORMAL,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_MissingAuth_Returns401 | Security: missing token",
                )
            )
            continue

        if slot.target.startswith("missing:"):
            param_name = slot.target.split(":", 1)[1]
            label_prefix = "header." if any(
                p.name == param_name and p.in_ == "header" for p in endpoint.params
            ) else ("body." if any(
                p.name == param_name and p.in_ == "body" for p in endpoint.params
            ) else "")
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền hợp lệ cho {endpoint.path}",
                    input=_format_input(base_values, drop=label_prefix + param_name),
                    expected=_expected_for(slot, endpoint),
                    type=ABNORMAL,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_{param_name}_Missing | EP: missing required",
                )
            )
            continue

        if slot.target.startswith("null:"):
            param_name = slot.target.split(":", 1)[1]
            label = f"header.{param_name}" if any(
                p.name == param_name and p.in_ == "header" for p in endpoint.params
            ) else (
                f"body.{param_name}"
                if any(p.name == param_name and p.in_ == "body" for p in endpoint.params)
                else param_name
            )
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền hợp lệ cho {endpoint.path}",
                    input=_format_input(base_values, override=(label, "null")),
                    expected=_expected_for(slot, endpoint),
                    type=ABNORMAL,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_{param_name}_Null | EP: null required",
                )
            )
            continue

        if slot.target.startswith("status:"):
            status_text = slot.target.split(":", 1)[1]
            response = next(
                (r for r in endpoint.responses if str(r.status) == status_text), None
            )
            error_code = response.error_code if response else "ERROR"
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền kích hoạt HTTP {status_text}",
                    input=_format_input(base_values),
                    expected={
                        "return": f'HTTP {status_text}; body {{"error":"{error_code}"}}',
                        "exception": error_code or "N/A",
                        "log": slot.note,
                    },
                    type=ABNORMAL,
                    rule_refs=slot.rule_refs,
                    note=f"{module.sheet_name}_Status{status_text} | HTTP {status_text}",
                )
            )
            continue

        if slot.target.startswith("rule:"):
            rule_id = slot.target.split(":", 1)[1]
            cases.append(
                GeneratedCase(
                    pre=f"dữ liệu nền hợp lệ cho {endpoint.path}",
                    input=_format_input(base_values),
                    expected=_expected_for(slot, endpoint),
                    type=slot.type,
                    rule_refs=[rule_id],
                    note=f"{module.sheet_name}_{rule_id}_{slot.type} | {slot.technique[:80]}",
                )
            )
            continue

    if not any(case.type == NORMAL for case in cases):
        raise GenerateError(
            f"Module '{module.sheet_name}' không sinh được test case Normal nào"
        )

    return cases


def build_ssot(spec: CanonicalSpec, provider: DataProvider | None = None,
               project: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sinh SSOT cho MỌI module. Trả payload đúng schema emit dùng."""
    if provider is None:
        provider = DataProvider.load()

    modules_payload: list[dict[str, Any]] = []
    normal_sheets: list[str] = []
    uncovered: dict[str, list[str]] = {}

    budgets = calculate_budgets(spec.modules)

    for module in spec.modules:
        if not module.endpoints:
            raise GenerateError(
                f"Module '{module.sheet_name or module.id}' không có endpoint nào"
            )

        methods_payload: list[dict[str, Any]] = []
        module_cases = 0
        module_normal = 0

        for endpoint in module.endpoints:
            cases = generate_for_endpoint(module, endpoint, provider)
            module_cases += len(cases)
            module_normal += sum(1 for c in cases if c.type == NORMAL)

            # Kiểm tra slop
            for case in cases:
                if is_slop(case.input):
                    raise GenerateError(
                        f"Test case sinh ra chứa dữ liệu rác: '{case.input[:60]}'"
                    )

            methods_payload.append(
                {
                    "name": endpoint.summary or endpoint.id or endpoint.path,
                    "endpoint_id": endpoint.id,
                    "api": {
                        "http_method": endpoint.http_method,
                        "path": endpoint.path,
                        "summary": endpoint.summary,
                        "source": module.source_doc,
                        "auth": endpoint.auth.type,
                        "request": [p.to_dict() for p in endpoint.params],
                        "responses": [r.to_dict() for r in endpoint.responses],
                        "rules": [r.to_dict() for r in endpoint.rules],
                    },
                    "test_cases": [c.to_dict() for c in cases],
                }
            )

            # Truy vết rule
            for rule in endpoint.rules:
                covered = any(rule.id in c.rule_refs for c in cases)
                if not covered:
                    uncovered.setdefault(module.sheet_name, []).append(rule.id)

        if module_normal == 0:
            raise GenerateError(
                f"Module '{module.sheet_name}' không có test case Normal (Normal == 0)"
            )

        normal_sheets.append(module.sheet_name)

        modules_payload.append(
            {
                "module_name": module.module_name,
                "sheet_name": module.sheet_name,
                "description": module.description,
                "pre_condition": module.pre_condition,
                "methods": methods_payload,
            }
        )

    uncovered_flat = [
        f"{sheet}:{rule_id}"
        for sheet, rule_ids in uncovered.items()
        for rule_id in rule_ids
    ]

    return {
        "project": project or spec.project.to_dict(),
        "stats_round": 3,
        "modules": modules_payload,
        "uncovered_rules": uncovered_flat,
        "zero_normal_sheets": [],
        "budgets": [b.to_dict() for b in budgets],
        "meta": {
            "generated_modules": len(modules_payload),
            "total_cases": sum(
                len(m["test_cases"])
                for module in modules_payload
                for m in module["methods"]
            ),
            "total_rules": sum(
                len(e.rules) for m in spec.modules for e in m.endpoints
            ),
        },
    }


def merge_module(ssot: dict[str, Any], new_module: dict[str, Any]) -> dict[str, Any]:
    """Cộng dồn module mới, giữ nguyên module cũ và mã UTC đã cấp."""
    sheet = new_module.get("sheet_name")
    existing = {m["sheet_name"] for m in ssot.get("modules", [])}
    if sheet in existing:
        raise GenerateError(
            f"sheet_name '{sheet}' đã tồn tại — chọn tên khác để tránh ghi đè"
        )
    ssot.setdefault("modules", []).append(new_module)
    return ssot
