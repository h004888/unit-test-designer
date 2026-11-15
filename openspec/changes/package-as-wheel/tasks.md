# Tasks

## 1. Sửa `sorted()` trước khi move (D2)

- [x] 1.1 Đổi `utd/match/engine.py:49` thành `sorted(target.glob("*.json"), key=lambda p: p.name)`; verify: `pytest tests/test_dsl.py tests/test_match_engine.py -q` xanh
- [x] 1.2 Chạy toàn bộ test trước khi đổi gì khác để có baseline xanh; verify: `pytest -q` 484 passed, 1 skipped

## 2. Move dữ liệu vào package

- [x] 2.1 Tạo `utd/_data/rules/` và move 10 file rule vào; verify: `ls utd/_data/rules/*.json | wc -l` = 10
- [x] 2.2 Tạo `utd/_data/data/` và move `realistic.json`, `payloads.json`, `tiers.json`; verify: 3 file, `du -sh utd/_data/data` ≈ 270 KB
- [x] 2.3 Tạo `utd/_data/skill/` và move `SKILL.md`, `SCHEMA.md`, `references/`, `assets/` vào; verify: `ls utd/_data/skill` có đủ 4 mục
- [x] 2.4 Sửa `tests/test_dsl.py:20` và `tests/test_dsl_interpreter.py:20` không còn dùng `ROOT / "rules"`; verify: hai file pass
- [x] 2.5 Dọn `tests/test_data_migration.py`: bỏ nhánh so sánh `assets/rules_domain/` đã xoá, chỉ giữ kiểm `utd/_data/rules` có 150 rule; verify: 0 skip trong file này
- [x] 2.6 Chạy toàn bộ test; verify: `pytest -q` 0 failed, 0 skipped

## 3. Đọc dữ liệu qua importlib.resources

- [x] 3.1 Đổi `DEFAULT_RULES_DIR` trong `utd/match/engine.py` sang `files("utd") / "_data" / "rules"`; verify: `load_rules()` trả 150 rule
- [x] 3.2 Đổi `DEFAULT_DATA_DIR` trong `utd/generate/data.py` sang `files("utd") / "_data" / "data"`; verify: `DataProvider.load()` đọc được 82 + 701 bản ghi
- [x] 3.3 Đổi `DEFAULT_TIERS_PATH` trong `utd/match/tier.py` sang `files("utd") / "_data" / "data" / "tiers.json"`; verify: `load_tier_config()` đọc được
- [x] 3.4 Kiểm không còn `parent.parent.parent` dùng để đọc dữ liệu; verify: `grep -rn "parent.parent.parent" utd/` không còn kết quả đọc rules/data
- [x] 3.5 Chạy toàn bộ test; verify: `pytest -q` 0 failed

## 4. Lệnh `utd install-skill`

- [x] 4.1 Viết `utd/install_skill.py` với `install_skill(target=None, force=False, dry_run=False)` đệ quy Traversable → Path; verify: gọi trực tiếp trên thư mục tạm tạo đủ file
- [x] 4.2 Kiểm frontmatter `SKILL.md` có `name:` và `allowed-tools:` trước khi ghi; verify: test với SKILL.md thiếu `allowed-tools` bị từ chối và nêu trường thiếu
- [x] 4.3 Không ghi đè khi đích tồn tại và thiếu `--force`; verify: test thoát 1, in đường dẫn, không ghi file
- [x] 4.4 Thêm subcommand `install-skill` vào `utd/cli.py` với `--target`, `--force`, `--dry-run`; verify: `utd install-skill --help` liệt kê đủ ba cờ
- [x] 4.5 `--dry-run` liệt kê file sẽ ghi và không tạo file; verify: test so danh sách và kiểm thư mục đích không tồn tại sau lệnh

## 5. Metadata gói

