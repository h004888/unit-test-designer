"""utd.interview.verify - Cổng chặn: 0 sạch, 1 còn PENDING, 4 nguồn không hợp lệ."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..io import atomic_write, read_text, sha256_text

EXIT_CLEAN = 0
EXIT_PENDING = 1
EXIT_TAMPER = 4

CRITICAL = "CRITICAL"
ALLOWED_CRITICAL_SOURCES = ("USER_UI", "USER_CHAT")
ALLOWED_STANDARD_SOURCES = ("USER_UI", "USER_CHAT", "STANDARD_BATCH")


@dataclass
class VerifyReport:
    exit_code: int
    total: int = 0
    answered: int = 0
    pending: int = 0
    pending_items: list[dict[str, Any]] = field(default_factory=list)
    tampered: list[str] = field(default_factory=list)
    by_source: dict[str, int] = field(default_factory=dict)
    chat_evidence_items: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.exit_code == EXIT_CLEAN

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "total": self.total,
            "answered": self.answered,
            "pending": self.pending,
            "pending_items": self.pending_items,
            "tampered": self.tampered,
            "by_source": self.by_source,
            "chat_evidence_items": self.chat_evidence_items,
        }


def verify_checklist(checklist: dict[str, Any]) -> VerifyReport:
    questions = checklist.get("questions", [])
    total = len(questions)
    answered = [q for q in questions if q.get("status") == "ANSWERED"]
    pending = [q for q in questions if q.get("status") != "ANSWERED"]

    report = VerifyReport(
        exit_code=EXIT_CLEAN,
        total=total,
        answered=len(answered),
        pending=len(pending),
        pending_items=[
            {
                "id": q.get("id"),
                "tier": q.get("tier"),
                "category": q.get("category"),
                "question": (q.get("question") or "")[:160],
            }
            for q in pending
        ],
    )

    for question in answered:
        source = question.get("answered_by") or "UNKNOWN"
        report.by_source[source] = report.by_source.get(source, 0) + 1

        tier = question.get("tier")
        if tier == CRITICAL:
            if source not in ALLOWED_CRITICAL_SOURCES:
                report.tampered.append(
                    f"{question.get('id')}: CRITICAL phải do người dùng trả lời "
                    f"(nguồn '{source}')"
                )
            elif source == "USER_CHAT":
                if not str(question.get("evidence") or "").strip():
                    report.tampered.append(
                        f"{question.get('id')}: USER_CHAT thiếu 'evidence' nguyên văn"
                    )
                else:
                    report.chat_evidence_items.append(question.get("id"))
            elif source == "USER_UI":
                if not str(question.get("nonce") or "").strip():
                    report.tampered.append(
                        f"{question.get('id')}: USER_UI thiếu nonce"
                    )
        else:
            if source not in ALLOWED_STANDARD_SOURCES:
                report.tampered.append(
                    f"{question.get('id')}: STANDARD có nguồn không hợp lệ '{source}'"
                )
            elif source == "USER_CHAT" and not str(question.get("evidence") or "").strip():
                report.tampered.append(
                    f"{question.get('id')}: USER_CHAT thiếu 'evidence' nguyên văn"
                )

    if report.tampered:
        report.exit_code = EXIT_TAMPER
    elif pending:
        report.exit_code = EXIT_PENDING

    return report


def verify_file(checklist_path: str | Path,
                out_path: str | Path | None = None) -> VerifyReport:
    checklist = json.loads(read_text(checklist_path))
    report = verify_checklist(checklist)

    if report.passed:
        payload = {
            "verified": True,
            "checklist_sha256": sha256_text(
                json.dumps(checklist, ensure_ascii=False, sort_keys=True)
            ),
            "report": report.to_dict(),
        }
        target = out_path or Path(checklist_path).with_name("verified.json")
        atomic_write(target, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    return report
