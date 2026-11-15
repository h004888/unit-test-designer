"""utd.audit.gates - Chín cổng kiểm toán kỹ thuật.

G1 EP              - tham số required phải có case thiếu/null kiểu Abnormal
G2 BVA             - có biên thì phải có case min-1 và max+1
G3 DUAL-PATH       - mỗi rule cần 1 case hợp lệ + 1 case vi phạm
G4 HTTP-STATUS     - mỗi mã response khai báo phải có case kiểm chứng
G5 ANTI-SLOP       - không chứa chuỗi mẫu vô nghĩa (blacklist cũ)
G6 SECURITY        - endpoint có auth phải có case 401
G7 SOURCE-RULE-COVERAGE - 150 rule nguồn, mỗi rule matched hoặc skipped có lý do
G8 EP-PROPER       - case "thiếu tham số" phải type=Abnormal, không tính case Normal
G9 NO-SLOP-PROPERTY - phát hiện slop theo thuộc tính, không chỉ blacklist

G8 và G9 là cổng mới; chúng sửa hai lỗ hổng đã đo được ở bản cũ:
  - verify_ep chấp nhận case Normal chỉ vì chuỗi input tình cờ thiếu tên param
  - verify_anti_slop chỉ chặn 5 chuỗi đen nên P001/id=1 lọt qua
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..generate.data import is_slop
from ..generate.ids import UTC_PATTERN

GATE_IDS = ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9")

GATE_NAMES = {
    "G1": "EP",
    "G2": "BVA",
    "G3": "DUAL-PATH",
    "G4": "HTTP-STATUS",
    "G5": "ANTI-SLOP",
    "G6": "SECURITY",
    "G7": "SOURCE-RULE-COVERAGE",
    "G8": "EP-PROPER",
    "G9": "NO-SLOP-PROPERTY",
}

GATE_ACTIONS = {
    "G1": "Bổ sung test case type=Abnormal cho tham số required (thiếu hoặc null)",
    "G2": "Bổ sung case biên min-1 và max+1 cho tham số có khoảng",
    "G3": "Bổ sung case Normal/Boundary và Abnormal cho rule được nêu",
    "G4": "Bổ sung test case có Expected Results chứa mã HTTP được khai báo",
    "G5": "Thay dữ liệu mẫu bằng dữ liệu thật từ kho",
    "G6": "Bổ sung test case 401 cho endpoint yêu cầu auth",
    "G7": "Khai báo lý do bỏ qua rule, hoặc bổ sung endpoint phù hợp",
    "G8": "Đổi type của case thiếu tham số thành Abnormal",
    "G9": "Thay giá trị giả (P001, id=1, chuỗi lặp) bằng dữ liệu thật",
}

BLACKLIST_SLOP = ("john doe", "jane doe", "test@example.com", "123 main st", "1111111111")

PROPERTY_SLOP = (
    (re.compile(r"^P\d{3}$", re.IGNORECASE), "định danh giả dạng P001"),
    (re.compile(r"\b(id|orderId|productId|userId)\s*=\s*1$", re.IGNORECASE),
     "định danh giả dạng id=1"),
    (re.compile(r"^(.)\1{5,}$"), "ký tự đơn lặp ≥6 lần"),
    (re.compile(r"^(abc|xyz|foo|bar|baz|test)\d*$", re.IGNORECASE), "chuỗi placeholder"),
    (re.compile(r"^<[a-z_]+>$", re.IGNORECASE), "placeholder không thay giá trị"),
)

REPEATED_CHAR = re.compile(r"(.)\1{5,}")


@dataclass
class Issue:
    gate: str
    sheet: str
    method: str
    message: str
    case_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "gate": self.gate,
            "gate_name": GATE_NAMES[self.gate],
            "sheet": self.sheet,
            "method": self.method,
            "message": self.message,
            "action": GATE_ACTIONS[self.gate],
        }
        if self.case_id:
            data["case_id"] = self.case_id
        return data


@dataclass
class GateResult:
    gate: str
    passed: bool
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "name": GATE_NAMES[self.gate],
            "passed": self.passed,
            "issue_count": len(self.issues),
            "issues": [i.to_dict() for i in self.issues],
        }


@dataclass
class AuditReport:
    results: list[GateResult] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    @property
    def total_issues(self) -> int:
        return sum(len(result.issues) for result in self.results)

    def by_gate(self, gate: str) -> GateResult | None:
        return next((r for r in self.results if r.gate == gate), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total_issues": self.total_issues,
            "gates": [r.to_dict() for r in self.results],
            "context": self.context,
        }


def _input_str(case: dict[str, Any]) -> str:
    raw = case.get("input", "")
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw)


def _expected_str(case: dict[str, Any]) -> str:
    raw = case.get("expected", "")
    if isinstance(raw, dict):
        return json.dumps(raw, ensure_ascii=False)
    return str(raw)


def _case_id(case: dict[str, Any]) -> str | None:
    return case.get("id") or None


def _bounds(param: dict[str, Any]) -> tuple[int, int] | None:
    constraints = param.get("constraints") or {}
    if not isinstance(constraints, dict):
        return None
    lowest = constraints.get("min")
    highest = constraints.get("max")
    if isinstance(lowest, int) and isinstance(highest, int):
        return lowest, highest
    return None


# --- G1 EP -----------------------------------------------------------------


def gate_ep(sheet: str, method: dict[str, Any]) -> GateResult:
    api = method.get("api") or {}
    params = api.get("request") or []
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for param in params:
        name = param.get("name")
        if not name or not param.get("required"):
            continue

        covered = False
        for case in cases:
            if case.get("type") != "Abnormal":
                continue
            text = _input_str(case)
            note = str(case.get("note", "")).lower()
            missing = f"{name}=" not in text and f'"{name}"' not in text
            nulled = f"{name}=null" in text or f"{name}=None" in text or f'"{name}": null' in text
            if missing or nulled or "missing" in note or "null" in note:
                covered = True
                break

        if not covered:
            issues.append(
                Issue("G1", sheet, method.get("name", "?"),
                      f"Tham số required '{name}' chưa có test case Abnormal "
                      f"kiểm thử Missing/Null")
            )

    return GateResult("G1", not issues, issues)


# --- G2 BVA ----------------------------------------------------------------


def gate_bva(sheet: str, method: dict[str, Any]) -> GateResult:
    api = method.get("api") or {}
    params = api.get("request") or []
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for param in params:
        bounds = _bounds(param)
        if bounds is None:
            continue
        lowest, highest = bounds
        name = param.get("name")

        has_min_minus = any(
            f"{name}={lowest - 1}" in _input_str(c) for c in cases
        )
        has_max_plus = any(
            f"{name}={highest + 1}" in _input_str(c) for c in cases
        )

        if not has_min_minus:
            issues.append(
                Issue("G2", sheet, method.get("name", "?"),
                      f"Param '{name}' khoảng {lowest}..{highest} thiếu điểm biên "
                      f"Min-1 ({lowest - 1})")
            )
        if not has_max_plus:
            issues.append(
                Issue("G2", sheet, method.get("name", "?"),
                      f"Param '{name}' khoảng {lowest}..{highest} thiếu điểm biên "
                      f"Max+1 ({highest + 1})")
            )

    return GateResult("G2", not issues, issues)


# --- G3 DUAL-PATH ---------------------------------------------------------


def gate_dual_path(sheet: str, method: dict[str, Any]) -> GateResult:
    api = method.get("api") or {}
    rules = api.get("rules") or []
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for rule in rules:
        rule_id = rule.get("id")
        if not rule_id:
            continue

        valid_count = 0
        invalid_count = 0
        for case in cases:
            refs = case.get("rule_refs", [])
            if isinstance(refs, str):
                refs = [refs]
            if rule_id not in refs:
                continue
            if case.get("type") in ("Normal", "Boundary"):
                valid_count += 1
            elif case.get("type") == "Abnormal":
                invalid_count += 1

        if valid_count == 0:
            issues.append(
                Issue("G3", sheet, method.get("name", "?"),
                      f"Rule '{rule_id}' chưa có test case hợp lệ (Normal hoặc Boundary)")
            )
        if invalid_count == 0:
            issues.append(
                Issue("G3", sheet, method.get("name", "?"),
                      f"Rule '{rule_id}' chưa có test case vi phạm (Abnormal)")
            )

    return GateResult("G3", not issues, issues)


# --- G4 HTTP-STATUS -------------------------------------------------------


def gate_http_status(sheet: str, method: dict[str, Any]) -> GateResult:
    api = method.get("api") or {}
    responses = api.get("responses") or []
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for response in responses:
        status = response.get("status")
        if not status:
            continue
        status_text = str(status)
        found = any(
            re.search(rf"HTTP\s*/?\s*{re.escape(status_text)}\b", _expected_str(c))
            for c in cases
        )
        if not found:
            issues.append(
                Issue("G4", sheet, method.get("name", "?"),
                      f"Mã HTTP {status_text} khai báo trong Responses chưa có test case "
                      f"nào kiểm chứng")
            )

    return GateResult("G4", not issues, issues)


# --- G5 ANTI-SLOP (blacklist cũ) -----------------------------------------


def gate_anti_slop(sheet: str, method: dict[str, Any]) -> GateResult:
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for case in cases:
        lowered = _input_str(case).lower()
        for slop in BLACKLIST_SLOP:
            if slop in lowered:
                issues.append(
                    Issue("G5", sheet, method.get("name", "?"),
                          f"Test case chứa dữ liệu rác (Slop Data): '{slop}'",
                          _case_id(case))
                )

    return GateResult("G5", not issues, issues)


# --- G6 SECURITY ----------------------------------------------------------


def gate_security(sheet: str, method: dict[str, Any]) -> GateResult:
    api = method.get("api") or {}
    auth = api.get("auth")
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    if auth and str(auth).lower() not in ("none", "public", "", "null"):
        has_auth_case = False
        for case in cases:
            expected = _expected_str(case)
            note = str(case.get("note", "")).lower()
            if ("401" in expected or "unauthorized" in note or "token" in note):
                has_auth_case = True
                break
        if not has_auth_case:
            issues.append(
                Issue("G6", sheet, method.get("name", "?"),
                      "API yêu cầu Authentication nhưng chưa có test case "
                      "Missing/Expired Token (HTTP 401)")
            )

    return GateResult("G6", not issues, issues)


# --- G8 EP-PROPER (mới) ---------------------------------------------------


def gate_ep_proper(sheet: str, method: dict[str, Any]) -> GateResult:
    """Case 'thiếu tham số' phải type=Abnormal; case Normal không được tính.

    Lỗ hổng bản cũ: `verify_ep` quét mọi test case, nên một case Normal viết
    sai định dạng Input (tình cờ thiếu tên param) được tính là đã phủ.
    """
    api = method.get("api") or {}
    params = api.get("request") or []
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for param in params:
        name = param.get("name")
        if not name or not param.get("required"):
            continue

        for case in cases:
            if case.get("type") == "Abnormal":
                continue
            text = _input_str(case)
            note = str(case.get("note", "")).lower()
            missing = f"{name}=" not in text and f'"{name}"' not in text
            nulled = f"{name}=null" in text or f'"{name}": null' in text
            declared_missing = "missing" in note or "thiếu" in note
            if missing or nulled or declared_missing:
                issues.append(
                    Issue("G8", sheet, method.get("name", "?"),
                          f"Case '{_case_id(case) or '?'}' thể hiện thiếu/null tham số "
                          f"'{name}' nhưng type là 'Normal' — phải là Abnormal",
                          _case_id(case))
                )

    return GateResult("G8", not issues, issues)


# --- G9 NO-SLOP-PROPERTY (mới) -------------------------------------------


def gate_no_slop_property(sheet: str, method: dict[str, Any]) -> GateResult:
    """Phát hiện slop theo thuộc tính, không chỉ 5 chuỗi đen."""
    api = method.get("api") or {}
    cases = method.get("test_cases") or []
    issues: list[Issue] = []

    for case in cases:
        text = _input_str(case)
        case_id = _case_id(case)

        for chunk in text.split(";"):
            if "=" not in chunk:
                continue
            key, value = chunk.split("=", 1)
            key = key.strip().lower()
            value = value.strip()
            if not value:
                continue

            if is_slop(value):
                issues.append(
                    Issue("G9", sheet, method.get("name", "?"),
                          f"Giá trị '{value[:40]}' là dữ liệu giả (blacklist)",
                          case_id)
                )
                continue

            # Định danh giả: giá trị 1/001 gán cho tham số kiểu id
            if re.search(r"(id|uuid|code)$", key) and value in ("1", "001", "01", "0"):
                issues.append(
                    Issue("G9", sheet, method.get("name", "?"),
                          f"Tham số '{key}' dùng định danh giả '{value}'",
                          case_id)
                )
                continue

            for pattern, reason in PROPERTY_SLOP:
                if pattern.search(value):
                    issues.append(
                        Issue("G9", sheet, method.get("name", "?"),
                              f"Giá trị '{value[:40]}' vi phạm thuộc tính: {reason}",
                              case_id)
                    )
                    break

            if REPEATED_CHAR.search(value) and len(value) <= 20:
                issues.append(
                    Issue("G9", sheet, method.get("name", "?"),
                          f"Giá trị '{value[:40]}' chứa ký tự lặp đơn điệu",
                          case_id)
                )

    return GateResult("G9", not issues, issues)


# --- G7 SOURCE-RULE-COVERAGE (cần dữ liệu từ inventory) ------------------


def gate_source_rule_coverage(sheet: str, method: dict[str, Any],
                              coverage: dict[str, Any] | None = None) -> GateResult:
    """Kiểm 150 rule nguồn; PASS khi matched + skipped-có-lý-do == total.

    Khác biệt cốt lõi so với bản cũ: bản cũ chỉ kiểm `uncovered_rules` trên
    rule ĐÃ sinh ra, nên 51 rule không bao giờ sinh vẫn không bị phát hiện.
    """
    issues: list[Issue] = []
    if not coverage:
        return GateResult("G7", True, [])

    total = int(coverage.get("total_rules") or 0)
    matched = int(coverage.get("matched") or 0)
    skipped = int(coverage.get("skipped") or 0)
    unaccounted = int(coverage.get("unaccounted") or 0)

    if unaccounted > 0:
        issues.append(
            Issue("G7", sheet, method.get("name", "?"),
                  f"{unaccounted} rule không matched và không có skipped_reason")
        )
    if total and matched + skipped != total:
        issues.append(
            Issue("G7", sheet, method.get("name", "?"),
                  f"matched ({matched}) + skipped ({skipped}) != total ({total})")
        )

    return GateResult("G7", not issues, issues)


# --- chạy toàn bộ ----------------------------------------------------------


def audit_ssot(ssot: dict[str, Any], coverage: dict[str, Any] | None = None,
               skipped_rules: list[dict[str, Any]] | None = None) -> AuditReport:
    """Chạy 9 cổng trên toàn bộ SSOT."""
    report = AuditReport()
    results_by_gate: dict[str, GateResult] = {
        gate: GateResult(gate, True, []) for gate in GATE_IDS
    }

    for module in ssot.get("modules", []):
        sheet = module.get("sheet_name", "Unknown_Sheet")
        for method in module.get("methods", []):
            for gate_name, fn in (
                ("G1", gate_ep),
                ("G2", gate_bva),
                ("G3", gate_dual_path),
                ("G4", gate_http_status),
                ("G5", gate_anti_slop),
                ("G6", gate_security),
                ("G8", gate_ep_proper),
                ("G9", gate_no_slop_property),
            ):
                partial = fn(sheet, method)
                results_by_gate[gate_name].issues.extend(partial.issues)

    # G7 chạy một lần trên coverage toàn cục
    g7_context = coverage or {}
    if skipped_rules is not None:
        missing_reason = [
            r.get("rule_id") for r in skipped_rules
            if not str(r.get("skipped_reason") or "").strip()
        ]
        g7_context = dict(g7_context)
        g7_context.setdefault("unaccounted", len(missing_reason))
    g7_result = gate_source_rule_coverage("(global)", {"name": "all"}, g7_context)
    results_by_gate["G7"].issues.extend(g7_result.issues)

    for gate in GATE_IDS:
        result = results_by_gate[gate]
        result.passed = not result.issues
        report.results.append(result)

    report.context = {
        "modules": len(ssot.get("modules", [])),
        "coverage": coverage or {},
        "uncovered_rules": ssot.get("uncovered_rules", []),
        "zero_normal_sheets": ssot.get("zero_normal_sheets", []),
    }

    # uncovered_rules từ generator cũng là dấu hiệu G3 hỏng
    if ssot.get("uncovered_rules"):
        g3 = results_by_gate["G3"]
        for entry in ssot["uncovered_rules"]:
            g3.issues.append(
                Issue("G3", entry.split(":")[0], "?",
                      f"Rule '{entry.split(':')[-1]}' không có test case nào tham chiếu")
            )
        g3.passed = False

    return report


def format_markdown(report: AuditReport) -> str:
    """Báo cáo người đọc: nhóm theo cổng, kèm hành động."""
    lines = ["# Audit Report", ""]

    status = "PASSED" if report.passed else "REJECTED"
    lines.append(f"**Kết quả:** {status} — {report.total_issues} vi phạm")
    lines.append("")

    lines.append("## Tổng hợp")
    lines.append("")
    lines.append("| Cổng | Tên | Kết quả | Vi phạm |")
    lines.append("|---|---|---|---|")
    for result in report.results:
        mark = "PASS" if result.passed else "FAIL"
        lines.append(
            f"| {result.gate} | {GATE_NAMES[result.gate]} | {mark} | "
            f"{len(result.issues)} |"
        )
    lines.append("")

    for result in report.results:
        if result.passed:
            continue
        lines.append(f"## {result.gate} — {GATE_NAMES[result.gate]}")
        lines.append("")
        lines.append(f"**Hành động:** {GATE_ACTIONS[result.gate]}")
        lines.append("")
        for issue in result.issues:
            location = f"[{issue.sheet} :: {issue.method}]"
            case = f" ({issue.case_id})" if issue.case_id else ""
            lines.append(f"- {location}{case} {issue.message}")
        lines.append("")

    coverage = report.context.get("coverage") or {}
    if coverage:
        lines.append("## Reachability")
        lines.append("")
        lines.append(
            f"- Tổng rule: {coverage.get('total_rules', '?')}"
        )
        lines.append(f"- Áp dụng: {coverage.get('matched', '?')}")
        lines.append(f"- Bỏ qua có lý do: {coverage.get('skipped', '?')}")
        lines.append("")

    return "\n".join(lines)
