"""utd.reconcile - Sinh báo cáo đối chiếu đặc tả vs mã nguồn.

Đây là stage DUY NHẤT được phép mở mã nguồn dự án. Máy không tự suy ra kết luận
đối chiếu: nó nhận `--findings` (do người/LLM điền sau khi đọc code) và phân loại
thành 4 nhóm theo `document-output` spec:

    Match           - code khớp 100% với rule
    Mismatch        - code xử lý sai biên/công thức/status/mã lỗi
    Missing in code - rule có trong đặc tả nhưng code chưa xử lý
    Extra in code   - logic có trong code nhưng không có trong đặc tả
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATEGORIES = ("Match", "Mismatch", "Missing in code", "Extra in code")

CATEGORY_LABEL = {
    "Match": "ĐÚNG (Match)",
    "Mismatch": "SAI / LỆCH (Mismatch)",
    "Missing in code": "THIẾU TRONG CODE (Missing)",
    "Extra in code": "THỪA NGOÀI ĐẶC TẢ (Extra in code)",
}


class ReconcileError(Exception):
    def __init__(self, message: str, exit_code: int = 2):
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class Finding:
    rule_id: str
    category: str
    detail: str = ""
    location: str = ""
    cases: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "category": self.category,
            "detail": self.detail,
            "location": self.location,
            "cases": self.cases,
        }


def load_findings(path: str | Path) -> list[Finding]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    items = data.get("findings") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ReconcileError("findings phải là mảng hoặc object có khoá 'findings'")

    findings: list[Finding] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ReconcileError(f"findings[{index}] phải là object")
        rule_id = str(item.get("rule_id") or "").strip()
        if not rule_id:
            raise ReconcileError(f"findings[{index}] thiếu 'rule_id'")
        category = str(item.get("category") or "").strip()
        if category not in CATEGORIES:
            raise ReconcileError(
                f"findings[{index}] category '{category}' không hợp lệ "
                f"(dùng: {', '.join(CATEGORIES)})",
                exit_code=3,
            )
        findings.append(
            Finding(
                rule_id=rule_id,
                category=category,
                detail=str(item.get("detail") or ""),
                location=str(item.get("location") or ""),
                cases=list(item.get("cases") or []),
            )
        )
    return findings


def collect_rules(ssot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Tập rule khai báo trong SSOT, kèm mã test case tham chiếu."""
    rules: dict[str, dict[str, Any]] = {}
    for module in ssot.get("modules", []):
        sheet = module.get("sheet_name", "")
        for method in module.get("methods", []):
            api = method.get("api") or {}
            for rule in api.get("rules") or []:
                rule_id = rule.get("id")
                if not rule_id:
                    continue
                entry = rules.setdefault(
                    rule_id,
                    {"text": rule.get("text", ""), "sheet": sheet, "cases": []},
                )
                for case in method.get("test_cases", []):
                    refs = case.get("rule_refs") or []
                    if isinstance(refs, str):
                        refs = [refs]
                    if rule_id in refs and case.get("id"):
                        entry["cases"].append(case["id"])
    return rules


def build_report(ssot: dict[str, Any], findings: list[Finding],
                 project_name: str = "") -> str:
    rules = collect_rules(ssot)
    by_category: dict[str, list[Finding]] = {c: [] for c in CATEGORIES}
    for finding in findings:
        by_category[finding.category].append(finding)

    total_expected = len(rules)
    accounted = {f.rule_id for f in findings}
    unclassified = sorted(set(rules) - accounted)
    unknown = sorted(accounted - set(rules))

    lines: list[str] = []
    lines.append("# Báo cáo đối chiếu Đặc tả vs Mã nguồn")
    lines.append("")
    if project_name:
        lines.append(f"**Dự án:** {project_name}")
        lines.append("")

    lines.append("## Tổng hợp")
    lines.append("")
    lines.append("| Nhóm | Số rule |")
    lines.append("|---|---|")
    for category in CATEGORIES:
        lines.append(f"| {CATEGORY_LABEL[category]} | {len(by_category[category])} |")
    lines.append(f"| **Tổng đã phân loại** | **{len(findings)}** |")
    lines.append(f"| Rule trong đặc tả | {total_expected} |")
    lines.append("")
    lines.append(
        f"Kiểm tra cộng: {len(findings)} finding + {len(unclassified)} rule chưa "
        f"phân loại = {total_expected} rule đặc tả."
    )
    lines.append("")

    for category in CATEGORIES:
        items = by_category[category]
        if not items:
            continue
        lines.append(f"## {CATEGORY_LABEL[category]}")
        lines.append("")
        lines.append("| Rule ID | Test case | Chi tiết | Vị trí code |")
        lines.append("|---|---|---|---|")
        for finding in items:
            cases = ", ".join(finding.cases) if finding.cases else (
                ", ".join(rules.get(finding.rule_id, {}).get("cases", [])) or "-"
            )
            lines.append(
                f"| {finding.rule_id} | {cases} | {finding.detail or '-'} "
                f"| {finding.location or '-'} |"
            )
        lines.append("")

    if unclassified:
        lines.append("## Rule chưa đối chiếu")
        lines.append("")
        for rule_id in unclassified:
            text = rules[rule_id]["text"]
            lines.append(f"- {rule_id}: {text[:100]}")
        lines.append("")

    if unknown:
        lines.append("## Finding không khớp rule nào trong đặc tả")
        lines.append("")
        for rule_id in unknown:
            lines.append(f"- {rule_id} (kiểm tra lại rule id)")
        lines.append("")

    return "\n".join(lines)


def reconcile_from_files(ssot_path: str | Path, findings_path: str | Path,
                         out_dir: str | Path) -> tuple[Path, dict[str, Any]]:
    from .io import atomic_write

    ssot = json.loads(Path(ssot_path).read_text(encoding="utf-8"))
    findings = load_findings(findings_path)
    project = ssot.get("project") or {}
    text = build_report(ssot, findings, project.get("name", ""))

    target = Path(out_dir) / "gap_report.md"
    atomic_write(target, text)

    rules = collect_rules(ssot)
    summary = {
        "total_findings": len(findings),
        "total_expected": len(rules),
        "unclassified": len(set(rules) - {f.rule_id for f in findings}),
        "by_category": {
            category: sum(1 for f in findings if f.category == category)
            for category in CATEGORIES
        },
    }
    return target, summary
