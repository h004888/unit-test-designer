"""Kiểm chứng dữ liệu rule và data trong package đầy đủ và đúng schema."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RULES_NEW = ROOT / "utd" / "_data" / "rules"
DATA = ROOT / "utd" / "_data" / "data"

EXPECTED_RULES = 150
EXPECTED_REALISTIC = 82
EXPECTED_PAYLOADS = 701
EXPECTED_DOMAIN_FILES = 10


def test_ten_domain_files_exist():
    files = sorted(RULES_NEW.glob("*.json"))
    assert len(files) == EXPECTED_DOMAIN_FILES


def test_total_rules_is_150():
    total = sum(
        len(json.loads(path.read_text(encoding="utf-8"))["rules"])
        for path in sorted(RULES_NEW.glob("*.json"))
    )
    assert total == EXPECTED_RULES


def test_realistic_records_count():
    data = json.loads((DATA / "realistic.json").read_text(encoding="utf-8"))
    assert len(data["records"]) == EXPECTED_REALISTIC


def test_payload_records_count():
    data = json.loads((DATA / "payloads.json").read_text(encoding="utf-8"))
    assert len(data["records"]) == EXPECTED_PAYLOADS


def test_realistic_has_required_columns():
    records = json.loads((DATA / "realistic.json").read_text(encoding="utf-8"))["records"]
    required = {"id", "category", "sub_type", "locale", "payload_value", "quirk_type"}
    for record in records:
        assert required <= set(record), record


def test_realistic_has_vietnamese_names():
    records = json.loads((DATA / "realistic.json").read_text(encoding="utf-8"))["records"]
    vi_names = [r for r in records if r["category"] == "name" and r["locale"] == "vi"]
    assert len(vi_names) >= 5

    def has_diacritics(text: str) -> bool:
        return any(ord(ch) > 127 for ch in text)

    assert any(has_diacritics(r["payload_value"]) for r in vi_names)


def test_no_slop_values_in_realistic():
    records = json.loads((DATA / "realistic.json").read_text(encoding="utf-8"))["records"]
    slop = {"john doe", "jane doe", "test@example.com", "123 main st", "1111111111"}
    for record in records:
        assert record["payload_value"].strip().lower() not in slop


def test_payload_categories_present():
    records = json.loads((DATA / "payloads.json").read_text(encoding="utf-8"))["records"]
    categories = {r["category"] for r in records}
    assert "XSS & Script Injection" in categories
    assert "Boundary & Punctuation" in categories
    assert len(categories) >= 10


def test_every_rule_has_trigger_condition():
    for path in sorted(RULES_NEW.glob("*.json")):
        for rule in json.loads(path.read_text(encoding="utf-8"))["rules"]:
            assert "trigger_condition" in rule, f"{path.name}: {rule.get('id')} thiếu trigger_condition"
            assert rule["trigger_condition"].strip(), f"{path.name}: {rule['id']} trigger rỗng"


def test_every_rule_has_target_element():
    for path in sorted(RULES_NEW.glob("*.json")):
        for rule in json.loads(path.read_text(encoding="utf-8"))["rules"]:
            assert rule.get("target_element"), f"{path.name}: {rule.get('id')} thiếu target_element"


def test_rule_ids_unique_across_domains():
    seen = {}
    for path in sorted(RULES_NEW.glob("*.json")):
        for rule in json.loads(path.read_text(encoding="utf-8"))["rules"]:
            rid = rule["id"]
            assert rid not in seen, f"rule id trùng: {rid} ({path.name} và {seen.get(rid)})"
            seen[rid] = path.name
    assert len(seen) == EXPECTED_RULES
