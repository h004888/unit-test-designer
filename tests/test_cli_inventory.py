"""Test CLI inventory: sinh checklist, reachability, ghi run.json."""

import json
from pathlib import Path

from utd.cli import EXIT_GATE, EXIT_INVALID_INPUT, EXIT_PASS, main

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def _prepare(tmp_path):
    """ingest rồi inventory trong workspace tạm."""
    spec = tmp_path / "canonical" / "spec.json"
    code = main(["ingest", "--from", "utd-v1", "--in", str(LEGACY), "--out", str(spec)])
    assert code == EXIT_PASS
    return spec


def test_inventory_creates_checklist(tmp_path):
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"

    code = main(["inventory", "--spec", str(spec), "--out", str(checklist),
                 "--workspace", str(tmp_path)])

    assert code == EXIT_PASS
    assert checklist.exists()

    data = json.loads(checklist.read_text(encoding="utf-8"))
    assert data["coverage"]["total_rules"] == 150
    assert data["coverage"]["coverage_ok"] is True
    assert data["session_state"] == "AWAITING_USER_INTERACTION"


def test_inventory_records_run_state(tmp_path):
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"

    main(["inventory", "--spec", str(spec), "--out", str(checklist),
          "--workspace", str(tmp_path)])

    run_file = tmp_path / ".unittest-design" / "run.json"
    state = json.loads(run_file.read_text(encoding="utf-8"))
    assert state["stage"] == "inventory"
    assert "checklist" in state["artifacts"]
    assert state["gates"]["reachability"]["passed"] is True


def test_inventory_missing_spec_exit_2(tmp_path):
    code = main(["inventory", "--spec", str(tmp_path / "nope.json"),
                 "--out", str(tmp_path / "c.json"), "--workspace", str(tmp_path)])
    assert code == EXIT_INVALID_INPUT


def test_inventory_corrupt_spec_exit_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ broken", encoding="utf-8")
    code = main(["inventory", "--spec", str(bad), "--out", str(tmp_path / "c.json"),
                 "--workspace", str(tmp_path)])
    assert code == EXIT_INVALID_INPUT


def test_every_question_has_unique_nonce(tmp_path):
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"
    main(["inventory", "--spec", str(spec), "--out", str(checklist),
          "--workspace", str(tmp_path)])

    data = json.loads(checklist.read_text(encoding="utf-8"))
    nonces = [q["nonce"] for q in data["questions"]]

    assert len(nonces) == len(set(nonces))
    assert all(len(n) == 32 for n in nonces)


def test_skipped_rules_all_have_reason(tmp_path):
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"
    main(["inventory", "--spec", str(spec), "--out", str(checklist),
          "--workspace", str(tmp_path)])

    data = json.loads(checklist.read_text(encoding="utf-8"))
    for skipped in data["skipped_rules"]:
        assert skipped["skipped_reason"].strip()


def test_matched_plus_skipped_equals_150(tmp_path):
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"
    main(["inventory", "--spec", str(spec), "--out", str(checklist),
          "--workspace", str(tmp_path)])

    coverage = json.loads(checklist.read_text(encoding="utf-8"))["coverage"]
    assert coverage["matched"] + coverage["skipped"] == coverage["total_rules"] == 150


def test_question_count_is_reasonable(tmp_path):
    """Gộp theo (endpoint, param, target_element) phải giảm số câu so với 544."""
    spec = _prepare(tmp_path)
    checklist = tmp_path / "interview" / "checklist.json"
    main(["inventory", "--spec", str(spec), "--out", str(checklist),
          "--workspace", str(tmp_path)])

    coverage = json.loads(checklist.read_text(encoding="utf-8"))["coverage"]
    assert coverage["questions"] < 200
    assert coverage["questions"] >= 20
