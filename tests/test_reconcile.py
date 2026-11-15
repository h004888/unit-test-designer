"""Test cho utd.reconcile: 4 nhóm phân loại, cộng đủ rule, CLI."""

import json
from pathlib import Path

import pytest

from utd.cli import EXIT_INVALID_INPUT, EXIT_PASS, main
from utd.reconcile import (
    CATEGORIES,
    ReconcileError,
    build_report,
    collect_rules,
    load_findings,
    reconcile_from_files,
)

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


def _ssot(rules=("BR-01", "BR-02")) -> dict:
    return {
        "project": {"name": "Demo"},
        "modules": [{
            "sheet_name": "S",
            "methods": [{
                "name": "f",
                "api": {"rules": [{"id": r, "text": f"rule {r}"} for r in rules]},
                "test_cases": [{"id": "UTC001", "rule_refs": [rules[0]],
                                "type": "Normal"}],
            }],
        }],
    }


def test_collect_rules_with_cases():
    rules = collect_rules(_ssot())
    assert set(rules) == {"BR-01", "BR-02"}
    assert rules["BR-01"]["cases"] == ["UTC001"]
    assert rules["BR-02"]["cases"] == []


def test_load_findings_rejects_bad_category(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"findings": [
        {"rule_id": "BR-01", "category": "Sai linh tinh"}
    ]}), encoding="utf-8")

    with pytest.raises(ReconcileError) as excinfo:
        load_findings(path)
    assert excinfo.value.exit_code == 3


def test_load_findings_rejects_missing_rule_id(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"findings": [{"category": "Match"}]}), encoding="utf-8")

    with pytest.raises(ReconcileError):
        load_findings(path)


def test_report_covers_all_four_categories():
    findings = load_findings_from([
        {"rule_id": "BR-01", "category": "Match"},
        {"rule_id": "BR-02", "category": "Missing in code"},
    ])
    text = build_report(_ssot(), findings)

    assert "ĐÚNG (Match)" in text
    assert "THIẾU TRONG CODE (Missing)" in text


def load_findings_from(items):
    from utd.reconcile import Finding
    return [Finding(rule_id=i["rule_id"], category=i["category"],
                    detail=i.get("detail", ""), location=i.get("location", ""))
            for i in items]


def test_report_totals_add_up():
    findings = load_findings_from([
        {"rule_id": "BR-01", "category": "Match"},
    ])
    text = build_report(_ssot(), findings)

    assert "Rule trong đặc tả | 2" in text
    assert "Rule chưa đối chiếu" in text
    assert "BR-02" in text


def test_report_flags_unknown_rule():
    findings = load_findings_from([{"rule_id": "BR-99", "category": "Match"}])
    text = build_report(_ssot(), findings)

    assert "không khớp rule nào" in text
    assert "BR-99" in text


def test_reconcile_from_files(tmp_path):
    ssot_path = tmp_path / "ssot.json"
    ssot_path.write_text(json.dumps(_ssot(), ensure_ascii=False), encoding="utf-8")

    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps({"findings": [
        {"rule_id": "BR-01", "category": "Match", "detail": "khớp"},
        {"rule_id": "BR-02", "category": "Extra in code",
         "detail": "code tự thêm", "location": "order.service.ts:42"},
    ]}), encoding="utf-8")

    target, summary = reconcile_from_files(ssot_path, findings_path, tmp_path / "out")

    assert target.exists()
    assert summary["total_findings"] == 2
    assert summary["by_category"]["Match"] == 1
    assert summary["by_category"]["Extra in code"] == 1
    assert summary["unclassified"] == 0

    text = target.read_text(encoding="utf-8")
    assert "order.service.ts:42" in text


def test_cli_reconcile_end_to_end(tmp_path):
    assert main(["ingest", "--from", "utd-v1", "--in", str(LEGACY),
                 "--workspace", str(tmp_path)]) == EXIT_PASS
    assert main(["generate", "--workspace", str(tmp_path),
                 "--source", ".unittest-design/canonical/spec.json"]) == EXIT_PASS

    design = tmp_path / ".unittest-design"
    findings = design / "reconcile" / "findings.json"
    findings.parent.mkdir(parents=True, exist_ok=True)
    findings.write_text(json.dumps({"findings": [
        {"rule_id": "BR-01", "category": "Match"},
        {"rule_id": "BR-02", "category": "Mismatch", "detail": "sai biên"},
        {"rule_id": "BR-03", "category": "Missing in code"},
        {"rule_id": "BR-04", "category": "Extra in code"},
        {"rule_id": "BR-05", "category": "Match"},
        {"rule_id": "BR-06", "category": "Match"},
        {"rule_id": "BR-07", "category": "Match"},
        {"rule_id": "BR-08", "category": "Match"},
        {"rule_id": "BR-09", "category": "Match"},
        {"rule_id": "BR-10", "category": "Match"},
        {"rule_id": "BR-11", "category": "Match"},
    ]}), encoding="utf-8")

    code = main(["reconcile", "--workspace", str(tmp_path)])
    assert code == EXIT_PASS

    report = design / "reconcile" / "gap_report.md"
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "SAI / LỆCH (Mismatch)" in text
    assert "sai biên" in text


def test_cli_reconcile_missing_findings(tmp_path):
    assert main(["ingest", "--from", "utd-v1", "--in", str(LEGACY),
                 "--workspace", str(tmp_path)]) == EXIT_PASS
    assert main(["generate", "--workspace", str(tmp_path),
                 "--source", ".unittest-design/canonical/spec.json"]) == EXIT_PASS

    code = main(["reconcile", "--workspace", str(tmp_path)])
    assert code == EXIT_INVALID_INPUT


def test_four_categories_defined():
    assert CATEGORIES == ("Match", "Mismatch", "Missing in code", "Extra in code")
