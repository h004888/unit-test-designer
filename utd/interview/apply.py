"""utd.interview.apply - Áp câu trả lời vào checklist, kiểm chữ ký.

Ba nguồn hợp lệ:
  USER_UI        - có `sig` khớp sha256(id|value|nonce|salt)     (giao diện sinh)
  USER_CHAT      - có `evidence` là nguyên văn người dùng gửi      (không có sig)
  STANDARD_BATCH - chỉ áp dụng cho tier STANDARD (phê duyệt theo lô)

Mọi mục KHÔNG hợp lệ -> toàn bộ file bị từ chối, không mục nào được ghi.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..io import atomic_write, read_text
from ..match.flags_questions import coerce_flag_value
from .signature import verify_signature


class TamperError(Exception):
    """File answers không hợp lệ: chữ ký sai, thiếu nonce, hoặc nguồn không được phép."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class ApplyResult:
    applied: int = 0
    skipped_unknown: list[str] = field(default_factory=list)
    by_source: dict[str, int] = field(default_factory=dict)
    regenerated_from_flags: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "skipped_unknown": self.skipped_unknown,
            "by_source": self.by_source,
            "regenerated_from_flags": self.regenerated_from_flags,
        }


def _flag_of(question: dict[str, Any]) -> tuple[str, bool | None] | None:
    """Trả (tên cờ, giá trị hiện tại) nếu mục là câu hỏi cờ."""
    from ..match.flags_questions import parse_flag_rule_id, parse_flag_target

    name = parse_flag_rule_id(str(question.get("rule_id") or ""))
    if name is None:
        name = parse_flag_target(question.get("target"))
    if name is None:
        return None
    current = question.get("flag_current")
    return name, (bool(current) if isinstance(current, bool) else None)


def _apply_flag_updates(checklist: dict[str, Any],
                        updates: list[tuple[str, str, bool]]) -> None:
    """Ghi giá trị cờ vào `checklist.modules[]` với nguồn `user`."""
    if not updates:
        return
    modules = {str(m.get("id") or ""): m for m in checklist.get("modules", [])}
    for module_id, name, value in updates:
        module = modules.get(module_id)
        if module is None:
            continue
        flags = module.setdefault("flags", {})
        values = flags.setdefault("values", {})
        sources = flags.setdefault("sources", {})
        values[name] = value
        sources[name] = "user"


def _load(path: str | Path) -> dict[str, Any]:
    data = json.loads(read_text(path))
    if not isinstance(data, dict):
        raise TamperError(["answers.json phải là một object"])
    return data


def apply_answers(checklist_path: str | Path, answers_path: str | Path,
                  out_path: str | Path | None = None) -> ApplyResult:
    """Áp answers vào checklist. Ném TamperError nếu bất kỳ mục nào không hợp lệ."""
    checklist = json.loads(read_text(checklist_path))
    answers_doc = _load(answers_path)

    salt = str(answers_doc.get("salt") or "")
    if not salt:
        raise TamperError(["answers.json thiếu 'salt' — file không do giao diện sinh"])

    questions = {q["id"]: q for q in checklist.get("questions", [])}
    items = answers_doc.get("answers")
    if not isinstance(items, list) or not items:
        raise TamperError(["answers.json không có mục trả lời nào"])

    # Mục đã biến mất do cờ thay đổi: bỏ qua CÓ KIỂM SOÁT.
    # Chỉ bỏ qua khi answers mang sha của checklist NGAY TRƯỚC lần sinh lại,
    # để phân biệt "câu hỏi biến mất hợp lệ" với "id rác do sửa tay".
    removed_ids = {
        entry.get("id")
        for entry in checklist.get("removed_questions", [])
        if isinstance(entry, dict)
    }
    previous_sha = str(checklist.get("previous_sha256") or "")
    reported_sha = str(answers_doc.get("checklist_sha256") or "")
    skippable_ids = removed_ids & {str(i.get("id")) for i in items if isinstance(i, dict)} \
        if previous_sha and reported_sha == previous_sha else set()

    problems: list[str] = []
    prepared: list[tuple[str, str, str]] = []  # (question_id, value, source)
    skipped_removed: list[str] = []

    for index, item in enumerate(items):
        prefix = f"answers[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{prefix}: phải là object")
            continue

        question_id = str(item.get("id") or "")
        if not question_id:
            problems.append(f"{prefix}: thiếu 'id'")
            continue

        question = questions.get(question_id)
        if question is None:
            if question_id in skippable_ids:
                skipped_removed.append(question_id)
                continue
            problems.append(f"{prefix}: id '{question_id}' không có trong checklist")
            continue

        value = item.get("value")
        if value is None or not str(value).strip():
            problems.append(f"{prefix} ({question_id}): 'value' rỗng")
            continue

        nonce = str(item.get("nonce") or "")
        if not nonce:
            problems.append(f"{prefix} ({question_id}): thiếu 'nonce'")
            continue
        if nonce != question.get("nonce"):
            problems.append(f"{prefix} ({question_id}): nonce không khớp checklist")
            continue

        sig = str(item.get("sig") or "")
        if not verify_signature(question_id, str(value), nonce, salt, sig):
            problems.append(f"{prefix} ({question_id}): chữ ký sai — nội dung đã bị sửa")
            continue

        prepared.append((question_id, str(value), "USER_UI"))

    if problems:
        raise TamperError(problems)

    result = ApplyResult(skipped_unknown=skipped_removed)
    flag_updates: list[tuple[str, str, bool]] = []  # (module_id, flag_name, value)

    for question_id, value, source in prepared:
        question = questions[question_id]
        question["status"] = "ANSWERED"
        question["answer"] = value
        question["answered_by"] = source
        question["evidence"] = None
        result.by_source[source] = result.by_source.get(source, 0) + 1
        result.applied += 1

        if (flag := _flag_of(question)) is not None:
            name, current = flag
            coerced = coerce_flag_value(value, current=current)
            if coerced is None:
                raise TamperError(
                    [f"{question_id}: không đọc được giá trị cờ từ '{value}' "
                     f"(dùng Có/Không hoặc Đồng ý/Sửa thành ...)"]
                )
            flag_updates.append((str(question.get("module_id") or ""), name, coerced))

    _apply_flag_updates(checklist, flag_updates)
    _recompute(checklist)
    _persist(checklist, out_path or checklist_path, answers_doc.get("salt"))
    result.regenerated_from_flags = bool(flag_updates)
    return result


