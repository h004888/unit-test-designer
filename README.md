# unit-test-designer

Thiết kế Unit Test theo **đặc tả độc lập** (black-box) từ SRS/SRD/OpenAPI/mô tả văn xuôi.

Phỏng vấn bắt buộc để chốt Business Rules → sinh test case theo ngân sách định lượng →
kiểm toán 9 cổng → xuất Excel tổng thể + bộ Markdown.

## Cài đặt

### Từ GitHub Releases

```bash
pip install https://github.com/h004888/unit-test-designer/releases/download/v2.0.0/unit_test_designer-2.0.0-py3-none-any.whl
```

Hoặc tải file `.whl` rồi:

```bash
pip install ./unit_test_designer-2.0.0-py3-none-any.whl
```

### Từ source

```bash
git clone https://github.com/h004888/unit-test-designer.git
cd unit-test-designer
pip install .
```

### Cài skill vào Claude Code

```bash
utd install-skill
# Cài vào ~/.claude/skills/unit-test-designer
# Mở phiên Claude Code mới để nạp skill.
```

Tuỳ chọn: `utd install-skill --target <thư mục>`, `--force`, `--dry-run`.

### Yêu cầu

- Python >= 3.10
- `openpyxl` (cài tự động qua `pip install`)
- `pyyaml` chỉ cần khi ingest OpenAPI/Swagger dạng YAML: `pip install "unit-test-designer[yaml]"`

## Sử dụng

Quy trình 8 stage, chạy trong thư mục dự án:

```bash
# 1. Chuẩn hoá đầu vào
utd ingest --from openapi --in docs/openapi.yaml
utd ingest --from swagger --in api.json
utd ingest --from utd-v1  --in spec_cu.json
utd ingest --from draft   --in draft.json

# 2. Đánh giá 150 rule -> checklist phỏng vấn
utd inventory
# kỳ vọng: "150 rule -> N áp dụng, M bỏ qua có lý do", "reachability: 150/150 OK"

# 3. Phỏng vấn
utd interview --export-html .unittest-design/interview/interview.html
# mở file HTML, trả lời, xuất answers.json
utd interview --apply .unittest-design/interview/answers.json
utd interview --answer-id <id> --value "..." --evidence "<nguyên văn user>"
utd interview --batch-consent    # chỉ STANDARD
utd interview --verify

# 4. Khoá sau khi người dùng gõ "Chốt"/"OK"
utd lock --sign "Chốt"

# 5. Sinh test case cho mọi module
utd generate
utd generate --add-endpoint new_api.json

# 6. Kiểm toán 9 cổng
utd audit

# 7. Xuất tài liệu
utd emit --xlsx .unittest-design/unit_test.xlsx --md-dir .unittest-design/docs

# 8. Đối chiếu mã nguồn (chỉ khi được yêu cầu)
utd reconcile
```

### Sáu câu hỏi cờ

Mỗi module có 6 câu hỏi cờ CRITICAL (`has_status_field`, `has_quota`, `has_dependencies`,
`is_multi_tenant`, `has_unique_field`, `has_currency`). Chúng quyết định rule nào áp dụng;
`utd lock` sẽ chặn nếu còn cờ chưa xác nhận.

Trả lời cờ xong, `utd inventory` tự sinh thêm câu cho rule vừa kích hoạt — xuất lại
`interview.html` để thấy câu mới (câu đã trả lời giữ nguyên, không cần ký lại).

### Mã exit

| Mã | Ý nghĩa |
|---|---|
| 0 | pass |
| 1 | gate block |
| 2 | input invalid |
| 3 | thiếu thông tin |
| 4 | tamper (chữ ký sai) |
| 5 | hash mismatch |

## Đầu ra

```
.unittest-design/
  canonical/spec.json              # sau ingest
  canonical/locked_spec.json       # sau lock
  canonical/unit_test_spec.json    # SSOT, nguồn duy nhất cho tài liệu
  interview/checklist.json  interview.html  answers.json  verified.json
  audit/report.json  audit/report.md
  unit_test.xlsx                   # Cover | Test Cases | Test Statistics | mỗi API 1 sheet
  docs/index.md  docs/<API>.md
  run.json                         # chuỗi hash từng artifact
```

Tài liệu chi tiết: `utd install-skill` cài `SCHEMA.md` và `references/` vào skill dir,
hoặc đọc trực tiếp trong `utd/_data/skill/`.

## Gỡ cài đặt

```bash
pip uninstall -y unit-test-designer
rm -rf ~/.claude/skills/unit-test-designer
```

## Phát triển

```bash
pip install -e ".[dev,yaml]"
pytest -q
```

## Giấy phép

MIT — xem [LICENSE](LICENSE).
