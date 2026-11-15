# Tasks

## 1. Sinh id theo khoá gộp

- [x] 1.1 Thêm `endpoint_question_id(sheet, target)` trả `row:<sheet>:endpoint:<target>` và `param_question_id(sheet, param, target)` trả `row:<sheet>:param:<param>:<target>`; verify: test hai hàm cho đúng chuỗi với sheet/param có dấu cách và dấu hai chấm
- [x] 1.2 Đổi `_build_question` dùng hai hàm trên thay vì `sheet_name + rule["id"]`; verify: test id của câu cấp endpoint chứa `:endpoint:`, câu cấp param chứa `:param:<tên>:`
- [x] 1.3 Giữ nguyên dạng id của câu cờ (`<sheet>_FLAG_<name>`) để không phá `fix-flag-questions`; verify: test 12 câu cờ vẫn có id cũ
- [x] 1.4 Đảm bảo id không phụ thuộc thứ tự rule trong ruleset; verify: test đảo thứ tự `ruleset.rules` rồi so tập id, phải bằng nhau

## 2. Cảnh báo khi rule_ids mở rộng

- [x] 2.1 Viết `expanded_answered_questions(old, new)` trả danh sách `(id, added_rule_ids)` cho câu đã ANSWERED mà `rule_ids` mới ⊃ cũ; verify: test câu PENDING không lọt vào, câu ANSWERED có rule mới thì có
- [x] 2.2 `utd inventory` in cảnh báo dùng hàm trên, tối đa 10 dòng kèm tổng số còn lại; verify: test chạy inventory sau khi bật cờ cho thấy cảnh báo nêu id và rule mới
- [x] 2.3 `_regenerate_after_flags` cũng in cảnh báo tương tự; verify: test `interview --apply` với câu cờ cho thấy cảnh báo mở rộng nếu có câu đã trả lời
- [x] 2.4 Không cảnh báo khi cờ không đổi; verify: test inventory hai lần cùng cờ không in cảnh báo mở rộng

## 3. Đo và khoá hành vi

- [x] 3.1 Test: bật cả 6 cờ trên fixture → số id biến mất = 0; verify: test so tập id trước/sau
- [x] 3.2 Test: bật cả 6 cờ → số câu mới = 8; verify: test so số cụ thể
- [x] 3.3 Test: bật cả 6 cờ → số câu giữ id với `rule_ids` tăng = 6; verify: test so số cụ thể
- [x] 3.4 Test: câu đã ANSWERED giữ nguyên `nonce`, `status`, `answer` sau khi `rule_ids` tăng; verify: test so từng trường

## 4. Tương thích và tài liệu

- [x] 4.1 Cập nhật các test dùng id cứng dạng cũ (`sheet_ruleid_param`); verify: `pytest -q` 0 failed
- [x] 4.2 Cập nhật `SCHEMA.md`: dạng id `row:...`, phân biệt `id` (ổn định) với `rule_id` (tham khảo, có thể đổi); verify: `grep` thấy dạng `row:` và câu giải thích
- [x] 4.3 Ghi mục tương thích ngược trong `SCHEMA.md`: checklist cũ có id dạng cũ sẽ bị coi là câu mới sau nâng cấp; verify: `grep` thấy mục này
- [x] 4.4 Chạy e2e 8 stage trên fixture; verify: mọi stage exit 0 và audit 9/9 PASS

## Workflow follow-up

- Archive change sau khi review xong.
- Kiểm chứng lại kết quả đã archive.