def apply_chat_answer(checklist_path: str | Path, question_id: str, value: str,
                      evidence: str, out_path: str | Path | None = None) -> ApplyResult:
    """Ghi một câu trả lời qua hội thoại, BẮT BUỘC có nguyên văn `evidence`."""
    if not str(evidence or "").strip():
        raise TamperError(
            [f"{question_id}: đường USER_CHAT bắt buộc có 'evidence' là nguyên văn người dùng gửi"]
        )
    if not str(value or "").strip():
        raise TamperError([f"{question_id}: 'value' rỗng"])

    checklist = json.loads(read_text(checklist_path))
    questions = {q["id"]: q for q in checklist.get("questions", [])}

    question = questions.get(question_id)
    if question is None:
        raise TamperError([f"id '{question_id}' không có trong checklist"])

    question["status"] = "ANSWERED"
    question["answer"] = str(value)
    question["answered_by"] = "USER_CHAT"
    question["evidence"] = str(evidence)

    regenerated = False
    flag = _flag_of(question)
    if flag is not None:
        name, current = flag
        coerced = coerce_flag_value(value, current=current)
        if coerced is None:
            raise TamperError(
                [f"{question_id}: không đọc được giá trị cờ từ '{value}' "
                 f"(dùng Có/Không hoặc Đồng ý/Sửa thành ...)"]
            )
        _apply_flag_updates(
            checklist, [(str(question.get("module_id") or ""), name, coerced)]
        )
        regenerated = True

    _recompute(checklist)
    _persist(checklist, out_path or checklist_path, None)
    return ApplyResult(
        applied=1,
        by_source={"USER_CHAT": 1},
        regenerated_from_flags=regenerated,
    )


def apply_batch_consent(checklist_path: str | Path,
                        out_path: str | Path | None = None) -> ApplyResult:
    """Phê duyệt theo lô cho toàn bộ câu STANDARD còn PENDING.

    KHÔNG được chấp nhận câu CRITICAL: chúng bắt buộc trả lời trực tiếp.
    """
    checklist = json.loads(read_text(checklist_path))
    result = ApplyResult()

    for question in checklist.get("questions", []):
        if question.get("tier") != "STANDARD":
            continue
        if question.get("status") != "PENDING":
            continue
        question["status"] = "ANSWERED"
        question["answer"] = question.get("recommended_option", "")
        question["answered_by"] = "STANDARD_BATCH"
        question["evidence"] = None
        result.by_source["STANDARD_BATCH"] = result.by_source.get("STANDARD_BATCH", 0) + 1
        result.applied += 1

    _recompute(checklist)
    _persist(checklist, out_path or checklist_path, None)
    return result


def _recompute(checklist: dict[str, Any]) -> None:
    questions = checklist.get("questions", [])
    answered = sum(1 for q in questions if q.get("status") == "ANSWERED")
    pending_critical = [
        q for q in questions
        if q.get("tier") == "CRITICAL" and q.get("status") == "PENDING"
    ]
    checklist.setdefault("api", {})["answered_count"] = answered
    checklist["api"]["pending_count"] = len(questions) - answered
    checklist["session_state"] = (
        "ALL_COMPLETED" if not pending_critical else "INTERACTION_IN_PROGRESS"
    )


def _persist(checklist: dict[str, Any], path: str | Path,
             salt: str | None) -> None:
    if salt:
        checklist["answers_salt"] = salt
    atomic_write(path, json.dumps(checklist, ensure_ascii=False, indent=2) + "\n")
