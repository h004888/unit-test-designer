"""Đo tác động thật của cờ: 92 -> 97 matched, 86 -> 98 -> 92 câu."""

import json
from pathlib import Path

import pytest

from utd.canonical import parse
from utd.match.engine import load_rules, match_spec

ROOT = Path(__file__).parent.parent
LEGACY = ROOT / "utd" / "_data" / "skill" / "assets" / "example_api_spec.json"


@pytest.fixture(scope="module")
def spec():
    from utd.ingest import convert

    return convert("utd-v1", json.loads(LEGACY.read_text(encoding="utf-8")))


def _set_user_flags(spec, values: dict[str, bool]):
    for module in spec.modules:
        for name, value in values.items():
            module.flags.set(name, value, source="user")
    return spec


def test_baseline_matched_is_92(spec):
    """Baseline: cờ default -> 92 matched, 58 skipped."""
    for module in spec.modules:
        for name in ("has_quota", "has_dependencies", "has_unique_field"):
            module.flags.values[name] = False
            module.flags.sources[name] = "default"

    report = match_spec(spec, load_rules())
    assert report.matched_count == 92
    assert report.skipped_count == 58
    assert report.matched_count + report.skipped_count == 150


def test_all_three_flags_true_gives_97_matched(spec):
    """Bật 3 cờ user-only -> 97 matched, 53 skipped (5 rule được cứu)."""
    _set_user_flags(spec, {
        "has_quota": True,
        "has_dependencies": True,
        "has_unique_field": True,
    })

    report = match_spec(spec, load_rules())
    assert report.matched_count == 97, f"được {report.matched_count}, mong đợi 97"
    assert report.skipped_count == 53
    assert report.matched_count + report.skipped_count == 150


def test_five_rules_rescued(spec):
    """Đúng 5 rule phải chuyển từ skipped sang matched."""
    affected = {
        "H-STATE-STOCK-QUOTA-01",
        "H-CONC-RACE-01",
        "H-DIST-CIRCUIT-BREAKER-01",
        "H-DIST-TIMEOUT-FALLBACK-01",
        "H-STATE-UNIQUE-01",
    }

    for module in spec.modules:
        for name in ("has_quota", "has_dependencies", "has_unique_field"):
            module.flags.values[name] = True
            module.flags.sources[name] = "user"

    report = match_spec(spec, load_rules())
    skipped_ids = {s.rule_id for s in report.skipped}

    assert affected <= report.matched_rule_ids, affected - report.matched_rule_ids
    assert not (affected & skipped_ids)


def test_flag_questions_present_for_every_module(spec):
    report = match_spec(spec, load_rules())
    flag_questions = [q for q in report.questions if q.rule_id.startswith("FLAG:")]

    assert len(flag_questions) == 6 * len(spec.modules)


def test_question_count_grows_with_flags(spec):
    for module in spec.modules:
        for name in ("has_quota", "has_dependencies", "has_unique_field"):
            module.flags.values[name] = False
            module.flags.sources[name] = "default"
    baseline_questions = len(match_spec(spec, load_rules()).questions)

    for module in spec.modules:
        for name in ("has_quota", "has_dependencies", "has_unique_field"):
            module.flags.values[name] = True
            module.flags.sources[name] = "user"
    with_flags = len(match_spec(spec, load_rules()).questions)

    assert with_flags > baseline_questions