- [x] 5.1 Viết `pyproject.toml` với `requires-python >= 3.10`, deps `openpyxl>=3.1`, extra `yaml`, entry point `utd = "utd.cli:main"`; verify: `python -m build` tạo được wheel
- [x] 5.2 Khai `package-data` cho `_data/**`; verify: `python -m zipfile -l dist/*.whl | grep _data` thấy 10 rule + 3 data + SKILL.md
- [x] 5.3 Thêm `LICENSE` MIT với tên tác giả `h004888`; verify: file tồn tại, có dòng "MIT License"
- [x] 5.4 Viết `README.md`: cài từ release, 8 lệnh, `utd install-skill`, cách gỡ; verify: có đủ 4 mục, grep thấy đủ 8 tên lệnh
- [x] 5.5 Mở rộng `.gitignore`: `dist/`, `build/`, `*.egg-info/`, `*.whl`; verify: `git status` không thấy artefact sau build

## 6. Đưa `openspec/` vào repo

- [ ] 6.1 Copy `temp_test/openspec/` → `unit-test-designer/openspec/`; verify: 13 file, `openspec list --json` chạy được từ trong repo mới
- [ ] 6.2 Kiểm `openspec validate --specs --strict` trong repo mới; verify: 8 spec pass

## 7. CI

- [ ] 7.1 Viết `.github/workflows/ci.yml`: matrix Python 3.10/3.11/3.12 × ubuntu/windows, cài `.[yaml]` + pytest, chạy `pytest -q`; verify: file parse được bằng `python -c "import yaml; yaml.safe_load(open(...))"`
- [ ] 7.2 Thêm job `build` phụ thuộc `test`, chạy `python -m build`; verify: job khai `needs: test`
- [ ] 7.3 Thêm bước kiểm wheel chứa `_data` bằng Python zipfile, fail nếu thiếu; verify: script in rõ số file rule/data tìm thấy

## 8. Kiểm chứng trong venv sạch

- [ ] 8.1 Tạo venv mới, `pip install dist/*.whl`; verify: `utd --version` in `utd 2.0.0`
- [ ] 8.2 Chạy `utd install-skill --target <tmp>` trong venv; verify: SKILL.md và references/ có mặt, frontmatter đúng
- [ ] 8.3 Chạy e2e 8 stage bằng `utd` từ venv trên fixture trong `_data/skill/assets/`; verify: ingest → inventory → interview → lock → generate → audit → emit đều exit 0, audit 9/9 PASS
- [ ] 8.4 `pip uninstall -y unit-test-designer`; verify: `utd` không còn trong venv, venv vẫn dùng được

## 9. Release workflow

- [ ] 9.1 Viết `.github/workflows/release.yml`: trigger `push: tags: ['v*']`, `permissions: contents: write`, build wheel, `gh release create`; verify: file parse được bằng yaml, có khai `permissions`
- [ ] 9.2 Kiểm workflow không chạy trên push thường; verify: `on:` chỉ có `push.tags`

## 10. Push lên GitHub — CẦN XÁC NHẬN RIÊNG

- [ ] 10.1 `git init` mới trong `unit-test-designer/`, commit đầu với `feat: unit-test-designer v2.0.0`; verify: `git log --oneline` có đúng 1 commit, `git ls-files | grep -c "\.claude\|\.agents"` = 0
- [ ] 10.2 Thêm remote `https://github.com/h004888/unit-test-designer.git`; verify: `git remote -v` đúng URL
- [ ] 10.3 **DỪNG — xin xác nhận người dùng** trước khi push lần đầu lên repo PUBLIC; verify: người dùng trả lời đồng ý
- [ ] 10.4 Push `master` lên remote; verify: `gh repo view h004888/unit-test-designer --json isEmpty` trả `false`
- [ ] 10.5 Kiểm history công khai không chứa skill ngoài; verify: `git log --all --name-only --pretty=format: | sort -u | grep -c "\.claude\|\.agents"` = 0

## Workflow follow-up

- Archive change sau khi review xong.
- Kiểm chứng lại kết quả đã archive.
