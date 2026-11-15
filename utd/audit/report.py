"""utd.audit.report - Ghi `audit/report.json` + `audit/report.md`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..io import atomic_write
from .gates import AuditReport, format_markdown


def write_report(report: AuditReport, out_dir: str | Path) -> tuple[Path, Path]:
    target = Path(out_dir)
    json_path = target / "report.json"
    md_path = target / "report.md"

    atomic_write(
        json_path,
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
    )
    atomic_write(md_path, format_markdown(report))

    return json_path, md_path


def count_issues_by_gate(report: AuditReport) -> dict[str, int]:
    return {result.gate: len(result.issues) for result in report.results}


def issues_match_json_and_markdown(report: AuditReport) -> bool:
    """Bảo đảm hai bản báo cáo mô tả cùng số vi phạm."""
    from .gates import format_markdown as render

    text = render(report)
    counts = count_issues_by_gate(report)
    return all(not (counts[gate] and gate not in text) for gate in counts)
