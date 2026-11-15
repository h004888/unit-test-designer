"""utd.match.reconcile_checklist - Sinh lại checklist kiểu append-merge.

Vấn đề: khi người dùng trả lời câu cờ, một số rule mới áp dụng và cần câu hỏi
mới; một số rule khác ngừng áp dụng và câu hỏi của chúng phải biến mất. Nếu
rebuild toàn bộ checklist, `nonce` đổi -> mọi chữ ký cũ trong `answers.json`
vô hiệu (vì `sig = sha256(id|value|nonce|salt)`).

Giải pháp (design.md D2/D3): giữ NGUYÊN ĐỐI TƯỢNG các mục đã tồn tại, chỉ thêm
mục mới. Mục biến mất được ghi vào `removed_questions` kèm lý do, không xoá
hẳn — để `apply` phân biệt "câu hỏi biến mất do cờ đổi" với "id rác do sửa tay".
"""

from __future__ import annotations

from typing import Any

from ..io import sha256_text
import json


def checklist_digest(checklist: dict[str, Any]) -> str:
    """Sha256 của checklist theo đúng quy ước `verify_file` dùng.

    `verify_file` tính trên `json.dumps(checklist, sort_keys=True)` — dùng cùng
    công thức để hai bên so sánh được.
    """
    return sha256_text(json.dumps(checklist, ensure_ascii=False, sort_keys=True))


def _index_by_id(questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {q["id"]: q for q in questions if isinstance(q, dict) and q.get("id")}


def reconcile_checklist(
    old_checklist: dict[str, Any] | None,
    new_checklist: dict[str, Any],
    removed_reason: str = "",
) -> dict[str, Any]:
    """Merge `new_checklist` vào `old_checklist` theo id.

    - Mục có trong cả hai: giữ NGUYÊN đối tượng từ `old` (nonce, status, answer...).
    - Mục chỉ có trong `new`: thêm vào cuối.
    - Mục chỉ có trong `old`: ghi vào `removed_questions` kèm lý do.

    Trả về checklist mới đã merge, có `previous_sha256` và `removed_questions`.
    """
    if not old_checklist:
        result = dict(new_checklist)
        result.setdefault("removed_questions", [])
        return result

    old_questions = list(old_checklist.get("questions", []))
    new_questions = list(new_checklist.get("questions", []))
    old_by_id = _index_by_id(old_questions)
    new_ids = {q["id"] for q in new_questions if isinstance(q, dict) and q.get("id")}

    merged: list[dict[str, Any]] = []
    added_ids: list[str] = []

    # Trường thuộc về NHÓM câu hỏi: lấy từ bản mới để nội dung nhóm luôn tươi
    # (rule_ids mở rộng khi cờ bật).
    GROUP_FIELDS = ("rule_id", "rule_ids", "tier", "question", "questions",
                    "category", "dimension")

    for question in new_questions:
        qid = question.get("id")
        previous = old_by_id.get(qid) if qid else None
        if previous is not None:
            merged_question = dict(previous)  # id, nonce, status, answer, evidence
            for field_name in GROUP_FIELDS:
                if field_name in question:
                    merged_question[field_name] = question[field_name]
            merged.append(merged_question)
        else:
            merged.append(question)
            if qid:
                added_ids.append(qid)

    removed: list[dict[str, Any]] = [
        {
            "id": qid,
            "rule_id": old_by_id[qid].get("rule_id"),
            "removed_reason": removed_reason or "câu hỏi không còn áp dụng",
        }
        for qid in old_by_id
        if qid not in new_ids
    ]

    result = dict(new_checklist)
    result["questions"] = merged
    result["removed_questions"] = removed
    result["previous_sha256"] = checklist_digest(old_checklist)
    result["added_question_ids"] = added_ids
    return result


def added_question_ids(old_checklist: dict[str, Any] | None,
                       new_checklist: dict[str, Any]) -> list[str]:
    """Id câu hỏi mới so với checklist cũ."""
    if not old_checklist:
        return []
    old_ids = {q["id"] for q in old_checklist.get("questions", [])
               if isinstance(q, dict) and q.get("id")}
    return [
        q["id"] for q in new_checklist.get("questions", [])
        if isinstance(q, dict) and q.get("id") and q["id"] not in old_ids
    ]


def has_answered(old_checklist: dict[str, Any] | None) -> bool:
    if not old_checklist:
        return False
    return any(
        q.get("status") == "ANSWERED"
        for q in old_checklist.get("questions", [])
        if isinstance(q, dict)
    )


def expanded_answered_questions(
    old_checklist: dict[str, Any] | None,
    new_checklist: dict[str, Any],
) -> list[tuple[str, list[str]]]:
    """Câu đã trả lời mà `rule_ids` mở rộng sau lần sinh lại.

    Trả `[(question_id, added_rule_ids)]`. Chỉ xét câu `ANSWERED` ở checklist
    cũ; câu PENDING không cần cảnh báo vì người dùng sẽ trả lời một lần cho cả
    nhóm. Đây là hệ quả trực tiếp của việc id ổn định (design D3 của
    `stabilize-question-ids`): câu giữ nguyên nhưng phạm vi mở rộng.
    """
    if not old_checklist:
        return []

    old_by_id = {
        q["id"]: q
        for q in old_checklist.get("questions", [])
        if isinstance(q, dict) and q.get("id")
    }

    expanded: list[tuple[str, list[str]]] = []
    for question in new_checklist.get("questions", []):
        if not isinstance(question, dict):
            continue
        qid = question.get("id")
        previous = old_by_id.get(qid) if qid else None
        if previous is None or previous.get("status") != "ANSWERED":
            continue

        old_rules = previous.get("rule_ids") or [previous.get("rule_id")]
        new_rules = question.get("rule_ids") or [question.get("rule_id")]
        added = [r for r in new_rules if r and r not in old_rules]
        if added:
            expanded.append((qid, added))

    return expanded
