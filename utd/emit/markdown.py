"""utd.emit.markdown - Sinh `.md` mỗi module + `index.md` từ SSOT.

Bố cục bám `references/layout-xlsx.md`: đặc tả API, Summary, 16 cột test case,
ma trận truy vết.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..io import atomic_write
from .formatting import (
    fmt_expected,
    fmt_input,
    md_row,
    slugify,
    tc_note,
)
from .layout import DETAIL_HEADERS, VALID_TYPES


def api_title(method: dict[str, Any]) -> str:
    api = method.get("api") or {}
    if api.get("http_method") and api.get("path"):
        return f"{str(api['http_method']).upper()} {api['path']}"
    return method.get("name", "")


def trace_rows(method: dict[str, Any]) -> tuple[list[dict], dict[str, list[str]]]:
    """Ma trận truy vết: mỗi rule -> danh sách mã test case kiểm chứng."""
    api = method.get("api") or {}
    rules = api.get("rules") or []
    cover: dict[str, list[str]] = {rule.get("id", ""): [] for rule in rules}
    for case in method.get("test_cases", []):
        refs = case.get("rule_refs") or []
        if isinstance(refs, str):
            refs = [refs]
        for rule_id in refs:
            cover.setdefault(rule_id, []).append(case.get("id", ""))
    return rules, cover


def _constraints_text(param: dict[str, Any]) -> str:
    constraints = param.get("constraints") or {}
    if not isinstance(constraints, dict):
        return str(constraints)
    parts = []
    if constraints.get("min") is not None or constraints.get("max") is not None:
        parts.append(f"{constraints.get('min')}..{constraints.get('max')}")
    if constraints.get("pattern"):
        parts.append(f"pattern={constraints['pattern']}")
    if constraints.get("enum"):
        parts.append("enum: " + ", ".join(str(v) for v in constraints["enum"]))
    return "; ".join(parts)


def build_module_md(ssot: dict[str, Any], module: dict[str, Any],
                    method: dict[str, Any]) -> str:
    project = ssot["project"]
    api = method.get("api") or {}
    cases = method.get("test_cases", [])
    total = len(cases)
    type_counts = {
        kind: sum(1 for case in cases if case.get("type") == kind)
        for kind in VALID_TYPES
    }

    lines: list[str] = []
    lines.append(f"# Unit Test Design - {api_title(method)}")
    lines.append("")
    lines.append(f"- **Project:** {project['name']} ({project['code']})")
    lines.append(f"- **Module:** {module['module_name']}")
    lines.append(
        f"- **Version:** {project['version']} | **Issue date:** {project['issue_date']} "
        f"| **Creator:** {project['creator'] or 'N/A'}"
    )
    if api.get("source"):
        lines.append(f"- **Nguồn đặc tả:** {api['source']}")
    lines.append("")

    section = 1
    if api:
        lines.append("## 1. API Specification")
        lines.append("")
        if api.get("summary"):
            lines.append(str(api["summary"]))
            lines.append("")
        if api.get("auth"):
            lines.append(f"- **Authentication:** {api['auth']}")
            lines.append("")
        if api.get("request"):
            lines.append("**Request parameters**")
            lines.append("")
            lines.append("| Name | In | Type | Required | Constraints |")
            lines.append("|---|---|---|---|---|")
            for param in api["request"]:
                required = param.get("required")
                required_text = "Yes" if required is True else ("No" if required is False else required or "")
                lines.append(md_row([
                    param.get("name"),
                    param.get("in", ""),
                    param.get("type", ""),
                    required_text,
                    _constraints_text(param),
                ]))
            lines.append("")
        if api.get("responses"):
            lines.append("**Responses**")
            lines.append("")
            lines.append("| Status | Error code | Description |")
            lines.append("|---|---|---|")
            for response in api["responses"]:
                lines.append(md_row([
                    response.get("status"),
                    response.get("error_code", ""),
                    response.get("condition", ""),
                ]))
            lines.append("")
        if api.get("rules"):
            lines.append("**Business rules / Requirements**")
            lines.append("")
            lines.append("| ID | Rule | Source |")
            lines.append("|---|---|---|")
            for rule in api["rules"]:
                lines.append(md_row([rule.get("id"), rule.get("text", ""),
                                     rule.get("source", "")]))
            lines.append("")
        section = 2

    lines.append(f"## {section}. Summary")
    lines.append("")
    lines.append(f"- **Code Module:** {module['sheet_name']}")
    lines.append(f"- **Number of TCs:** {total}")
    lines.append("")
    lines.append("| Testing Round | Passed | Failed | Pending |")
    lines.append("|---|---|---|---|")
    for round_number in (1, 2, 3):
        lines.append(f"| Round {round_number} | 0 | 0 | {total} |")
    lines.append("")
    lines.append("| Testing Type | Normal | Abnormal | Boundary |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| Count | {type_counts['Normal']} | {type_counts['Abnormal']} "
        f"| {type_counts['Boundary']} |"
    )
    lines.append("")
    lines.append(
        "> Bảng Markdown không có công thức: sau khi test, cập nhật số liệu Round "
        "thủ công (hoặc dùng file Excel để tự thống kê)."
    )
    lines.append("")

    lines.append(f"## {section + 1}. Test Case Details")
    lines.append("")
    lines.append(md_row(DETAIL_HEADERS))
    lines.append("|" + "---|" * len(DETAIL_HEADERS))
    lines.append(md_row([f"**{method['name']}**"] + [""] * (len(DETAIL_HEADERS) - 1)))
    for case in cases:
        pre = case.get("pre") or case.get("pre_conditions") or "N/A"
        lines.append(md_row([
            case.get("id", ""), pre, fmt_input(case.get("input")),
            fmt_expected(case), case.get("type", ""),
            "Pending", "", "", "Pending", "", "", "Pending", "", "",
            case.get("defect_ids", ""), tc_note(case),
        ]))
    lines.append("")

    rules, cover = trace_rows(method)
    if rules:
        lines.append(f"## {section + 2}. Traceability Matrix (Rule → Test case)")
        lines.append("")
        lines.append("| Rule ID | Test cases | Covered |")
        lines.append("|---|---|---|")
        for rule in rules:
            ids = cover.get(rule.get("id", ""), [])
            lines.append(md_row([
                rule.get("id"),
                ", ".join(ids) or "-",
                "Yes" if ids else "**NO - cần bổ sung TC**",
            ]))
        lines.append("")

    return "\n".join(lines)


def uncovered_rules(ssot: dict[str, Any]) -> list[tuple[str, str]]:
    missing: list[tuple[str, str]] = []
    for module in ssot.get("modules", []):
        for method in module.get("methods", []):
            rules, cover = trace_rows(method)
            for rule in rules:
                if not cover.get(rule.get("id", "")):
                    missing.append((api_title(method), rule.get("id", "")))
    return missing


def write_markdown(ssot: dict[str, Any], out_dir: str | Path) -> list[Path]:
    """Ghi mỗi API một file .md + index.md. Trả danh sách đường dẫn đã ghi."""
    target = Path(out_dir)
    written: list[Path] = []
    used: set[str] = set()
    index_rows: list[tuple] = []

    for module in ssot.get("modules", []):
        for method in module.get("methods", []):
            api = method.get("api") or {}
            if api.get("http_method") and api.get("path"):
                base = slugify(f"{api['http_method']}_{api['path']}")
            else:
                base = slugify(f"{module['sheet_name']}_{method['name'].split('(')[0]}")

            name, counter = base, 2
            while name.lower() in used:
                name, counter = f"{base}_{counter}", counter + 1
            used.add(name.lower())

            path = target / f"{name}.md"
            atomic_write(path, build_module_md(ssot, module, method) + "\n")
            written.append(path)

            cases = method.get("test_cases", [])
            index_rows.append((
                module["module_name"], module["sheet_name"], api_title(method),
                f"{name}.md", len(cases),
                *[sum(1 for c in cases if c.get("type") == kind) for kind in VALID_TYPES],
            ))

    project = ssot["project"]
    lines = [
        f"# Unit Test Design - {project['name']} ({project['code']})",
        "",
        f"Version {project['version']} - {project['issue_date']}",
        "",
        "| Module | Sheet | API / Function | File | TCs | Normal | Abnormal | Boundary |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in index_rows:
        lines.append(md_row([row[0], row[1], row[2], f"[{row[3]}]({row[3]})", *row[4:]]))

    if index_rows:
        totals = [sum(row[k] for row in index_rows) for k in range(4, 8)]
        lines.append(md_row(["**Total**", "", "", "", *totals]))

    missing = uncovered_rules(ssot)
    if missing:
        lines += ["", "## Rule chưa có test case", ""]
        lines += [f"- {title}: {rule_id}" for title, rule_id in missing]

    index_path = target / "index.md"
    atomic_write(index_path, "\n".join(lines) + "\n")
    written.append(index_path)

    return written
