# Proposal

## Why

`unit-test-designer` hiện có kho tri thức đúng (150 heuristic rule, 701 payload, 82 bản ghi dữ liệu thực tế) nhưng cách thi hành sai: bộ lọc ngữ cảnh động bỏ qua trường `trigger_condition` có sẵn trong JSON và dùng if-chain chỉ phủ 37/72 `target_element`, nên tối đa chỉ 83/150 rule có thể kích hoạt — 51 rule không bao giờ được hỏi dù spec thế nào. Cùng lúc, `test_matrix_generator.py` và `test_budget_calculator.py` chỉ đọc `modules[0].methods[0]` nên tuyên bố trong `SKILL.md` ("bảo đảm 100% vượt qua Gatekeeper ngay từ lượt đầu tiên") sai với mọi spec nhiều API, còn cơ chế "tamper-proof" lại dựa vào `--answered-by` có giá trị mặc định `USER` nên AI tự khai được. Bản cũ không có contract giữa các stage, không ghi hash, và crash Unicode trên console Windows mặc định (`cp437`). Ba gốc rễ là: luật nằm trong code thay vì trong dữ liệu, không có contract giữa các bước, và tin lời khai thay vì kiểm bằng hash.

## What Changes

- **BREAKING** Viết lại toàn bộ `unit-test-designer` thành package `utd/` với một CLI duy nhất (`utd ingest|inventory|interview|lock|generate|audit|emit|reconcile`); xoá `scripts/` (11 file, ~4195 dòng) và `tests/` (26 file, ~1559 dòng) của bản cũ.
- **BREAKING** Định nghĩa Canonical IR `schema_version: 2.0` làm contract duy nhất cho mọi stage; mọi input (OpenAPI 3.x, Swagger 2.0, spec JSON cũ, SRS văn xuôi) phải đi qua `utd ingest`.
- Thay if-chain `match_dynamic_context` (cognitive 40) bằng interpreter đánh giá trực tiếp `trigger_condition` của từng rule (54 biểu thức DSL đóng, ~60 dòng, `ast` whitelist).
- Đạt reachability 150/150: rule không áp dụng phải có `skipped_reason`, không được im lặng bỏ qua.
- Thêm cổng `G7 SOURCE-RULE-COVERAGE`, `G8 EP-PROPER`, `G9 NO-SLOP-PROPERTY`; tổng 9 cổng thay vì 6.
- Xử lý toàn bộ `modules[]`, không chỉ module đầu.
- Thay cơ chế tin `answered_by` bằng chữ ký `sha256(id|value|nonce|salt)` do UI sinh; ghi hash chain trong `run.json` để stage sau từ chối artifact đã bị sửa.
- Bỏ SQLite và bước compile: `test_knowledge.db` (derived) → `data/realistic.json` + `data/payloads.json`; bỏ `heuristic_matrix.json` (trùng nội dung).
- Giữ nguyên và tái sử dụng: 10 file `rules_domain/*.json` (150 rule), `realistic_data/*.json`, `raw_sources/` (blns 517 dòng), `example_{api_,}spec.json`, và toàn bộ spec bố cục Excel/Markdown trong `template-layout.md`.
- Rút `SKILL.md` từ 350 dòng xuống ~120 dòng: skill chỉ mô tả chạy gì và dừng khi nào; script quyết định đúng/sai.

## Capabilities

### New Capabilities

- `spec-ingestion`: chuẩn hoá mọi định dạng đầu vào về Canonical IR 2.0, kèm adapter cho spec JSON bản cũ và đường draft cho văn xuôi.
- `rule-evaluation`: đánh giá `trigger_condition` trên từng endpoint/param, gán tier CRITICAL/STANDARD, và báo cáo reachability 150/150 kèm lý do bỏ qua.
- `interview-gate`: sinh checklist có nonce, xuất giao diện trả lời, ghi câu trả lời có chữ ký, và khoá spec sau khi người dùng sign-off.
- `test-case-generation`: định lượng ngân sách, sinh khung ma trận cho mọi module, cấp dữ liệu thực tế chống slop, và duy trì truy vết rule→test case.
- `quality-audit`: 9 cổng kiểm toán kỹ thuật với exit code phân loại, chặn emit khi chưa đạt.
- `document-output`: kết xuất `.xlsx` tổng thể và bộ `.md` từ SSOT, cùng trạng thái `run.json` có hash chain.

### Modified Capabilities

Không có: dự án chưa có capability nào được đặc tả (`openspec/specs/` rỗng).

## Impact

- **Xoá**: `unit-test-designer/scripts/*.py`, `unit-test-designer/tests/*.py`, `unit-test-designer/SKILL.md` (viết lại), `unit-test-designer/references/requirement-analysis.md` (gộp vào SCHEMA.md + references/gate-rationale.md), `unit-test-designer/assets/heuristic_matrix.json`, `unit-test-designer/assets/test_knowledge.db`.
- **Chuyển**: `assets/rules_domain/` → `rules/`; `assets/realistic_data/` + bảng `realistic_user_data` → `data/realistic.json`; bảng `test_payloads` → `data/payloads.json`; `references/template-layout.md` → `references/layout-xlsx.md`.
- **Thêm**: `utd/` package (cli, io, state, canonical, dsl, ingest/, match/, interview/, generate/, audit/, emit/), `SCHEMA.md`, `tests/` mới.
- **Ràng buộc môi trường**: Python 3.10+, không dependency bắt buộc ngoài `openpyxl` (đã có 3.1.5) cho emit `.xlsx`; `pytest` chỉ cho dev.
- **Tương thích**: spec JSON bản cũ vẫn đọc được qua `utd ingest --from utd-v1`; không cam kết giữ CLI flag cũ của 11 script.
- **Rủi ro dữ liệu**: repo không có git; mọi thao tác xoá phải sau khi người dùng sao lưu `unit-test-designer/`.
- Không ảnh hưởng `openspec/`, `.claude/skills/`, `.agents/skills/`.
