"""migrate_v1_data.py - Chuyển dữ liệu v1 sang dạng JSON của v2 (ĐÃ CHẠY, giữ làm tham chiếu).

CẢNH BÁO: script này cần thư mục `assets/rules_domain/` và `assets/test_knowledge.db`
của bản v1, đã bị xoá ở task 8.5. Chạy lại chỉ được nếu khôi phục từ backup
(`_backup_v2/unit-test-designer-pre-v2.tar.gz`) hoặc từ commit `pre-v2`.

Việc chuyển đổi này là chuyển vị trí + đổi định dạng chứa, KHÔNG đổi nội dung:
  - assets/rules_domain/*.json  ->  rules/*.json            (copy nguyên byte)
  - bảng realistic_user_data     ->  data/realistic.json     (gộp mọi cột)
  - bảng test_payloads           ->  data/payloads.json      (gộp mọi cột)

Sau khi chuyển xong, `test_knowledge.db` và `heuristic_matrix.json` là derived
và có thể xoá (xem tasks 8.5).

Chạy: python tools/migrate_v1_data.py
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
RULES_SRC = ASSETS / "rules_domain"
RULES_DST = ROOT / "rules"
DATA_DST = ROOT / "data"
DB_PATH = ASSETS / "test_knowledge.db"

EXPECTED_RULES = 150
EXPECTED_REALISTIC = 82
EXPECTED_PAYLOADS = 701


def copy_rules() -> int:
    RULES_DST.mkdir(parents=True, exist_ok=True)
    count = 0
    for source in sorted(RULES_SRC.glob("*.json")):
        target = RULES_DST / source.name
        shutil.copy2(source, target)
        count += 1
    return count


def read_table(conn: sqlite3.Connection, table: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table}")
    return [dict(row) for row in cursor.fetchall()]


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def main() -> int:
    if not DB_PATH.exists():
        print(f"[-] Không tìm thấy database nguồn: {DB_PATH}", file=sys.stderr)
        return 1

    copied = copy_rules()
    print(f"[+] Đã copy {copied} file rule -> {RULES_DST}")

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        realistic = read_table(conn, "realistic_user_data")
        payloads = read_table(conn, "test_payloads")
    finally:
        conn.close()

    write_json(
        DATA_DST / "realistic.json",
        {
            "schema_version": 1,
            "source": "v1:realistic_user_data",
            "records": realistic,
        },
    )
    write_json(
        DATA_DST / "payloads.json",
        {
            "schema_version": 1,
            "source": "v1:test_payloads",
            "records": payloads,
        },
    )

    print(f"[+] realistic.json: {len(realistic)} bản ghi")
    print(f"[+] payloads.json : {len(payloads)} payload")

    ok = True
    if copied != 10:
        print(f"[!] Số file rule lệch: {copied} (mong đợi 10)", file=sys.stderr)
        ok = False
    if len(realistic) != EXPECTED_REALISTIC:
        print(f"[!] realistic lệch: {len(realistic)} (mong đợi {EXPECTED_REALISTIC})", file=sys.stderr)
        ok = False
    if len(payloads) != EXPECTED_PAYLOADS:
        print(f"[!] payloads lệch: {len(payloads)} (mong đợi {EXPECTED_PAYLOADS})", file=sys.stderr)
        ok = False

    total_rules = sum(
        len(json.loads((RULES_DST / p.name).read_text(encoding="utf-8"))["rules"])
        for p in sorted(RULES_DST.glob("*.json"))
    )
    if total_rules != EXPECTED_RULES:
        print(f"[!] Tổng rule lệch: {total_rules} (mong đợi {EXPECTED_RULES})", file=sys.stderr)
        ok = False

    print(f"[+] Tổng rule: {total_rules}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
