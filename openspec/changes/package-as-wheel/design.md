# Design

## Context

Xem `proposal.md` — Why. Dưới đây là hiện trạng kỹ thuật quyết định cách làm.

Hiện trạng sau ba change trước:

- `utd/match/engine.py:32` `DEFAULT_RULES_DIR = Path(__file__).resolve().parent.parent.parent / "rules"`
- `utd/match/tier.py:19` cùng dạng, trỏ `data/tiers.json`
- `utd/generate/data.py:17` cùng dạng, trỏ `data/`
- `utd/match/engine.py:49` `for path in sorted(target.glob("*.json"))` — `sorted` trên `Path` được, trên `Traversable` không
- Toàn bộ import trong package là **relative** (47 chỗ), không có import tuyệt đối `from utd...` ⇒ không cần sửa import khi đóng gói
- `tests/test_dsl.py:20` và `tests/test_dsl_interpreter.py:20` đọc `ROOT / "rules"` bằng đường dẫn cứng
- `tests/test_data_migration.py` tham chiếu `assets/rules_domain/` đã bị xoá ở change trước, đang `skipif` 1 test
- 50 lời gọi `load_rules()` và 18 lời gọi `DataProvider.load()` không truyền tham số ⇒ đọc default
- `temp_test/.git` có 1 commit chứa cả `.claude/skills/` (11 skill, frontmatter `author: openspec`) và `.agents/skills/` (bản sao byte-for-byte)

Đo kích thước: 871 KB / 59 file khi bỏ `tests/` và `tools/`.

## Goals / Non-Goals

**Goals:**

- `pip install <wheel>` là đủ để có lệnh `utd` chạy được trên máy sạch.
- Wheel tự chứa rule, data, và tài liệu skill — không phụ thuộc thư mục bên ngoài.
- Cài skill là hành động chủ động, không tự chạy sau `pip install`.
- CI bắt được lỗi `package-data` trước khi phát hành.
- Repo public có history sạch, LICENSE MIT, README dùng được.

**Non-Goals:**

- Không publish lên PyPI (chọn 3a: gửi file qua GitHub Releases).
- Không giữ history cũ của `temp_test`.
- Không đóng gói `.claude/skills/` hay `.agents/skills/` — đó là skill của OpenSpec.
- Không thêm tính năng CLI nào ngoài `install-skill`.
- Không đổi `SCHEMA.md`, 8 stage, 9 cổng, 150 rule, 6 cờ, định dạng id.

## Decisions

### D1. Dữ liệu nằm trong `utd/_data/`, không phải `utd/rules/`

**Chọn:** `utd/_data/{rules,data,skill}/`.

**Vì:** `ls utd/` phải cho thấy module Python trước; dữ liệu là thứ tra cứu khi cần. Đặt tên `_` cũng báo hiệu đây không phải API công khai.

**Loại bỏ:** *phẳng (`utd/rules/`)* — lẫn code với dữ liệu, `find utd -name "*.py"` khó đọc hơn; *giữ ngoài package + `data_files` trong pyproject* — `data_files` cài vào `sys.prefix` không theo package, đường dẫn phụ thuộc nền tảng, khó kiểm.

### D2. Sửa `sorted()` trước khi move dữ liệu

**Chọn:** thứ tự thực thi là (1) `sorted(..., key=lambda p: p.name)`, (2) move dữ liệu, (3) đổi hằng số.

**Vì:** `Traversable` không định nghĩa `__lt__`; `sorted()` trên nó ném `TypeError`. Nếu move dữ liệu trước, 50 test đỏ cùng lúc và không phân biệt được lỗi do move hay do sort. Sửa sort trước để mỗi bước chỉ có một biến số.

**Loại bỏ:** *đổi cả hai cùng lúc* — hai biến số trong một bước, khi đỏ không biết do đâu; *dùng `os.listdir` trên `str(...)`* — `Traversable` không đảm bảo có đường dẫn filesystem thật khi cài từ zip import.

### D3. `install-skill` là lệnh riêng, không tự chạy

**Chọn:** subcommand `utd install-skill` với `--target`, `--force`, `--dry-run`.

**Vì:** `pip install` ghi vào `site-packages`; ghi thêm vào `~/.claude/` là vượt ranh giới công cụ. Người dùng phải chủ động. Và `post_install` không còn là hook ổn định trong pip hiện đại.

**Loại bỏ:** *entry point `post_install`* — không ổn định, và pip khuyến nghị không dùng; *tự copy trong `utd` lần chạy đầu* — hành vi ẩn, khó debug khi thư mục đích bị chặn quyền.

### D4. CI có bước kiểm wheel chứa `_data`

**Chọn:** sau `python -m build`, chạy một đoạn Python mở zip và assert có `utd/_data/rules/`, `utd/_data/data/`, `utd/_data/skill/SKILL.md`.

**Vì:** lỗi `package-data` không làm test đỏ (test chạy từ source tree, `files("utd")` trỏ thẳng thư mục nguồn). Nó chỉ lộ khi cài wheel ở máy khác. Bước này là chốt chặn duy nhất bắt được.

