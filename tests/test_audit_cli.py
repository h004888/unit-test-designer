"""Test cho audit report writer và tích hợp cổng G7 từ inventory."""

import json

import pytest

from utd.audit.gates import audit_ssot, format_markdown
from utd.audit.report import (
    count_issues_by_gate,
    issues_match_json_and_markdown,
    write_report,
)


def _ssot(modules=None) -> dict:
    return {"modules": modules or [
        {"sheet_name": "S", "methods": [{
            "name": "createOrder",
            "api": {"http_method": "POST", "path": "/x", "auth": "jwt",
                    "request": [], "responses": [], "rules": []},
            "test_cases": [],
        }]},
    ]}


def test_write_report_creates_both_files(tmp_path):
    report = audit_ssot(_ssot())
    json_path, md_path = write_report(report, tmp_path / "audit")

    assert json_path.exists()
    assert md_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert "gates" in data
    assert len(data["gates"]) == 9


def test_report_json_and_markdown_counts_match(tmp_path):
    report = audit_ssot(_ssot())
    json_path, md_path = write_report(report, tmp_path / "audit")

    data = json.loads(json_path.read_text(encoding="utf-8"))
    text = md_path.read_text(encoding="utf-8")

    failing = [g for g in data["gates"] if not g["passed"]]
    for gate in failing:
        assert gate["gate"] in text

    assert data["total_issues"] == report.total_issues


def test_count_issues_by_gate_reports_all_nine():
    counts = count_issues_by_gate(audit_ssot(_ssot()))
    assert set(counts) == {"G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"}


def test_issues_match_json_and_markdown_true_for_report():
    report = audit_ssot(_ssot())
    assert issues_match_json_and_markdown(report) is True


def test_markdown_has_actions_for_failing_gates():
    report = audit_ssot(_ssot())
    text = format_markdown(report)

    for result in report.results:
        if result.passed:
            continue
        assert "**Hành động:**" in text


def test_g7_integration_with_inventory_coverage():
    """G7 phải phát hiện coverage chưa cộng đủ 150."""
    coverage = {
        "total_rules": 150,
        "matched": 83,
        "skipped": 60,
        "unaccounted": 7,
    }
    report = audit_ssot(_ssot(), coverage=coverage)
    g7 = report.by_gate("G7")

    assert g7.passed is False


def test_g7_would_have_caught_old_implementation():
    """Mô phỏng số liệu bản cũ: 83 matched, không có lý do cho 67 rule còn lại.

    Bản cũ: `uncovered_rules` chỉ kiểm rule ĐÃ sinh -> 150 - 83 = 67 rule
    hoàn toàn vô hình. G7 phát hiện.
    """
    coverage = {
        "total_rules": 150,
        "matched": 83,
        "skipped": 0,
        "unaccounted": 67,
    }
    report = audit_ssot(_ssot(), coverage=coverage)
    g7 = report.by_gate("G7")

    assert g7.passed is False
    assert any("67" in issue.message for issue in g7.issues)
