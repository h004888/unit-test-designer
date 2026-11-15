"""utd.state - run.json: trạng thái từng stage và chuỗi hash của artifact.

Chuỗi hash là cơ chế chống sửa tay: stage sau đối chiếu sha256 của artifact
với giá trị đã ghi ở stage trước. Lệch -> exit 5 (hash mismatch).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import atomic_write, sha256_file

RUN_FILE_NAME = "run.json"

STAGE_ORDER = (
    "ingest",
    "inventory",
    "interview",
    "lock",
    "generate",
    "audit",
    "emit",
    "reconcile",
)


class HashMismatchError(Exception):
    """Artifact đã bị sửa so với giá trị ghi trong run.json."""

    def __init__(self, artifacts: list[tuple[str, str, str]]):
        self.artifacts = artifacts
        detail = "; ".join(
            f"{name}: mong đợi {expected}, thực tế {actual}"
            for name, expected, actual in artifacts
        )
        super().__init__(f"Hash mismatch - {detail}")


def empty_state() -> dict[str, Any]:
    return {
        "stage": None,
        "version": 1,
        "artifacts": {},
        "gates": {},
        "updated_at": None,
        # Marker tự khai: "none" cho ingest->emit, "read" sau reconcile.
        # KHÔNG phải bằng chứng kiểm chứng được — xem SCHEMA.md mục 7.
        "source_access": "none",
    }


def run_path(workspace: str | Path) -> Path:
    return Path(workspace) / ".unittest-design" / RUN_FILE_NAME


def load_state(workspace: str | Path) -> dict[str, Any]:
    """Đọc run.json; trả state rỗng nếu chưa có file."""
    path = run_path(workspace)
    if not path.exists():
        return empty_state()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        return empty_state()
    state = empty_state()
    state.update(data)
    return state


def save_state(workspace: str | Path, state: dict[str, Any]) -> Path:
    state = dict(state)
    state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return atomic_write(run_path(workspace), payload)


def record_artifact(
    workspace: str | Path,
    state: dict[str, Any],
    name: str,
    path: str | Path,
) -> dict[str, Any]:
    """Ghi sha256 của artifact vào state (chưa persist)."""
    digest = sha256_file(path)
    state.setdefault("artifacts", {})[name] = {
        "path": str(path),
        "sha256": digest,
    }
    return state


def record_gate(state: dict[str, Any], gate: str, passed: bool,
                issues: list[str] | None = None) -> dict[str, Any]:
    state.setdefault("gates", {})[gate] = {
        "passed": bool(passed),
        "issues": list(issues or []),
    }
    return state


def mark_stage(workspace: str | Path, state: dict[str, Any], stage: str,
               source_access: str | None = None) -> Path:
    if stage not in STAGE_ORDER:
        raise ValueError(f"Stage không hợp lệ: {stage}")
    state["stage"] = stage
    if source_access is not None:
        state["source_access"] = source_access
    return save_state(workspace, state)


def verify_artifacts(
    workspace: str | Path,
    state: dict[str, Any] | None = None,
    names: list[str] | None = None,
) -> list[tuple[str, str, str]]:
    """Đối chiếu sha256 hiện tại với giá trị đã ghi.

    Trả danh sách (name, expected, actual) cho mọi artifact bị lệch hoặc biến mất.
    Danh sách rỗng nghĩa là tất cả khớp.
    """
    if state is None:
        state = load_state(workspace)

    recorded = state.get("artifacts", {})
    checked = names if names is not None else list(recorded)
    problems: list[tuple[str, str, str]] = []

    for name in checked:
        entry = recorded.get(name)
        if not entry:
            problems.append((name, "chưa ghi nhận", "không có trong run.json"))
            continue
        stored_path = entry.get("path", "")
        expected = entry.get("sha256", "")
        candidate = _resolve_artifact_path(workspace, stored_path, name)
        if candidate is None or not candidate.exists():
            problems.append((name, expected, "file không tồn tại"))
            continue
        actual = sha256_file(candidate)
        if actual != expected:
            problems.append((name, expected, actual))

    return problems


def require_artifacts(
    workspace: str | Path,
    names: list[str],
    state: dict[str, Any] | None = None,
) -> None:
    """Ném HashMismatchError nếu bất kỳ artifact nào trong `names` bị lệch."""
    problems = verify_artifacts(workspace, state=state, names=names)
    if problems:
        raise HashMismatchError(problems)


def _resolve_artifact_path(workspace: str | Path, stored_path: str, name: str) -> Path | None:
    if not stored_path:
        return None
    candidate = Path(stored_path)
    if candidate.is_absolute():
        return candidate
    # Đường dẫn tương đối: ưu tiên đường dẫn đã ghi (tương đối workspace).
    relative = Path(workspace) / candidate
    if relative.exists():
        return relative
    return relative
