"""Test CLI ingest end-to-end: exit code phân loại 0/2/3."""

import json
from pathlib import Path

import pytest

from utd.cli import (
    EXIT_INSUFFICIENT_INFO,
    EXIT_INVALID_INPUT,
    EXIT_PASS,
    main,
)

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def test_ingest_legacy_exit_0(tmp_path):
    out = tmp_path / "spec.json"
    code = main([
        "ingest", "--from", "utd-v1", "--in", str(LEGACY), "--out", str(out)
    ])

    assert code == EXIT_PASS
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema_version"] == "2.0"
    assert len(data["modules"]) == 2


def test_ingest_openapi_exit_0(tmp_path):
    pytest.importorskip("yaml")
    out = tmp_path / "spec.json"
    code = main([
        "ingest", "--from", "openapi",
        "--in", str(FIXTURES / "openapi_minimal.yaml"),
        "--out", str(out),
    ])

    assert code == EXIT_PASS
    assert out.exists()


def test_ingest_missing_file_exit_2(tmp_path):
    code = main(["ingest", "--from", "utd-v1", "--in", str(tmp_path / "nope.json")])
    assert code == EXIT_INVALID_INPUT


def test_ingest_malformed_json_exit_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    code = main(["ingest", "--from", "utd-v1", "--in", str(bad),
                 "--out", str(tmp_path / "out.json")])
    assert code == EXIT_INVALID_INPUT


def test_ingest_no_modules_exit_2(tmp_path):
    spec = tmp_path / "empty.json"
    spec.write_text(json.dumps({"project": {}}), encoding="utf-8")
    out = tmp_path / "out.json"
    code = main(["ingest", "--from", "utd-v1", "--in", str(spec), "--out", str(out)])

    assert code == EXIT_INVALID_INPUT
    assert not out.exists()


def test_ingest_no_args_exit_2():
    assert main(["ingest"]) == EXIT_INVALID_INPUT


def test_ingest_unknown_kind_rejected_by_argparse():
    with pytest.raises(SystemExit):
        main(["ingest", "--from", "khong_ho_tro", "--in", "x"])


def test_ingest_draft_incomplete_exit_3(tmp_path):
    draft = tmp_path / "draft.json"
    draft.write_text(
        json.dumps({"modules": [{"module_name": "X", "endpoints": []}]}),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    code = main(["ingest", "--from", "draft", "--in", str(draft), "--out", str(out)])

    assert code == EXIT_INSUFFICIENT_INFO
    assert not out.exists()


def test_ingest_does_not_overwrite_on_error(tmp_path):
    existing = tmp_path / "out.json"
    existing.write_text('{"giu_nguyen": true}', encoding="utf-8")

    code = main(["ingest", "--from", "utd-v1",
                 "--in", str(tmp_path / "nope.json"),
                 "--out", str(existing)])

    assert code == EXIT_INVALID_INPUT
    assert existing.read_text(encoding="utf-8") == '{"giu_nguyen": true}'
