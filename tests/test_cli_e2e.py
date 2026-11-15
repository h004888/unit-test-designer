"""Test end-to-end bằng subprocess: ingest -> inventory -> interview -> lock -> generate -> audit -> emit."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "utd", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


RECORD = Path(__file__).parent / "conftest.py"


def _record(workspace: Path) -> None:
    """Sinh answers.json bằng chữ ký thật rồi apply.

    Ghi một script nhỏ trong workspace rồi chạy để mô phỏng giao diện ký.
    """
    script = workspace / "_sign.py"
    script.write_text(
        "import json, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from pathlib import Path\n"
        "from utd.interview.signature import make_salt, signature\n"
        "from utd.interview.apply import apply_answers, apply_batch_consent\n"
        "ws = Path(sys.argv[1])\n"
        "checklist = json.loads((ws / '.unittest-design/interview/checklist.json').read_text(encoding='utf-8'))\n"
        "salt = make_salt()\n"
        "answers = []\n"
        "for q in checklist['questions']:\n"
        "    if q['tier'] != 'CRITICAL':\n"
        "        continue\n"
        "    # Câu hỏi cờ cần giá trị boolean đọc được; câu rule dùng câu trả lời chung.\n"
        "    if str(q.get('rule_id', '')).startswith('FLAG:'):\n"
        "        value = 'Không'\n"
        "    else:\n"
        "        value = 'theo đặc tả'\n"
        "    answers.append({'id': q['id'], 'value': value, 'nonce': q['nonce'],\n"
        "                    'sig': signature(q['id'], value, q['nonce'], salt)})\n"
        "doc = {'schema_version': 1, 'salt': salt, 'answers': answers}\n"
        "answers_path = ws / '.unittest-design/interview/answers.json'\n"
        "answers_path.write_text(json.dumps(doc), encoding='utf-8')\n"
        "apply_answers(ws / '.unittest-design/interview/checklist.json', answers_path)\n"
        "apply_batch_consent(ws / '.unittest-design/interview/checklist.json')\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(script), str(workspace)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert result.returncode == 0, result.stderr


def test_full_pipeline_exit_zero(tmp_path):
    result = _run(["ingest", "--from", "utd-v1", "--in", str(LEGACY)], tmp_path)
    assert result.returncode == 0, result.stderr

    result = _run(["inventory"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "150/150" in result.stdout

    _record(tmp_path)

    result = _run(["interview", "--verify"], tmp_path)
    assert result.returncode == 0, result.stderr

    result = _run(["lock", "--sign", "Chốt"], tmp_path)
    assert result.returncode == 0, result.stderr

    result = _run(["generate"], tmp_path)
    assert result.returncode == 0, result.stderr

    result = _run(["audit"], tmp_path)
    assert result.returncode == 0, result.stderr

    result = _run([
        "emit",
        "--xlsx", ".unittest-design/unit_test.xlsx",
        "--md-dir", ".unittest-design/docs",
    ], tmp_path)
    assert result.returncode == 0, result.stderr

    design = tmp_path / ".unittest-design"
    assert (design / "canonical" / "locked_spec.json").exists()
    assert (design / "canonical" / "unit_test_spec.json").exists()
    assert (design / "audit" / "report.json").exists()
    assert (design / "unit_test.xlsx").exists()
    assert (design / "docs" / "index.md").exists()

    state = json.loads((design / "run.json").read_text(encoding="utf-8"))
    assert state["stage"] == "emit"


def test_emit_before_audit_fails(tmp_path):
    _run(["ingest", "--from", "utd-v1", "--in", str(LEGACY)], tmp_path)
    _run(["inventory"], tmp_path)
    _run(["generate", "--source", ".unittest-design/canonical/spec.json"], tmp_path)
    result = _run(["emit", "--xlsx", ".unittest-design/x.xlsx"], tmp_path)

    assert result.returncode == 1, result.stderr
    assert not (tmp_path / ".unittest-design" / "x.xlsx").exists()


def test_emit_without_ssot_exit_2(tmp_path):
    _run(["ingest", "--from", "utd-v1", "--in", str(LEGACY)], tmp_path)
    result = _run(["emit", "--xlsx", ".unittest-design/x.xlsx"], tmp_path)

    assert result.returncode == 2


def test_generate_without_spec_fails(tmp_path):
    result = _run(["generate"], tmp_path)
    assert result.returncode == 2


def test_lock_without_verify_fails(tmp_path):
    _run(["ingest", "--from", "utd-v1", "--in", str(LEGACY)], tmp_path)
    _run(["inventory"], tmp_path)

    result = _run(["lock", "--sign", "Chốt"], tmp_path)
    assert result.returncode == 1


def test_help_lists_eight_stages(tmp_path):
    result = _run(["--help"], tmp_path)
    assert result.returncode == 0
    for stage in ("ingest", "inventory", "interview", "lock",
                  "generate", "audit", "emit", "reconcile"):
        assert stage in result.stdout


def test_cli_prints_vietnamese_on_windows(tmp_path):
    result = _run(["--help"], tmp_path)
    assert "UnicodeEncodeError" not in result.stderr
    assert "chuẩn hoá" in result.stdout or "chuan hoa" in result.stdout
