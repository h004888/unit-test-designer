# interview-gate Specification

## Purpose
Bảo đảm mọi ràng buộc nghiệp vụ được chốt bởi con người chứ không do AI tự suy, bằng cách buộc câu trả lời phải đi qua giao diện do máy sinh và mang chữ ký kiểm chứng được, đồng thời khoá đặc tả sau khi người dùng sign-off để các stage sau không thể sửa lén.

## Requirements

### Requirement: Mỗi câu hỏi mang nonce duy nhất

Hệ thống SHALL sinh một `nonce` ngẫu nhiên tối thiểu 16 byte cho mỗi mục checklist tại thời điểm khởi tạo, và lưu `nonce` trong `interview/checklist.json`. Câu trả lời MUST tham chiếu đúng `nonce` của câu hỏi tương ứng.

#### Scenario: Nonce khác nhau giữa các câu
- **WHEN** checklist có 100 câu hỏi
- **THEN** cả 100 `nonce` là duy nhất và không mục nào dùng lại nonce của mục khác

#### Scenario: Nonce chỉ sinh cho câu mới khi khởi tạo lại
- **WHEN** `utd inventory` chạy lại trên cùng spec
- **THEN** câu hỏi mới nhận `nonce` mới, còn câu đã tồn tại giữ nguyên `nonce` và trạng thái trả lời của nó

### Requirement: Câu trả lời phải có chữ ký do giao diện sinh

Giao diện trả lời (`interview.html`) SHALL sinh `answers.json` chứa cho mỗi mục: `id`, `value`, `nonce`, và `sig` là `sha256(id|value|nonce|salt)`. Hệ thống MUST từ chối bất kỳ mục nào có `sig` không khớp khi tính lại.

#### Scenario: Câu trả lời hợp lệ được chấp nhận
- **WHEN** người dùng trả lời trên `interview.html` và file `answers.json` được giao diện ghi ra
- **THEN** `utd interview --apply` chấp nhận và đánh dấu mục đó ANSWERED với nguồn `USER_UI`

#### Scenario: Chữ ký sai bị từ chối
- **WHEN** một mục có `value` bị sửa sau khi giao diện đã ký
- **THEN** `utd interview --apply` từ chối toàn bộ file, nêu id vi phạm, và thoát với exit code 4

#### Scenario: Không có nonce
- **WHEN** một mục thiếu trường `nonce`
- **THEN** mục đó bị từ chối với exit code 4 và không mục nào khác trong file bị áp dụng

### Requirement: Đường dự phòng khi không dùng giao diện

Khi người dùng trả lời trực tiếp trong hội thoại, hệ thống SHALL ghi nguồn `USER_CHAT` kèm `evidence` là nguyên văn nội dung người dùng đã gửi. Mục `USER_CHAT` MUST được đánh dấu riêng trong báo cáo audit để người đọc phân biệt với câu trả lời đã ký.

#### Scenario: Trả lời qua chat được ghi nhận
- **WHEN** người dùng gõ "quantity từ 1 đến 100" trong hội thoại và AI ghi nhận qua `utd interview --answer-id <id> --value "1..100" --source chat --evidence "<nguyên văn>"`
- **THEN** mục đó có `answered_by: "USER_CHAT"` và `evidence` lưu nguyên văn

#### Scenario: Audit phân biệt nguồn
- **WHEN** checklist có cả mục `USER_UI` và `USER_CHAT`
- **THEN** `audit/report.json` liệt kê riêng số lượng và danh sách id của từng nguồn

### Requirement: Cổng chặn interview

`utd interview --verify` SHALL thoát 0 chỉ khi không còn mục PENDING và mọi mục CRITICAL có nguồn hợp lệ. Nó MUST thoát 1 khi còn PENDING và 4 khi phát hiện mục CRITICAL mang nguồn không hợp lệ.

#### Scenario: Còn câu hỏi chưa trả lời
- **WHEN** còn 3 mục PENDING, trong đó 1 mục CRITICAL
- **THEN** lệnh thoát 1 và in danh sách 3 mục kèm tier

#### Scenario: CRITICAL bị gán nguồn không hợp lệ
- **WHEN** mục CRITICAL có `answered_by: "STANDARD_BATCH"` hoặc `"MODEL"`
- **THEN** lệnh thoát 4 và nêu id vi phạm

#### Scenario: Đạt cổng
- **WHEN** 0 mục PENDING và mọi mục CRITICAL có nguồn `USER_UI` hoặc `USER_CHAT`
- **THEN** lệnh thoát 0 và ghi `interview/verified.json` kèm sha256 của `answers.json`

### Requirement: Khoá đặc tả sau sign-off

Hệ thống SHALL sinh `canonical/locked_spec.json` chỉ khi người dùng xác nhận bằng chuỗi `Chốt` hoặc `OK`, và ghi `lock.sha256` là sha256 của `locked_spec.json`. Sau khi khoá, mọi stage sau MUST từ chối làm việc nếu sha256 không khớp.

#### Scenario: Khoá thành công
- **WHEN** người dùng gửi `Chốt` và `utd lock --sign "Chốt"` chạy với answers đã verify
- **THEN** `locked_spec.json` và `lock.sha256` được tạo, exit code 0

#### Scenario: Từ chối khi thiếu sign-off
- **WHEN** `utd lock` chạy nhưng chưa có `interview/verified.json`
- **THEN** hệ thống thoát 1 và không tạo file nào

#### Scenario: Phát hiện sửa lén sau khoá
- **WHEN** `utd generate` chạy và `locked_spec.json` đã bị sửa khiến sha256 khác `lock.sha256`
- **THEN** hệ thống thoát 5, nêu tên file bị lệch, và không sinh test case

### Requirement: Giao diện trả lời phải tự chứa

`interview.html` SHALL hoạt động khi mở trực tiếp từ đĩa, không cần máy chủ hay kết nối mạng. Nó MUST hiển thị toàn bộ câu hỏi, cho phép chọn và ghi chú, và xuất `answers.json` chứa chữ ký hợp lệ khi người dùng bấm xuất.

#### Scenario: Mở offline
- **WHEN** người dùng mở `interview.html` bằng trình duyệt khi máy không có mạng
- **THEN** toàn bộ câu hỏi hiển thị và chức năng xuất file hoạt động

#### Scenario: Xuất file đúng định dạng
- **WHEN** người dùng trả lời xong và bấm xuất
- **THEN** file tải về có `id`, `value`, `nonce`, `sig` cho mỗi mục đã trả lời, và `utd interview --apply` chấp nhận file đó
