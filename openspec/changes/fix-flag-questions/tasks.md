# Tasks

## 1. Sinh câu hỏi cờ

- [x] 1.1 Viết `utd/match/flags_questions.py` với `FLAG_META` mô tả 6 cờ: tên, nhãn tiếng Việt, cờ nào `inferred`; verify: test import được và `len(FLAG_META) == 6`
- [x] 1.2 Thêm `build_flag_questions(module)` sinh 6 `Question` với `id=<sheet>_FLAG_<name>`, `tier=CRITICAL`, `target=flag:<name>`; verify: test 1 module cho đúng 6 mục, 2 module cho 12 mục
- [x] 1.3 Với 3 cờ `inferred`: nội dung câu nêu giá trị đã suy, lựa chọn đầu là "Đồng ý"; verify: test `has_currency=true` có "Đồng ý" ở vị trí đầu và câu chứa giá trị đã suy
- [x] 1.4 Với 3 cờ `user-only`: không nêu giá trị mặc định, lựa chọn là Có/Không; verify: test câu `FLAG:has_quota` không chứa chuỗi khẳng định hiện trạng
- [x] 1.5 Tích hợp vào `match_spec` để 6 câu cờ nằm trong `report.questions`; verify: test `example_api_spec.json` có 12 câu `FLAG:*` (6 × 2 module)

## 2. Sinh lại kiểu append-merge

- [x] 2.1 Viết `reconcile_checklist(old_checklist, new_checklist)` merge theo `id`, giữ nguyên đối tượng cũ; verify: test mục có trong cả hai giữ `nonce`, `status`, `answer` y hệt
- [x] 2.2 Câu mới (id chỉ có ở `new`) được thêm vào cuối checklist; verify: test sau merge, `len(questions)` = cũ + mới
- [x] 2.3 Mục chỉ có ở `old` được ghi vào `removed_questions` kèm `removed_reason`; verify: test cờ true→false làm câu rule biến mất và xuất hiện trong `removed_questions`
- [x] 2.4 Ghi `previous_sha256` = sha checklist trước khi merge; verify: test `previous_sha256` khớp sha tính trên checklist đầu vào
- [x] 2.5 `utd inventory` dùng `reconcile_checklist` thay vì ghi đè; verify: test chạy inventory 2 lần giữ nguyên `nonce` của các câu cũ

## 3. Ghi cờ từ câu trả lời

- [x] 3.1 Trong `apply_answers`, nhận diện `rule_id` bắt đầu bằng `FLAG:`; verify: test câu `FLAG:has_quota` được nhận diện, câu rule thường không bị nhầm
- [x] 3.2 Chuyển giá trị trả lời thành bool (Có/true/1 → true; Không/false/0 → false) và gọi `flags.set(name, value, source="user")`; verify: test trả lời "Có" cho ra `get=True`, `source="user"`
- [x] 3.3 Sau khi cập nhật cờ, chạy lại đánh giá rule và merge vào checklist hiện tại; verify: test trả lời `has_quota=true` làm 2 rule quota xuất hiện trong checklist
- [x] 3.4 Giá trị trả lời không nhận diện được boolean → từ chối mục đó với thông báo cụ thể; verify: test trả lời "tuỳ" cho câu cờ bị từ chối và nêu id

## 4. Bỏ qua mục đã biến mất có kiểm soát

- [x] 4.1 `apply` bỏ qua mục answers có `id` nằm trong `removed_questions` khi `answers.json.checklist_sha256` khớp `checklist.previous_sha256`; verify: test bỏ qua thành công, `apply` exit 0, báo cáo liệt kê id bỏ qua
- [x] 4.2 Không khớp sha → từ chối toàn bộ file với exit 4; verify: test sha sai cho exit 4 và không mục nào được ghi
- [x] 4.3 Id lạ không nằm trong `removed_questions` → vẫn exit 4 như hành vi hiện tại; verify: test id rác bị từ chối

## 5. Lý do bỏ qua trung thực

- [x] 5.1 Viết `_flag_dependencies(rule)` trả danh sách cờ mà `trigger_condition` tham chiếu; verify: test `has_quota == true` trả `["has_quota"]`, điều kiện không có cờ trả `[]`
- [x] 5.2 `_skip_reason` kiểm cờ còn `default` và trả lý do "cờ X chưa được xác nhận — cần trả lời câu FLAG:X"; verify: test `H-STATE-UNIQUE-01` có lý do nêu `has_unique_field`
- [x] 5.3 Cờ đã xác nhận là false → giữ lý do nghiệp vụ, không nhắc "chưa xác nhận"; verify: test set cờ `source="user"` xong lý do không chứa "chưa được xác nhận"

## 6. Siết lock

- [x] 6.1 `lock` so sha checklist hiện tại với `verified.json.checklist_sha256`, lệch → exit 1 nêu hai giá trị; verify: test sửa checklist sau verify cho exit 1
- [x] 6.2 `lock` từ chối khi còn cờ `source == "default"`, nêu `sheet_name` + tên cờ; verify: test còn 1 cờ default cho exit 1 và không tạo `locked_spec.json`
- [x] 6.3 `lock` đọc `checklist.modules[].flags` và ghi đè vào `locked_spec.modules[].flags` theo `id`; verify: test cờ `has_quota=true` ở checklist xuất hiện trong `locked_spec`
- [x] 6.4 Module có trong `spec.json` nhưng không có trong checklist giữ nguyên flags cũ; verify: test module ngoài checklist không bị reset cờ
- [x] 6.5 Ba điều kiện mới không làm hỏng luồng hợp lệ; verify: test e2e đầy đủ trên fixture vẫn exit 0 tới emit

## 7. Cảnh báo re-run

- [x] 7.1 `inventory` đếm số câu mới so với checklist cũ và in cảnh báo khi checklist cũ đã có mục ANSWERED; verify: test chạy inventory lần 2 sau khi trả lời cho thấy cảnh báo kèm số câu mới
- [x] 7.2 Không có câu mới → không cảnh báo; verify: test chạy inventory 2 lần không đổi cờ không in cảnh báo

## 8. Đo lường và tài liệu

- [x] 8.1 Test khẳng định sau khi trả lời 3 cờ `user-only = true`, `matched` đạt 97 (từ 92) trên `example_api_spec.json`; verify: test so số cụ thể
- [x] 8.2 Cập nhật `SCHEMA.md`: thêm mục câu hỏi cờ, `removed_questions`, `previous_sha256`, và ghi rõ `checklist_sha256` là dấu hiệu không phải chữ ký; verify: `grep` thấy cả bốn mục
- [x] 8.3 Cập nhật `SKILL.md` mục "Điều kiện dừng": lock chặn khi còn cờ default; verify: `grep` thấy điều kiện cờ trong bảng dừng
- [x] 8.4 Chạy toàn bộ test; verify: `pytest -q` 0 failed
- [x] 8.5 Chạy e2e 8 stage trên fixture; verify: matched 92→97 khi 3 cờ user-only = true, và questions 98 (có 12 câu cờ) khi cờ default — số liệu đo lại 2026-11-16 khác kế hoạch ban đầu 86→92 do cờ đã có sẵn 6 câu/module

## Workflow follow-up

- Archive change sau khi review xong.
- Kiểm chứng lại kết quả đã archive.
