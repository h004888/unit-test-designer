"""utd.match.engine - Đánh giá rule trên spec, sinh checklist đã khử trùng lặp.

Luồng:
  1. Nạp toàn bộ rule từ `rules/*.json` (150 rule).
  2. Với mỗi module/endpoint/param, dựng ngữ cảnh và đánh giá `trigger_condition`.
  3. Rule khớp -> sinh câu hỏi, gộp theo (endpoint_id, param_name, rule_id).
  4. Rule không khớp ở bất kỳ đâu -> ghi `skipped_reason`.

Điểm khác biệt so với bản cũ: KHÔNG lọc theo `target_element` bằng if-chain.
Mọi rule đều được đánh giá, nên reachability đạt 150/150.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..canonical import CanonicalSpec, Endpoint, Module, Param
from ..dsl import DSLSyntaxError, evaluate, validate_syntax
from .question_id import build_question_id
from .tier import (
    CRITICAL,
    STANDARD,
    describe_tier_decision,
    determine_tier,
    load_tier_config,
)

from importlib.resources import files as _pkg_files

DEFAULT_RULES_DIR = _pkg_files("utd") / "_data" / "rules"
NONCE_BYTES = 16


@dataclass
class RuleSet:
    rules: list[dict[str, Any]] = field(default_factory=list)
    parse_errors: list[tuple[str, str]] = field(default_factory=list)

    def by_id(self) -> dict[str, dict[str, Any]]:
        return {r["id"]: r for r in self.rules}


def load_rules(rules_dir: str | Path | None = None) -> RuleSet:
    """Nạp mọi rule và validate cú pháp `trigger_condition`."""
    target = Path(rules_dir) if rules_dir else DEFAULT_RULES_DIR
    result = RuleSet()
    for path in sorted(target.glob("*.json"), key=lambda p: p.name):
        data = json.loads(path.read_text(encoding="utf-8"))
        for rule in data.get("rules", []):
            rule = dict(rule)
            rule["_source_file"] = path.name
            try:
                validate_syntax(rule.get("trigger_condition", ""))
            except DSLSyntaxError as exc:
                result.parse_errors.append((rule.get("id", "?"), str(exc)))
                continue
            result.rules.append(rule)
    return result


def build_context(module: Module, endpoint: Endpoint | None,
                  param: Param | None = None) -> dict[str, Any]:
    """Ngữ cảnh đánh giá: endpoint, param, method và 6 cờ module."""
    context: dict[str, Any] = {
        "has_status_field": module.flags.get("has_status_field"),
        "has_quota": module.flags.get("has_quota"),
        "has_dependencies": module.flags.get("has_dependencies"),
        "is_multi_tenant": module.flags.get("is_multi_tenant"),
        "has_unique_field": module.flags.get("has_unique_field"),
        "has_currency": module.flags.get("has_currency"),
        "module": {
            "name": module.module_name,
            "kind": module.kind,
            "sheet_name": module.sheet_name,
        },
    }

    if endpoint is not None:
        context["method"] = endpoint.http_method
        context["endpoint"] = {
            "id": endpoint.id,
            "http_method": endpoint.http_method,
            "path": endpoint.path,
            "kind": endpoint.kind,
            "auth": endpoint.auth.type,
            "roles": endpoint.auth.roles,
            "summary": endpoint.summary,
        }
    else:
        context["method"] = "GET"
        context["endpoint"] = {
            "id": "", "http_method": "GET", "path": "", "kind": "",
            "auth": "none", "roles": [], "summary": "",
        }

    if param is not None:
        context["param"] = {
            "name": param.name,
            "in": param.in_,
            "type": param.type,
            "required": param.required,
            "format": param.format,
            "enum": param.enum,
            "default": param.default,
            "constraints": param.constraints.to_dict(),
        }
    else:
        context["param"] = None

    return context


@dataclass
class Question:
    """Một mục checklist.

    Mục được GỘP theo (endpoint, param, category): nhiều rule cùng chủ đề
    áp dụng cho cùng một tham số sẽ nằm trong một mục với `rule_ids`.
    Câu hỏi hiển thị là `question_template` của rule đầu tiên; `rule_ids`
    ghi lại đầy đủ mọi rule mà câu trả lời này chốt cùng lúc.
    """

    id: str
    rule_id: str
    rule_ids: list[str]
    tier: str
    dimension: str
    category: str
    module_id: str
    sheet_name: str
    endpoint_id: str
    endpoint_label: str
    target: str
    param_name: str | None
    question: str
    questions: list[str]
    recommended_option: str
    alternative_options: list[str]
    nonce: str
    status: str = "PENDING"
    answered_by: str | None = None
    answer: Any = None
    evidence: str | None = None
    tier_reason: str = ""
    flag_name: str | None = None
    flag_current: bool | None = None
    flag_known: bool = False

    def add_rule(self, rule: dict[str, Any], tier: str, rendered: str) -> None:
        """Gộp thêm rule cùng chủ đề vào mục này."""
        if rule["id"] not in self.rule_ids:
            self.rule_ids.append(rule["id"])
        if rendered and rendered not in self.questions:
            self.questions.append(rendered)
        # Mục gộp có tier cao nhất trong các rule thành phần.
        if tier == "CRITICAL":
            self.tier = "CRITICAL"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_id": self.rule_id,
            "rule_ids": self.rule_ids,
            "tier": self.tier,
            "dimension": self.dimension,
            "category": self.category,
            "module_id": self.module_id,
            "sheet_name": self.sheet_name,
            "endpoint_id": self.endpoint_id,
            "endpoint_label": self.endpoint_label,
            "target": self.target,
            "param_name": self.param_name,
            "question": self.question,
            "questions": self.questions,
            "recommended_option": self.recommended_option,
            "alternative_options": self.alternative_options,
            "nonce": self.nonce,
            "status": self.status,
            "answered_by": self.answered_by,
            "answer": self.answer,
            "evidence": self.evidence,
            "tier_reason": self.tier_reason,
            "flag_name": self.flag_name,
            "flag_current": self.flag_current,
            "flag_known": self.flag_known,
        }


@dataclass
class SkippedRule:
    rule_id: str
    dimension: str
    category: str
    target_element: str
    trigger_condition: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "dimension": self.dimension,
            "category": self.category,
            "target_element": self.target_element,
            "trigger_condition": self.trigger_condition,
            "skipped_reason": self.reason,
        }


@dataclass
class MatchReport:
    questions: list[Question] = field(default_factory=list)
    matched_rule_ids: set[str] = field(default_factory=set)
    skipped: list[SkippedRule] = field(default_factory=list)
    total_rules: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def matched_count(self) -> int:
        return len(self.matched_rule_ids)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def coverage_ok(self) -> bool:
        return self.matched_count + self.skipped_count == self.total_rules

    def summary(self) -> dict[str, Any]:
        return {
            "total_rules": self.total_rules,
            "matched": self.matched_count,
            "skipped": self.skipped_count,
            "coverage_ok": self.coverage_ok,
            "questions": len(self.questions),
            "critical": sum(1 for q in self.questions if q.tier == CRITICAL),
            "standard": sum(1 for q in self.questions if q.tier == STANDARD),
            "parse_errors": len(self.parse_errors),
        }


def _make_nonce() -> str:
    return secrets.token_hex(NONCE_BYTES)


def _render_template(template: str, param_name: str | None) -> str:
    text = template or ""
    if param_name:
        text = text.replace("{param_name}", param_name)
    text = text.replace("{resource_name}", "tài nguyên")
    text = text.replace("{threshold_desc}", "ngưỡng")
    text = text.replace("{min_len}", "1").replace("{max_len}", "255")
    return text


def _alternatives(rule: dict[str, Any]) -> list[str]:
    raw = rule.get("alternative_options")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            raw = [raw]
    if not isinstance(raw, list):
        return []
    return [str(x) for x in raw if str(x).strip()]


def match_spec(spec: CanonicalSpec, ruleset: RuleSet | None = None,
               tier_config: dict[str, Any] | None = None) -> MatchReport:
    """Đánh giá toàn bộ rule trên toàn bộ spec."""
    if ruleset is None:
        ruleset = load_rules()
    if tier_config is None:
        tier_config = load_tier_config()

    report = MatchReport(total_rules=len(ruleset.rules), parse_errors=list(ruleset.parse_errors))

    # key -> Question; gộp theo (endpoint, param, target_element) để nhiều rule
    # cùng chủ đề trên cùng tham số nằm trong một câu hỏi với `rule_ids`.
    grouped: dict[tuple[str, str | None, str], Question] = {}
    # rule_id -> danh sách ngữ cảnh đã đánh giá nhưng không khớp (cho lý do)
    non_matching: dict[str, list[str]] = {}
    # (endpoint_id, param_name, target) -> Question, để gộp thêm rule
    key_to_question: dict[tuple[str, str | None, str], Question] = {}

    def _consider(rule: dict[str, Any], context: dict[str, Any], endpoint: Endpoint | None,
                  param: Param | None, module: Module, endpoint_label: str,
                  scope_label: str) -> None:
        result = evaluate(rule["trigger_condition"], context)
        if result.warnings:
            report.warnings.extend(f"[{rule['id']}] {w}" for w in result.warnings)
        if not result.value:
            non_matching.setdefault(rule["id"], []).append(scope_label)
            return

        report.matched_rule_ids.add(rule["id"])
        endpoint_id = endpoint.id if endpoint else ""
        param_name = param.name if param else None
        target_key = rule.get("target_element", "") or rule["id"]
        group_key = (endpoint_id, param_name, target_key)
        tier = determine_tier(rule, tier_config)
        rendered = _render_template(rule.get("question_template", ""), param_name)

        existing = key_to_question.get(group_key)
        if existing is not None:
            existing.add_rule(rule, tier, rendered)
            return

        question = _build_question(
            rule, module, endpoint, param, endpoint_label, tier_config, tier
        )
        key_to_question[group_key] = question
        grouped[group_key] = question

    def _mentions_param(rule: dict[str, Any]) -> bool:
        """Rule có phụ thuộc `param` không.

        Rule không nhắc tới `param` là rule cấp endpoint: đánh giá một lần cho
        endpoint, KHÔNG lặp lại cho từng tham số (nếu lặp sẽ bùng nổ số câu hỏi
        và tạo ra nhiều mục trùng chủ đề).
        """
        return "param" in rule.get("trigger_condition", "")

    for module in spec.modules:
        endpoints = module.endpoints or [None]

        for endpoint in endpoints:
            endpoint_label = (
                f"{endpoint.http_method} {endpoint.path}" if endpoint else "(không có endpoint)"
            )
            scope_ep = f"{module.sheet_name}:{endpoint_label}"

            # (a) Rule cấp endpoint
            context_ep = build_context(module, endpoint)
            for rule in ruleset.rules:
                if _mentions_param(rule):
                    continue
                _consider(rule, context_ep, endpoint, None, module, endpoint_label, scope_ep)

            # (b) Rule cấp tham số
            if endpoint is None:
                continue
            for param in endpoint.params:
                context_param = build_context(module, endpoint, param)
                scope_param = f"{scope_ep}:{param.name}"
                for rule in ruleset.rules:
                    if not _mentions_param(rule):
                        continue
                    _consider(
                        rule, context_param, endpoint, param, module, endpoint_label,
                        scope_param,
                    )

    report.questions = list(grouped.values())

    # (0) Sáu câu hỏi cờ cho mỗi module — đứng đầu checklist vì chúng quyết
    #     định rule nào áp dụng. Sinh SAU khi đánh giá rule để không làm nhiễu
    #     `matched_rule_ids`, nhưng chèn trước về thứ tự hiển thị.
    from .flags_questions import build_flag_questions

    flag_questions: list[Question] = []
    for module in spec.modules:
        flag_questions.extend(build_flag_questions(module))
    report.questions = flag_questions + report.questions

    # (c) Rule không khớp ở bất kỳ đâu -> có lý do
    for rule in ruleset.rules:
        if rule["id"] in report.matched_rule_ids:
            continue
        checked = non_matching.get(rule["id"], [])
        reason = _skip_reason(rule, checked, spec)
        report.skipped.append(
            SkippedRule(
                rule_id=rule["id"],
                dimension=rule.get("dimension", ""),
                category=rule.get("category", ""),
                target_element=rule.get("target_element", ""),
                trigger_condition=rule.get("trigger_condition", ""),
                reason=reason,
            )
        )

    return report


def _build_question(rule: dict[str, Any], module: Module, endpoint: Endpoint | None,
                    param: Param | None, endpoint_label: str,
                    tier_config: dict[str, Any], tier: str | None = None) -> Question:
    param_name = param.name if param else None
    # Id theo khoá gộp, không theo rule đại diện (design D1 của
    # stabilize-question-ids): bật/tắt cờ không còn làm id đổi.
    question_id = build_question_id(
        module.sheet_name or module.id,
        rule.get("target_element", "") or rule["id"],
        param_name,
    )
    if tier is None:
        tier = determine_tier(rule, tier_config)
    rendered = _render_template(rule.get("question_template", ""), param_name)
    return Question(
        id=question_id,
        rule_id=rule["id"],
        rule_ids=[rule["id"]],
        tier=tier,
        questions=[rendered] if rendered else [],
        dimension=rule.get("dimension", ""),
        category=rule.get("category", ""),
        module_id=module.id,
        sheet_name=module.sheet_name,
        endpoint_id=endpoint.id if endpoint else "",
        endpoint_label=endpoint_label,
        target=f"param:{param_name}" if param_name else "endpoint",
        param_name=param_name,
        question=rendered,
        recommended_option=str(rule.get("recommended_option", "")),
        alternative_options=_alternatives(rule),
        nonce=_make_nonce(),
        tier_reason=describe_tier_decision(rule, tier_config),
    )


FLAG_NAME_SET = {
    "has_status_field", "has_quota", "has_dependencies",
    "is_multi_tenant", "has_unique_field", "has_currency",
}


def _flag_dependencies(rule: dict[str, Any]) -> list[str]:
    """Các cờ mà `trigger_condition` tham chiếu, theo thứ tự xuất hiện."""
    condition = str(rule.get("trigger_condition", ""))
    found: list[str] = []
    for name in FLAG_NAME_SET:
        if name in condition and name not in found:
            found.append(name)
    # Sắp theo vị trí xuất hiện để lý do đọc tự nhiên
    return sorted(found, key=condition.find)


def _unconfirmed_flags(rule: dict[str, Any], spec: CanonicalSpec) -> list[str]:
    """Cờ mà rule phụ thuộc nhưng còn ở nguồn `default` ở mọi module."""
    deps = _flag_dependencies(rule)
    if not deps:
        return []
    unconfirmed: list[str] = []
    for name in deps:
        sources = {m.flags.source(name) for m in spec.modules}
        if sources and sources <= {"default"}:
            unconfirmed.append(name)
    return unconfirmed


def _skip_reason(rule: dict[str, Any], checked: list[str], spec: CanonicalSpec) -> str:
    """Lý do cụ thể vì sao rule không áp dụng cho spec này."""
    target = rule.get("target_element", "")
    condition = rule.get("trigger_condition", "")
    checked_count = len(checked)

    # Ưu tiên nêu nguyên nhân THẬT: cờ chưa được hỏi, không phải "điều kiện không thoả".
    unconfirmed = _unconfirmed_flags(rule, spec)
    if unconfirmed:
        names = ", ".join(unconfirmed)
        return (
            f"cờ {names} chưa được xác nhận — cần trả lời câu "
            f"{', '.join('FLAG:' + n for n in unconfirmed)} "
            f"(điều kiện hiện tại: '{condition}')"
        )

    if checked_count == 0:
        return (
            f"chưa có module/endpoint nào để đánh giá (target_element='{target}') — "
            f"spec có {len(spec.modules)} module"
        )

    if condition.strip() == "true":
        # Điều kiện luôn đúng mà không khớp là bất khả thi -> dấu hiệu lỗi
        return f"điều kiện 'true' nhưng không khớp — cần kiểm tra lại (target='{target}')"

    hints = _target_hints(target)
    return (
        f"điều kiện '{condition}' không thoả trên {checked_count} ngữ cảnh đã kiểm; "
        f"target_element='{target}' cần {hints}"
    )


def _target_hints(target: str) -> str:
    """Mô tả dạng dữ liệu mà target_element yêu cầu, để người đọc hiểu vì sao trượt."""
    if target.endswith("_param"):
        return "tham số có kiểu/tên/định dạng tương ứng"
    if target.endswith("_endpoint") or target in ("all_endpoints", "request_body", "json_body"):
        return "endpoint có path/method/auth tương ứng"
    if target in ("database_transaction", "database_connection", "async_worker",
                  "external_client", "external_dependency"):
        return "thành phần hạ tầng tương ứng (spec hiện không mô tả)"
    return "ngữ cảnh tương ứng"


def build_checklist(report: MatchReport, spec: CanonicalSpec) -> dict[str, Any]:
    """Payload checklist ghi ra `interview/checklist.json`."""
    questions = [q.to_dict() for q in report.questions]
    summary = report.summary()

    return {
        "schema_version": 1,
        "session_state": "AWAITING_USER_INTERACTION",
        "project": spec.project.to_dict(),
        "coverage": summary,
        "modules": [
            {
                "id": m.id,
                "sheet_name": m.sheet_name,
                "module_name": m.module_name,
                "flags": m.flags.to_dict(),
            }
            for m in spec.modules
        ],
        "skipped_rules": [s.to_dict() for s in report.skipped],
        "warnings": report.warnings[:200],
        "questions": questions,
    }
