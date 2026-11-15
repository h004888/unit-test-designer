"""utd.interview.signature - Chữ ký câu trả lời, thay thế cơ chế tin `answered_by`.

Bản cũ: `--answered-by` có default `USER`, nên AI tự gọi `--answer-id` là đủ để
`verify_gate` PASS. Đó là self-report, không có gì kiểm chứng.

Bản mới: giao diện `interview.html` sinh `salt` riêng cho mỗi lần xuất và ký
    sig = sha256(id | value | nonce | salt)
`apply` tính lại và từ chối mọi mục lệch (exit 4). AI không có salt (salt chỉ
sống trong trình duyệt) nên không tạo được chữ ký hợp lệ.
"""

from __future__ import annotations

import hashlib
import secrets

NONCE_BYTES = 16
SALT_BYTES = 16


def make_salt() -> str:
    return secrets.token_hex(SALT_BYTES)


def make_nonce() -> str:
    return secrets.token_hex(NONCE_BYTES)


def signature(question_id: str, value: str, nonce: str, salt: str) -> str:
    """sha256 của (id|value|nonce|salt), chuẩn hoá khoảng trắng và newline."""
    payload = "|".join(
        [
            str(question_id).strip(),
            str(value).replace("\r\n", "\n").replace("\r", "\n").strip(),
            str(nonce).strip(),
            str(salt).strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_signature(question_id: str, value: str, nonce: str, salt: str,
                     provided: str) -> bool:
    if not provided:
        return False
    expected = signature(question_id, value, nonce, salt)
    return secrets.compare_digest(expected, str(provided).strip().lower())
