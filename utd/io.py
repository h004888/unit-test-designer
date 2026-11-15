"""utd.io - I/O an toàn: UTF-8 stdout, ghi nguyên tử, sha256.

Mục tiêu: mọi lệnh `utd` in được tiếng Việt trên console Windows mặc định
(code page 437/1252) và không bao giờ để lại artifact ở trạng thái nửa vời.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path


def reconfigure_stdout() -> None:
    """Ép stdout/stderr sang UTF-8 để không ném UnicodeEncodeError trên cp437.

    Gọi hàm này ngay đầu mọi entry point. Không phụ thuộc biến môi trường
    PYTHONUTF8; hoạt động với cả khi bị chạy dưới `python -I`.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            # Stream bị bọc bởi thứ khác (vd pytest capture) -> bỏ qua.
            pass


def atomic_write(path: str | Path, text: str, encoding: str = "utf-8") -> Path:
    """Ghi file qua file tạm cùng thư mục rồi thay thế nguyên tử.

    Đảm bảo: nếu tiến trình bị ngắt giữa chừng, file đích giữ nguyên nội dung cũ.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, target)
    except BaseException:
        # Dọn file tạm nếu bất kỳ lỗi nào xảy ra trước khi replace.
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def atomic_write_bytes(path: str | Path, data: bytes) -> Path:
    """Như atomic_write nhưng cho nội dung nhị phân (vd .xlsx)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return target


def read_text(path: str | Path, encoding: str = "utf-8") -> str:
    """Đọc text UTF-8, luôn chuẩn hoá CRLF về LF để hash ổn định."""
    data = Path(path).read_text(encoding=encoding)
    return data.replace("\r\n", "\n").replace("\r", "\n")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hash văn bản ASCII-sạch qua UTF-8, chuẩn hoá newline trước khi hash."""
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash nội dung file; text được chuẩn hoá newline để hash không phụ thuộc OS."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Không tìm thấy file để hash: {p}")
    raw = p.read_bytes()
    # Chuẩn hoá newline trên byte để kết quả giống nhau giữa Windows/Unix.
    normalised = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(normalised).hexdigest()