**Loại bỏ:** *kiểm bằng `unzip -l | grep`* — phụ thuộc công cụ có sẵn trên runner; Python zipfile có ở mọi runner.

### D5. `git init` mới thay vì push history cũ

**Chọn:** tạo repo git mới **bên trong** `unit-test-designer/`, 1 commit đầu, push lên `h004888/unit-test-designer`.

**Vì:** history hiện tại của `temp_test` chứa `.claude/skills/` và `.agents/skills/` — 11 skill của OpenSpec với `metadata.author: openspec`. Dù xoá ở HEAD, `git log -p` vẫn xem lại được. Trên repo công khai mang tên người dùng, đó là phân phối lại tài sản của người khác.

**Loại bỏ:** *giữ history + `git filter-branch`* — phức tạp, dễ sai, và baseline 1 commit không có giá trị giữ; *push riêng từng subtree* — thêm bước mà vẫn dính history.

### D6. `openspec/` được copy vào repo (cách B)

**Chọn:** copy `temp_test/openspec/` → `unit-test-designer/openspec/`.

**Vì:** proposal + design + specs + tasks là bằng chứng thiết kế; người đọc repo thấy được vì sao có 9 cổng, vì sao bỏ SQLite, vì sao id đổi dạng. Đây là tài sản, không phải rác.

**Loại bỏ:** *bỏ `openspec/` (cách A)* — mất lịch sử nhưng đơn giản hơn; *push `temp_test/` nguyên trạng (cách C)* — kéo theo `.claude/` và `.agents/`.

### D7. Payload XSS giữ trong repo

**Chọn:** commit `utd/_data/data/payloads.json` (244 KB, gồm 230 payload XSS/SQLi).

**Vì:** đây là dữ liệu test chuẩn ngành (OWASP, SecLists, BLNS), không phải secret. Giấu đi thì clone repo không build được wheel đầy đủ, và CI không kiểm được cùng dữ liệu người dùng nhận.

**Loại bỏ:** *`.gitignore` payload, chỉ có trong wheel phát hành* — repo không build được từ clone; *tách repo riêng* — thêm phụ thuộc cho một file dữ liệu tĩnh.

## Risks / Trade-offs

- **[Move dữ liệu làm đỏ test]** `test_dsl.py:20`, `test_dsl_interpreter.py:20` đọc `ROOT / "rules"` cứng. Mitigation: sửa hai file đó cùng bước move; chạy `pytest -q` sau mỗi bước.
- **[`package-data` glob sai trên Windows]** setuptools dùng `/` trong glob kể cả Windows, nhưng một số phiên bản cần `**`. Mitigation: D4 kiểm wheel; test trên `windows-latest` trong matrix.
- **[Repo public là vĩnh viễn]** Lần push đầu không hoàn tác. Mitigation: task push là task cuối, đánh dấu "cần xác nhận riêng", và `git init` mới (D5) bảo đảm không có gì ngoài ý muốn.
- **[Người dùng cũ mất đường cài thủ công]** Sau khi move, không còn `SKILL.md` ở gốc repo để copy. Mitigation: README nêu rõ `utd install-skill`; `SKILL.md` vẫn có trong `utd/_data/skill/`.
- **[Release workflow cần quyền tạo Release]** `GITHUB_TOKEN` mặc định có `contents: write` khi khai `permissions`. Mitigation: khai tường minh `permissions: contents: write` trong `release.yml`.
- **[Version 2.0.0 trùng với code hiện tại]** Nếu release rồi mới phát hiện lỗi đóng gói, phải phát hành 2.0.1. Mitigation: bước 8 (cài thử trong venv) chạy trước bước 10 (push), nên lỗi lộ trước khi tốn version.

## Migration Plan

1. `sorted(..., key=lambda p: p.name)` trong `load_rules`; chạy test.
2. Move `rules/`, `data/`, tài liệu skill vào `utd/_data/`; sửa hai test đọc `ROOT / "rules"`; chạy test.
3. Đổi ba hằng số sang `importlib.resources`; chạy test.
4. Thêm `utd/install_skill.py` + subcommand; test.
5. `pyproject.toml`, `LICENSE`, `README.md`, `.gitignore`; build wheel.
6. Copy `openspec/` vào; kiểm `openspec validate --specs` vẫn chạy trong repo mới.
7. `.github/workflows/ci.yml`.
8. Build + cài trong venv sạch + chạy e2e 8 stage.
9. `.github/workflows/release.yml`.
10. `git init` mới, commit, tạo remote, push — **cần xác nhận riêng trước khi chạy**.

Rollback: các bước 1-9 revert được bằng git; bước 10 không (repo public).

## Open Questions

Không có. Bốn quyết định — tên `unit-test-designer`, version `2.0.0` giữ nguyên, README do tác nhân viết, LICENSE MIT — đã chốt trước khi mở change.
