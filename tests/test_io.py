"""Test cho utd.io: tiếng Việt trên console Windows, ghi nguyên tử, sha256."""

import io
import os
import sys

import pytest

from utd.io import atomic_write, reconfigure_stdout, sha256_file, sha256_text


def test_atomic_write_creates_parent_and_preserves_vietnamese(tmp_path):
    target = tmp_path / "nested" / "deeper" / "vn.txt"
    text = "Trần Lê Bảo Ánh — Ẩu Ỹ — đặng thị hồng"
    written = atomic_write(target, text)

    assert written == target
    assert target.exists()
    assert target.read_text(encoding="utf-8") == text


def test_atomic_write_replaces_existing_content(tmp_path):
    target = tmp_path / "file.txt"
    atomic_write(target, "cũ")
    atomic_write(target, "mới")

    assert target.read_text(encoding="utf-8") == "mới"


def test_atomic_write_leaves_no_temp_files(tmp_path):
    target = tmp_path / "file.txt"
    atomic_write(target, "nội dung")

    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_atomic_write_keeps_original_on_failure(tmp_path, monkeypatch):
    target = tmp_path / "file.txt"
    atomic_write(target, "bản gốc")

    def boom(*args, **kwargs):
        raise RuntimeError("giả lập lỗi ghi")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(RuntimeError):
        atomic_write(target, "bản mới bị lỗi")

    assert target.read_text(encoding="utf-8") == "bản gốc"
    assert [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")] == []


def test_sha256_file_is_newline_insensitive(tmp_path):
    lf_file = tmp_path / "lf.txt"
    crlf_file = tmp_path / "crlf.txt"
    lf_file.write_bytes(b"a\nb\nc\n")
    crlf_file.write_bytes(b"a\r\nb\r\nc\r\n")

    assert sha256_file(lf_file) == sha256_file(crlf_file)


def test_sha256_file_missing_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        sha256_file(tmp_path / "khong_ton_tai.txt")


def test_sha256_text_normalises_newlines():
    assert sha256_text("a\r\nb") == sha256_text("a\nb")


def test_reconfigure_stdout_handles_cp437(monkeypatch):
    """Giả lập console cp437 rồi in tiếng Việt.

    Trước khi sửa, print() ném UnicodeEncodeError vì stream mã hoá cp437
    không chứa được 'ầ', 'ả'...
    """
    buffer = io.BytesIO()
    cp437_stream = io.TextIOWrapper(buffer, encoding="cp437")
    monkeypatch.setattr(sys, "stdout", cp437_stream)

    reconfigure_stdout()
    print("Trần Lê Bảo Ánh — Ẩu Ỹ")
    sys.stdout.flush()

    assert buffer.getvalue().decode("utf-8").strip() == "Trần Lê Bảo Ánh — Ẩu Ỹ"


def test_reconfigure_stdout_tolerates_unreconfigurable_stream(monkeypatch):
    """Stream không hỗ trợ reconfigure (vd pytest capture) không được làm nổ."""

    class Opaque:
        def write(self, _text):
            return None

    monkeypatch.setattr(sys, "stdout", Opaque())
    reconfigure_stdout()  # không được ném
