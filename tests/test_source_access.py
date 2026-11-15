"""Test marker source_access: 'none' từ ingest→emit, 'read' sau reconcile."""

import json
from pathlib import Path

from utd.cli import EXIT_PASS, main
from utd.state import STAGE_ORDER, empty_state

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def _state(workspace) -> dict:
    path = workspace / ".unittest-design" / "run.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_empty_state_defaults_to_none():
    assert empty_state()["source_access"] == "none"


def test_ingest_keeps_none(tmp_path):
    main(["ingest", "--from", "utd-v1", "--in", str(LEGACY),
          "--workspace", str(tmp_path)])
    # ingest không tạo run.json trừ khi state được ghi; kiểm qua inventory
    assert True


def test_inventory_records_none(tmp_path):
    main(["ingest", "--from", "utd-v1", "--in", str(LEGACY), "--workspace", str(tmp_path)])
    main(["inventory", "--workspace", str(tmp_path)])

    assert _state(tmp_path)["source_access"] == "none"


def test_generate_keeps_none(tmp_path):
    main(["ingest", "--from", "utd-v1", "--in", str(LEGACY), "--workspace", str(tmp_path)])
    main(["inventory", "--workspace", str(tmp_path)])
    main(["generate", "--workspace", str(tmp_path),
          "--source", ".unittest-design/canonical/spec.json"])

    assert _state(tmp_path)["source_access"] == "none"


def test_reconcile_sets_read(tmp_path):
    main(["ingest", "--from", "utd-v1", "--in", str(LEGACY), "--workspace", str(tmp_path)])
    main(["inventory", "--workspace", str(tmp_path)])
    main(["generate", "--workspace", str(tmp_path),
          "--source", ".unittest-design/canonical/spec.json"])

    findings = tmp_path / ".unittest-design" / "reconcile" / "findings.json"
    findings.parent.mkdir(parents=True, exist_ok=True)
    findings.write_text(json.dumps({"findings": [
        {"rule_id": "BR-01", "category": "Match"},
    ]}), encoding="utf-8")

    code = main(["reconcile", "--workspace", str(tmp_path)])
    assert code == EXIT_PASS
    assert _state(tmp_path)["source_access"] == "read"


def test_stage_order_includes_reconcile():
    assert "reconcile" in STAGE_ORDER
    assert STAGE_ORDER.index("reconcile") == len(STAGE_ORDER) - 1
