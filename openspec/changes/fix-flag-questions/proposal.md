# Proposal

## Why

Change `rebuild-unit-test-designer-v2` đã hoàn tất và verify-change tìm ra một lỗi CRITICAL: ba cờ nghiệp vụ `has_quota`, `has_dependencies`, `has_unique_field` **chưa bao giờ được hỏi người dùng**, luôn nằm ở `source: "default"` với giá trị `false`, và `utd lock` vẫn cho qua. Hệ quả đo được trên `example_api_spec.json`: 5 rule phụ thuộc cờ đó bị bỏ qua với `skipped_reason` ghi sai sự thật — câu "điều kiện không thoả" che giấu việc "cờ chưa được xác nhận". Đây đúng loại lỗi mà chính dự án đặt ra để chống: hệ thống tự cho qua thay vì hỏi người dùng.

Spec `specs/spec-ingestion/spec.md` của change trước đã yêu cầu điều này (dòng 51, scenario dòng 57-59 và 53-55) nhưng code không thi hành: `utd/match/engine.py` chỉ **đọc** `flags`, `utd/interview/apply.py` không có đường ghi `flags.set(...)`, và `utd/lock.py` chỉ copy `spec.json` mà không đọc `checklist.json`. Không tồn tại đường nào để câu trả lời trở thành giá trị cờ.

## What Changes

- Sinh **6 câu hỏi cờ** cho mỗi module ở stage inventory, tier CRITICAL, id ổn định dạng `<sheet_name>_FLAG_<flag_name>`: 3 cờ `inferred` hiển thị giá trị đã suy đoán để người dùng xác nhận hoặc sửa; 3 cờ `user-only` hỏi trắng Có/Không.
- **Re-run khi apply (C3 append-merge):** khi người dùng trả lời câu cờ, `utd interview --apply` cập nhật `flags.set(name, value, source="user")` rồi chạy lại đánh giá rule. Câu hỏi đã tồn tại giữ nguyên **từng byte** (kể cả `nonce`), chỉ **thêm** câu mới cho rule vừa được kích hoạt. Không rebuild toàn bộ checklist.
- **`skipped_reason` trung thực:** khi điều kiện phụ thuộc một cờ còn `source == "default"`, lý do bỏ qua phải nêu rõ "cờ X chưa được xác nhận", không được viết "điều kiện không thoả".
- **`utd lock` siết ba điều kiện:** (a) `verified.json.checklist_sha256` phải khớp sha của checklist hiện tại; (b) từ chối khi còn bất kỳ cờ nào `source == "default"`; (c) đọc `checklist.modules[].flags` và ghi đè vào `locked_spec.modules[].flags` — nếu bỏ sót bước này, cờ vẫn `false` tới `generate` và hai điều kiện trên vô nghĩa.
- **`utd interview --apply` lenient có kiểm soát:** câu trả lời cho id không còn trong checklist bị bỏ qua (không báo lỗi) chỉ khi `answers.json` mang `checklist_sha256` khớp checklist trước lần re-run; id lạ không khớp vẫn exit 4.
- `utd inventory` in cảnh báo khi phát hiện đây là lần chạy lại sau khi đã có câu trả lời, nhắc xuất lại `interview.html`.

## Capabilities

### New Capabilities

- `flag-interview`: vòng lặp hỏi-xác nhận sáu cờ nghiệp vụ, cơ chế sinh lại theo kiểu append-merge khi cờ thay đổi, và các điều kiện khoá đi kèm.

### Modified Capabilities

Không có. Delta spec của `rebuild-unit-test-designer-v2` đã hoàn tất và giữ nguyên làm lịch sử; change này bổ sung hành vi mới trong capability riêng thay vì sửa artifact đã archive-able.

## Impact

- **Sửa**: `unit-test-designer/utd/match/engine.py` (sinh câu hỏi cờ, merge theo id, lý do bỏ qua), `utd/interview/apply.py` (ghi flags, lenient rule), `utd/lock.py` (ba điều kiện), `utd/cli.py` (cảnh báo re-run), `utd/state.py` (ghi sha checklist để phát hiện re-run).
- **Thêm test**: `tests/test_flag_questions.py` (6 câu/module, merge giữ nonce, lenient/strict, lock ba điều kiện).
- **Dữ liệu**: không đổi `rules/`, `data/`, `SCHEMA.md` chỉ thêm mục mô tả câu hỏi cờ và trạng thái re-run.
- **Tương thích**: snapshot checklist cũ vẫn đọc được; chỉ checklist thiếu câu `FLAG_*` bị coi là "chưa hỏi cờ" và `lock` sẽ chặn — đúng ý định.
- **Đo lường kỳ vọng** trên `assets/example_api_spec.json`: `matched` 92 → 97, `skipped` 58 → 53, `questions` 86 → 92, cờ còn `default` 3 → 0.
