# Proposal

## Why

Ba change trước đã hoàn tất `unit-test-designer` v2 (59 + 32 + 16 task, 484 test pass), nhưng cách phân phối hiện tại chỉ là copy thư mục và tự tạo wrapper `utd` trong PATH. Điều này có ba hệ quả đo được: (1) `utd` không tự có trong PATH nên `allowed-tools: Bash(utd:*)` trong `SKILL.md` không khớp trên máy mới; (2) runtime phụ thuộc ba thư mục dữ liệu **bên ngoài** package (`engine.py:32`, `tier.py:19`, `data.py:17` dùng `parent.parent.parent`), nên copy thiếu một thư mục là hỏng; (3) không có version, không có nơi tải, không có đường nâng cấp.

Đo hiện trạng: gói cần phân phối là 871 KB / 59 file (bỏ `tests/` 1.1 MB và `tools/`). Đây là gói nhẹ, đủ nhỏ để đóng wheel và phát hành qua GitHub Releases.

## What Changes

- **Move dữ liệu vào trong package**: `rules/` → `utd/_data/rules/`, `data/` → `utd/_data/data/`, `SKILL.md` + `SCHEMA.md` + `references/` + `assets/` → `utd/_data/skill/`.
- **Đổi ba hằng số đường dẫn** sang `importlib.resources.files("utd")` (design D1).
- **Sửa `sorted()` trên `Traversable`** — `Traversable` không định nghĩa `__lt__`, nên `sorted(target.glob(...))` ném `TypeError` và làm 50 lời gọi test trong 9 file đỏ cùng lúc (design D2).
- **Thêm lệnh `utd install-skill`**: copy skill từ wheel vào `~/.claude/skills/unit-test-designer`, có `--target`, `--force`, `--dry-run`, kiểm frontmatter trước khi ghi.
- **Thêm `pyproject.toml`** với `console_scripts` entry point và `package-data` khai đủ `_data/**`; `LICENSE` MIT; `README.md`.
- **Đưa repo lên GitHub** `h004888/unit-test-designer` (PUBLIC, MIT) bằng `git init` **mới** để history không chứa 11 skill OpenSpec trong `.claude/skills/` và `.agents/skills/` (design D5).
- **Copy `openspec/` vào trong repo** (cách B) để giữ lịch sử thiết kế làm tài sản của dự án.
- **CI** (`.github/workflows/ci.yml`): matrix Python 3.10/3.11/3.12 × ubuntu/windows, chạy pytest, cộng một bước xác nhận wheel chứa `_data` (design D4).
- **Release** (`.github/workflows/release.yml`): push tag `v*` → build wheel → GitHub Release đính kèm `.whl`.

## Capabilities

### New Capabilities

- `distribution`: đóng gói, kiểm chứng và phát hành `unit-test-designer` dưới dạng wheel tự chứa, kèm lệnh cài skill và quy trình CI/release.

### Modified Capabilities

Không có. Các capability đã sync (`spec-ingestion`, `rule-evaluation`, `interview-gate`, `test-case-generation`, `quality-audit`, `document-output`, `flag-interview`, `question-identity`) mô tả hành vi của CLI, không mô tả cách đóng gói; change này không đổi hành vi nào trong số đó.

## Impact

- **Move**: `rules/` (10 file) → `utd/_data/rules/`; `data/` (3 file) → `utd/_data/data/`; `SKILL.md`, `SCHEMA.md`, `references/`, `assets/` → `utd/_data/skill/`.
- **Sửa**: `utd/match/engine.py` (hằng số + `sorted`), `utd/match/tier.py` (hằng số), `utd/generate/data.py` (hằng số), `utd/cli.py` (subcommand `install-skill`).
- **Sửa test**: `tests/test_dsl.py:20` và `tests/test_dsl_interpreter.py:20` đọc `ROOT / "rules"` bằng đường dẫn cứng; `tests/test_data_migration.py` tham chiếu `assets/rules_domain/` đã xoá (đang skip) — dọn luôn trong change này.
- **Thêm**: `utd/install_skill.py`, `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore` (mở rộng), `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `MANIFEST.in` nếu cần.
- **Giữ nguyên**: 50 lời gọi `load_rules()` và 18 lời gọi `DataProvider.load()` không tham số vẫn xanh vì default trỏ `_data/` đúng.
- **Không đổi**: hành vi 8 stage, `SCHEMA.md` contract, exit code, 9 cổng, 150 rule, 6 cờ, định dạng id `row:*`.
- **Rủi ro công khai**: repo PUBLIC và lần push đầu là vĩnh viễn; `data/payloads.json` chứa 230 payload XSS (dữ liệu test chuẩn ngành, không phải secret) — giữ trong repo để clone build được.
- **Tương thích người dùng hiện tại**: ai đã copy thư mục skill thủ công sẽ phải chuyển sang `pip install` + `utd install-skill`; checklist cũ vẫn ở dạng id cũ như đã ghi trong `SCHEMA.md` mục Tương thích ngược (từ change `stabilize-question-ids`).
