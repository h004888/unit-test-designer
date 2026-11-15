"""utd.install_skill - Cài tài liệu skill vào thư mục cấu hình Claude Code.

Vì sao là lệnh riêng chứ không tự chạy khi `pip install`: ghi vào `~/.claude/`
là vượt ranh giới của package; người dùng phải chủ động.

Nguồn: `utd/_data/skill/` (đọc qua `importlib.resources` để chạy được cả khi
package nằm trong zip).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any

SKILL_DIR_NAME = "unit-test-designer"
DEFAULT_TARGET = Path.home() / ".claude" / "skills" / SKILL_DIR_NAME

REQUIRED_FRONTMATTER = ("name:", "allowed-tools:")


class InstallError(Exception):
    def __init__(self, message: str, exit_code: int = 1):
        self.exit_code = exit_code
        super().__init__(message)


@dataclass
class InstallResult:
    target: Path
    written: list[str] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": str(self.target),
            "written": self.written,
            "dry_run": self.dry_run,
        }


def skill_source() -> Any:
    """Traversable trỏ `utd/_data/skill`."""
    return files("utd") / "_data" / "skill"


def validate_source(source: Any | None = None) -> None:
    """Kiểm nguồn có SKILL.md và frontmatter bắt buộc."""
    source = source or skill_source()

    skill_md = source / "SKILL.md"
    if not skill_md.is_file():
        raise InstallError(f"Không tìm thấy SKILL.md trong {source}")

    header = skill_md.read_text(encoding="utf-8")[:800]
    if not header.startswith("---"):
        raise InstallError("SKILL.md thiếu frontmatter YAML ở đầu file")

    missing = [token for token in REQUIRED_FRONTMATTER if token not in header]
    if missing:
        raise InstallError(
            "SKILL.md thiếu trường bắt buộc: " + ", ".join(t.rstrip(":") for t in missing)
        )


def _walk(node: Any, prefix: str = ""):
    """Sinh (đường dẫn tương đối, Traversable) cho mọi file, đệ quy."""
    for entry in sorted(node.iterdir(), key=lambda p: p.name):
        rel = f"{prefix}/{entry.name}" if prefix else entry.name
        if entry.is_dir():
            yield from _walk(entry, rel)
        else:
            yield rel, entry


def install_skill(target: str | Path | None = None, force: bool = False,
                  dry_run: bool = False) -> InstallResult:
    """Copy toàn bộ `utd/_data/skill` sang `target`."""
    dest = Path(target).expanduser().resolve() if target else DEFAULT_TARGET
    source = skill_source()

    validate_source(source)

    if dest.exists() and not force:
        raise InstallError(
            f"Thư mục đích đã tồn tại: {dest}\n"
            f"Dùng --force để ghi đè, hoặc --target <thư mục khác>."
        )

    files_to_write = list(_walk(source))
    result = InstallResult(target=dest, dry_run=dry_run)

    for rel, node in files_to_write:
        result.written.append(rel)
        if dry_run:
            continue
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(node.read_bytes())

    if not dry_run:
        # Giữ quyền đọc cho mọi người dùng trên máy, tránh file chỉ root đọc được
        for rel in result.written:
            try:
                os.chmod(dest / rel, 0o644)
            except OSError:
                pass

    return result
