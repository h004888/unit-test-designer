# Proposal

## Why

Change `fix-flag-questions` đã đóng lỗ hổng cờ nghiệp vụ, nhưng verify-change phát hiện một hành vi chưa được mô tả: khi cờ thay đổi, `question_id` đổi theo dù nhóm câu hỏi không đổi. Nguyên nhân là id được đặt theo **rule đại diện** (`utd/match/engine.py:376-381`) trong khi việc gộp nhóm dựa trên **group key** (`:301-302`). Cờ quyết định rule nào khớp trước, nên đại diện đổi, nên id đổi.

Đo trên `assets/example_api_spec.json` khi bật cả 6 cờ:

```
6 câu biến mất id
7 rule trong những câu đó VẪN áp dụng (không phải rule chết)
mỗi rule chuyển sang câu có đại diện mới:
  H-STATE-ARCHIVE-READONLY-01    -> ...H-STATE-TRANS-INVALID-01
  H-STATE-CONDITIONAL-TRANS-01   -> ...H-STATE-TRANS-INVALID-01
  H-STATE-CYCLE-DETECTION-01     -> ...H-STATE-TRANS-INVALID-01
  H-STATE-ROLLBACK-STATE-01      -> ...H-STATE-TRANS-INVALID-01
  H-STATE-TERMINAL-01            -> ...H-STATE-TRANS-INVALID-01
  H-CONC-TENANT-QUOTA-01         -> ...H-SEC-TENANT-01
  H-FIN-INVENTORY-RESERVATION-01 -> ...H-CONC-RACE-01
```

Hệ quả người dùng: trả lời 88 câu, bật cờ, còn 82 ANSWERED — mất 6 câu trả lời dù rule vẫn cần được hỏi. Cơ chế append-merge của `fix-flag-questions` (D2/D3) không cứu được vì id đã khác.

## What Changes

- Đặt `question_id` theo **group key** thay vì rule đại diện, dạng `row:<sheet>:endpoint:<target>` cho câu cấp endpoint và `row:<sheet>:param:<param>:<target>` cho câu cấp tham số.
- Giữ nguyên cách gộp (theo `target_element`) — không đổi số câu, không phá mô hình 1 nhóm = 1 câu.
- Khi một câu đã trả lời có `rule_ids` tăng do cờ thay đổi, in cảnh báo liệt kê rule mới kèm nhắc trả lời lại nếu cần.
- Hệ quả kỳ vọng đo trên fixture: id biến mất 6 → 0, câu mới vẫn 8, 6 câu giữ id với `rule_ids` tăng.

## Capabilities

### New Capabilities

- `question-identity`: quy tắc đặt id câu hỏi sao cho id ổn định qua các lần sinh lại, và cách xử lý khi nội dung một câu mở rộng.

### Modified Capabilities

Không có. `specs/rule-evaluation` của `rebuild-unit-test-designer-v2` đã có sửa scenario nonce; change này chỉ thêm capability mới cho phần id.

## Impact

- **Sửa**: `unit-test-designer/utd/match/engine.py` (`_build_question`, thêm hàm sinh id theo group key), `utd/cli.py` (cảnh báo khi `rule_ids` tăng), `SCHEMA.md` (mục checklist ghi rõ dạng id mới).
- **Thêm test**: `tests/test_question_identity.py` — id ổn định khi cờ đổi, id không đụng nhau giữa endpoint/param, cảnh báo `rule_ids` tăng.
- **Không đổi**: cách gộp, số câu, nonce, chữ ký, `answers.json`, `removed_questions`, `previous_sha256`.
- **Tương thích ngược**: checklist cũ (id dạng rule đại diện) sẽ không khớp id mới → toàn bộ câu bị coi là "mới". Đây là hành vi chấp nhận được: người dùng chạy lại `utd inventory` và trả lời lại. Ghi rõ trong `SCHEMA.md`.
