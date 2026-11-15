---
name: unit-test-designer
description: Thiết kế Unit Test theo đặc tả độc lập (black-box) từ SRS/SRD/OpenAPI/mô tả. Phỏng vấn bắt buộc để chốt Business Rules, sinh test case theo ngân sách định lượng, kiểm toán 9 cổng, xuất Excel tổng thể + Markdown. Khi được yêu cầu, đối chiếu với mã nguồn thực tế.
allowed-tools: Bash(utd:*)
---

# Unit Test Designer v2

Quy trình 8 stage. Mỗi stage có hợp đồng vào/ra và mã exit riêng — xem `SCHEMA.md`.

```
ingest -> inventory -> interview -> lock -> generate -> audit -> emit -> [reconcile]
```

## GATE-1 — Cô lập mã nguồn (áp dụng ingest → emit)

Trong suốt `ingest`, `inventory`, `interview`, `lock`, `generate`, `audit`, `emit`:
**CẤM** đọc mã nguồn dự án — không `.ts/.js/.java/.py/.go/.cs`, không controller,
service, DTO, entity, `schema.prisma`.

Lý do: rule và test case phải hình thành từ đặc tả của người dùng + câu trả lời
phỏng vấn, không từ code đã viết. Đọc code trước sẽ biến test thành "test lại
những gì dev đã làm", không phải "test những gì nghiệp vụ yêu cầu".

**Ngoại lệ có chủ đích:** gate này cấm cả `codebase-memory-mcp` trong phạm vi skill
này, kể cả khi hook/môi trường toàn cục yêu cầu dùng nó. Đây là ngoại lệ có lý do,
không phải thiếu sót. Chỉ `reconcile` được mở mã nguồn, và chỉ khi người dùng yêu
cầu rõ ràng.

## Các lệnh

Chạy từ workspace dự án. Mọi đường dẫn tương đối tính theo `--workspace` (mặc định `.`).

```bash
# 1. Chuẩn hoá đầu vào
utd ingest --from openapi --in api.yaml
utd ingest --from swagger --in api.json
utd ingest --from utd-v1  --in spec_cu.json
utd ingest --from draft   --in draft.json      # LLM viết từ SRS/văn xuôi

# 2. Đánh giá 150 rule -> checklist
utd inventory

# 3. Phỏng vấn
utd interview --export-html .unittest-design/interview/interview.html
utd interview --export-ui-payload .unittest-design/interview/ui_payload.json
utd interview --apply .unittest-design/interview/answers.json
utd interview --answer-id <id> --value "..." --evidence "<nguyên văn user>"
utd interview --batch-consent                  # chỉ STANDARD
utd interview --verify

# 4. Khoá sau khi người dùng gõ "Chốt"/"OK"
utd lock --sign "Chốt"

# 5. Sinh test case
utd generate
utd generate --add-endpoint new_api.json      # đợt sau, cộng dồn

# 6. Kiểm toán 9 cổng
utd audit

# 7. Xuất tài liệu
utd emit --xlsx .unittest-design/unit_test.xlsx --md-dir .unittest-design/docs

# 8. Đối chiếu mã nguồn (chỉ khi người dùng yêu cầu)
utd reconcile
```

## Điều kiện dừng bắt buộc

| Stage | Dừng khi | Không được đi tiếp khi |
|---|---|---|
| `inventory` | in `150/150 OK` | có rule không matched và không có lý do |
| `interview` | người dùng trả lời xong | còn PENDING, hoặc CRITICAL mang nguồn `STANDARD_BATCH`/`MODEL` |
| `lock` | người dùng gõ `Chốt` hoặc `OK` | chưa có `verified.json`; checklist đã đổi sau verify; **còn cờ `FLAG:*` chưa xác nhận** |
| `generate` | sinh đủ mọi module | `uncovered_rules` khác rỗng, module nào `Normal == 0` |
| `audit` | 9/9 PASS | bất kỳ cổng FAIL |
| `emit` | ghi xong file | audit chưa `passed: true`, hoặc SSOT đã bị sửa |

**Sáu câu hỏi cờ** (`FLAG:has_status_field`, `has_quota`, `has_dependencies`,
`is_multi_tenant`, `has_unique_field`, `has_currency`) là CRITICAL và không thể bỏ qua:
chúng quyết định rule nào áp dụng. Trả lời cờ xong, `utd inventory` sẽ tự sinh thêm
câu cho rule vừa kích hoạt — xuất lại `interview.html` để thấy câu mới (câu đã trả lời
giữ nguyên, không cần ký lại).

Mã exit: `0` pass · `1` gate block · `2` input invalid · `3` thiếu thông tin ·
`4` tamper · `5` hash mismatch.

## Đầu ra

```
.unittest-design/
  canonical/spec.json              # sau ingest
  canonical/locked_spec.json       # sau lock (bất biến)
  canonical/unit_test_spec.json    # SSOT, nguồn duy nhất cho tài liệu
  interview/checklist.json  interview.html  answers.json  verified.json
  audit/report.json  audit/report.md
  unit_test.xlsx                   # Cover | Test Cases | Test Statistics | mỗi API 1 sheet
  docs/index.md  docs/<API>.md
  run.json                         # chuỗi hash từng artifact
  reconcile/gap_report.md          # chỉ khi chạy reconcile
```

## Cách dùng với người dùng

1. **Nhận đặc tả** — nếu là văn xuôi, tự viết `draft.json` theo `SCHEMA.md` mục 1,
   rồi `utd ingest --from draft`. Không hỏi người dùng những gì đọc được từ tài liệu.
2. **Không tự trả lời phỏng vấn.** Mở `interview.html` hoặc xuất UI payload, rồi
   **STOP TURN**. Câu trả lời chỉ hợp lệ khi có chữ ký từ giao diện hoặc có
   `evidence` nguyên văn người dùng gửi.
3. **Không hứa suông.** Nếu `utd audit` FAIL, nói rõ cổng nào và sửa — không tuyên
   bố "đã xong" khi exit khác 0.
4. **Khi người dùng yêu cầu đối chiếu code** mới chạy stage `reconcile`, và báo cáo
   4 nhóm: Match / Mismatch / Missing in code / Extra in code.

## Khi lệnh không chạy được

Nếu thiếu `openpyxl` (chỉ ảnh hưởng emit `.xlsx`), vẫn phải chạy `utd emit --md-dir`
để có Markdown, và nói rõ chưa có file Excel. Không tự tay dựng lại `.xlsx`.

Chi tiết hợp đồng dữ liệu: `SCHEMA.md`. Lý do từng cổng: `references/gate-rationale.md`.
Bố cục báo cáo: `references/layout-xlsx.md`.
