"""utd.lock - Khoá đặc tả sau sign-off của người dùng.

Điều kiện tạo `canonical/locked_spec.json`:
  1. Đã có `interview/verified.json` với `verified: true`
  2. Người dùng đã gõ "Chốt" hoặc "OK" (tham số `--sign`)
  3. Checklist đã sạch (không PENDING, không mục CRITICAL mang nguồn sai)

Sau khi khoá, `lock.sha256` chứa sha256 của locked_spec. Mọi stage sau đối chiếu
và từ chối làm việc nếu lệch (exit 5).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import atomic_write, read_text, sha256_file, sha256_text
from .match.reconcile_checklist import checklist_digest

ACCEPTED_SIGNS = ("chốt", "chot", "ok")


class LockError(Exception):
    """Không đủ điều kiện khoá."""

    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class LockResult:
    locked_spec: Path
    lock_file: Path
    sha256: str
    signoffs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "locked_spec": str(self.locked_spec),
            "lock_file": str(self.lock_file),
            "sha256": self.sha256,
            "signoffs": self.signoffs,
        }


def normalise_sign(text: str) -> str:
    normalised = str(text or "").strip().lower()
    # Bỏ dấu tiếng Việt cho "chốt" -> "chot"
    for accented, plain in (("ố", "o"), ("ó", "o"), ("ô", "o")):
        normalised = normalised.replace(accented, plain)
    return normalised


def is_valid_sign(text: str) -> bool:
    return normalise_sign(text) in ACCEPTED_SIGNS


def _apply_confirmed_flags(spec: dict[str, Any], checklist: dict[str, Any]) -> int:
    """Ghi cờ người dùng đã xác nhận từ checklist vào spec (in place).

    Chỉ ghi cờ có `source == "user"` để không đè giá trị `inferred` của module
    không xuất hiện trong checklist. Trả số module đã cập nhật.
    """
    checklist_modules = {
        str(m.get("id") or ""): m
        for m in checklist.get("modules", [])
        if isinstance(m, dict)
    }
    updated = 0

    for module in spec.get("modules", []):
        source_module = checklist_modules.get(str(module.get("id") or ""))
        if source_module is None:
            continue  # module ngoài checklist -> giữ nguyên cờ trong spec

        flags = source_module.get("flags") or {}
        values = flags.get("values") or {}
        sources = flags.get("sources") or {}

        target = module.setdefault("flags", {})
        target_values = target.setdefault("values", {})
        target_sources = target.setdefault("sources", {})

        changed = False
        for name, source in sources.items():
            if source != "user" or name not in values:
                continue
            target_values[name] = bool(values[name])
            target_sources[name] = "user"
            changed = True
        if changed:
            updated += 1

    return updated


def lock_spec(spec_path: str | Path, checklist_path: str | Path,
              verified_path: str | Path, sign: str,
              out_dir: str | Path) -> LockResult:
    """Kiểm tra điều kiện rồi ghi locked_spec.json + lock.sha256."""
    if not is_valid_sign(sign):
        raise LockError(
            f"Chữ ký xác nhận không hợp lệ: '{sign}'. "
            f"Người dùng phải gõ 'Chốt' hoặc 'OK'."
        )

    verified = Path(verified_path)
    if not verified.exists():
        raise LockError(
            f"Chưa có {verified.name}. Chạy 'utd interview --verify' trước."
        )

    verified_data = json.loads(read_text(verified))
    if not verified_data.get("verified"):
        raise LockError("interview/verified.json không đánh dấu verified=true")

    checklist = json.loads(read_text(checklist_path))

    # (a) Checklist phải còn nguyên như lúc verify — chặn sửa tay sau verify.
    expected_sha = str(verified_data.get("checklist_sha256") or "")
    actual_sha = checklist_digest(checklist)
    if expected_sha and actual_sha != expected_sha:
        raise LockError(
            "checklist.json đã thay đổi sau bước verify.\n"
            f"  sha mong đợi: {expected_sha}\n"
            f"  sha thực tế : {actual_sha}\n"
            "Chạy lại 'utd interview --verify' trước khi khoá."
        )

    pending = [q for q in checklist.get("questions", []) if q.get("status") != "ANSWERED"]
    if pending:
        raise LockError(
            f"Còn {len(pending)} câu hỏi chưa trả lời. Không thể khoá đặc tả."
        )

    # (b) Không khoá khi còn cờ nghiệp vụ chưa được người dùng xác nhận.
    unconfirmed: list[str] = []
    for module in checklist.get("modules", []):
        flags = module.get("flags") or {}
        sources = flags.get("sources") or {}
        for name, source in sources.items():
            if source == "default":
                unconfirmed.append(f"{module.get('sheet_name') or module.get('id')}.{name}")
    if unconfirmed:
        shown = "\n  ".join(unconfirmed[:12])
        more = f"\n  ... và {len(unconfirmed) - 12} cờ khác" if len(unconfirmed) > 12 else ""
        raise LockError(
            f"Còn {len(unconfirmed)} cờ nghiệp vụ chưa được xác nhận:\n  {shown}{more}\n"
            "Trả lời các câu FLAG:* ở stage interview trước khi khoá."
        )

    bad_sources = [
        q for q in checklist.get("questions", [])
        if q.get("tier") == "CRITICAL"
        and q.get("answered_by") not in ("USER_UI", "USER_CHAT")
    ]
    if bad_sources:
        raise LockError(
            f"{len(bad_sources)} câu CRITICAL có nguồn không hợp lệ. Không thể khoá."
        )

    spec = json.loads(read_text(spec_path))

    # (c) Cờ đã xác nhận phải tới được locked_spec — nếu không, generate chạy với
    #     cờ mặc định và mọi điều kiện trên trở nên vô nghĩa.
    _apply_confirmed_flags(spec, checklist)

    # Nhúng bộ câu trả lời vào locked spec để stage sau không phải đọc 2 nguồn.
    spec["interview"] = {
        "locked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "signoff": "USER",
        "answers_sha256": verified_data.get("checklist_sha256"),
        "answers": [
            {
                "id": q["id"],
                "rule_ids": q.get("rule_ids", [q.get("rule_id")]),
                "tier": q.get("tier"),
                "param_name": q.get("param_name"),
                "answer": q.get("answer"),
                "answered_by": q.get("answered_by"),
                "evidence": q.get("evidence"),
            }
            for q in checklist.get("questions", [])
        ],
    }

    target_dir = Path(out_dir)
    locked_path = target_dir / "locked_spec.json"
    lock_file = target_dir / "lock.sha256"

    payload = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
    atomic_write(locked_path, payload)

    digest = sha256_file(locked_path)
    atomic_write(lock_file, digest + "\n")

    return LockResult(
        locked_spec=locked_path,
        lock_file=lock_file,
        sha256=digest,
        signoffs=["USER"],
    )


def verify_lock(locked_spec: str | Path, lock_file: str | Path) -> list[str]:
    """Đối chiếu sha256; trả danh sách vấn đề (rỗng nghĩa là khớp)."""
    problems: list[str] = []
    spec_path = Path(locked_spec)
    lock_path = Path(lock_file)

    if not spec_path.exists():
        problems.append(f"không tìm thấy {spec_path.name}")
    if not lock_path.exists():
        problems.append(f"không tìm thấy {lock_path.name}")
    if problems:
        return problems

    expected = read_text(lock_path).strip()
    actual = sha256_file(spec_path)
    if expected != actual:
        problems.append(
            f"{spec_path.name} bị sửa sau khi khoá: mong đợi {expected[:12]}…, "
            f"thực tế {actual[:12]}…"
        )
    return problems
