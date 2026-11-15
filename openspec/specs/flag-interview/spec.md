# flag-interview Specification

## Purpose
Bảo đảm sáu cờ nghiệp vụ quyết định phạm vi kiểm thử đều được con người xác nhận trước khi khoá đặc tả, và khi câu trả lời làm thay đổi tập rule áp dụng thì checklist được cập nhật theo kiểu chỉ thêm — không làm mất hay vô hiệu hoá câu trả lời đã có.

## Requirements

### Requirement: Sáu câu hỏi cờ cho mỗi module

Hệ thống SHALL sinh đúng sáu câu hỏi cờ cho mỗi module ở stage inventory: `has_status_field`, `has_quota`, `has_dependencies`, `is_multi_tenant`, `has_unique_field`, `has_currency`. Mỗi câu MUST có `tier: "CRITICAL"` và `id` dạng `<sheet_name>_FLAG_<flag_name>`.

#### Scenario: Đủ sáu câu cờ
- **WHEN** `utd inventory` chạy trên spec có 2 module
- **THEN** checklist chứa đúng 12 mục có `rule_id` bắt đầu bằng `FLAG:`, sáu mục cho mỗi module

#### Scenario: Câu cờ luôn CRITICAL
- **WHEN** mục câu hỏi có `rule_id` dạng `FLAG:has_quota`
- **THEN** mục đó có `tier: "CRITICAL"` và `target: "flag:has_quota"`

#### Scenario: Id ổn định giữa các lần chạy
- **WHEN** `utd inventory` chạy hai lần trên cùng spec với cùng tập rule
- **THEN** id của sáu mục cờ giống hệt nhau ở cả hai lần

### Requirement: Cờ suy đoán hiển thị giá trị để xác nhận

Ba cờ `has_status_field`, `is_multi_tenant`, `has_currency` SHALL hiển thị giá trị đã suy đoán trong nội dung câu hỏi và cung cấp hai lựa chọn "Đồng ý" / "Sửa thành ngược lại". Ba cờ còn lại MUST hỏi trắng với hai lựa chọn Có/Không và không nêu giá trị mặc định như thể đã biết.

#### Scenario: Cờ inferred nêu giá trị suy đoán
- **WHEN** module có tham số `currency` nên `has_currency` được suy là `true`
- **THEN** câu hỏi `FLAG:has_currency` chứa giá trị đã suy và lựa chọn đầu tiên là xác nhận giá trị đó

#### Scenario: Cờ user-only không nêu giá trị mặc định
- **WHEN** module có `has_quota` ở `source: "default"`
- **THEN** câu hỏi `FLAG:has_quota` chỉ có hai lựa chọn Có và Không, không tuyên bố giá trị hiện tại như một sự thật đã biết

### Requirement: Trả lời câu cờ cập nhật giá trị cờ

`utd interview --apply` SHALL nhận diện câu trả lời có `rule_id` bắt đầu bằng `FLAG:`, chuyển giá trị trả lời thành boolean, và gọi `flags.set(name, value, source="user")` trên module tương ứng. Sau khi cập nhật, hệ thống MUST đánh giá lại toàn bộ rule trên spec đã cập nhật.

#### Scenario: Trả lời Có bật cờ
- **WHEN** người dùng trả lời "Có" cho `FLAG:has_quota` của module `POST_api_orders`
- **THEN** `module.flags.get("has_quota")` là `true` và `flags.source("has_quota")` là `"user"`

#### Scenario: Trả lời Không giữ cờ tắt nhưng đã xác nhận
- **WHEN** người dùng trả lời "Không" cho `FLAG:has_dependencies`
- **THEN** `flags.get("has_dependencies")` là `false` và `flags.source("has_dependencies")` là `"user"`

#### Scenario: Cờ inferred bị sửa ngược
- **WHEN** `has_currency` đang là `true` với nguồn `inferred` và người dùng chọn "Sửa thành Không"
- **THEN** `flags.get("has_currency")` là `false` và nguồn là `"user"`

### Requirement: Sinh lại theo kiểu chỉ thêm, giữ nguyên câu cũ

Khi cờ thay đổi làm tập rule áp dụng thay đổi, hệ thống SHALL sinh lại danh sách câu hỏi bằng cách giữ nguyên từng byte của các mục đã tồn tại (bao gồm `nonce`, `status`, `answer`, `answered_by`) và chỉ thêm mục mới cho câu hỏi có `id` chưa xuất hiện. Hệ thống MUST NOT cấp `nonce` mới cho mục đã tồn tại.

#### Scenario: Nonce của câu cũ không đổi
- **WHEN** checklist có mục `A` với `nonce` là `n1`, người dùng trả lời cờ khiến rule mới áp dụng
- **THEN** sau khi sinh lại, mục `A` vẫn có `nonce` là `n1` và giữ nguyên trạng thái trả lời

#### Scenario: Câu mới nhận nonce mới
- **WHEN** cờ `has_quota` chuyển sang `true` làm rule `H-CONC-RACE-01` áp dụng lần đầu
- **THEN** mục câu hỏi cho rule đó được thêm vào checklist với `nonce` chưa từng xuất hiện

#### Scenario: Chữ ký cũ vẫn dùng được
- **WHEN** người dùng đã ký `answers.json` cho các mục cũ trước khi sinh lại
- **THEN** `utd interview --apply` chấp nhận các mục đó mà không báo lỗi chữ ký

### Requirement: Câu trả lời cho mục đã biến mất được bỏ qua có kiểm soát

Khi câu trả lời tham chiếu `id` không còn trong checklist, hệ thống SHALL bỏ qua mục đó và ghi nhận vào báo cáo nếu `answers.json` mang `checklist_sha256` khớp giá trị sha của checklist ngay trước lần sinh lại. Nếu không khớp, hệ thống MUST từ chối toàn bộ file với exit code 4.

#### Scenario: Mục biến mất do cờ đổi thành false
- **WHEN** cờ `has_currency` chuyển thành `false` làm câu hỏi về rule tỷ giá không còn, và `answers.json` có sha khớp checklist cũ
- **THEN** mục đó được bỏ qua, `apply` vẫn thành công, và báo cáo liệt kê id bị bỏ qua

#### Scenario: Id lạ không khớp sha bị từ chối
- **WHEN** `answers.json` chứa `id` không tồn tại và sha không khớp checklist nào đã ghi
- **THEN** `apply` từ chối toàn bộ file với exit code 4 và không ghi mục nào

### Requirement: Lý do bỏ qua rule phải trung thực về cờ

Khi một rule bị bỏ qua vì điều kiện phụ thuộc cờ còn ở nguồn `default`, trường `skipped_reason` SHALL nêu tên cờ chưa được xác nhận. Hệ thống MUST NOT ghi lý do chung chung kiểu "điều kiện không thoả" cho trường hợp này.

#### Scenario: Lý do nêu tên cờ chưa xác nhận
- **WHEN** rule `H-STATE-UNIQUE-01` có điều kiện `has_unique_field == true` và cờ còn `default`
- **THEN** `skipped_reason` chứa chuỗi nêu rõ `has_unique_field` chưa được xác nhận

#### Scenario: Lý do khác khi cờ đã xác nhận là false
- **WHEN** cờ `has_unique_field` đã được người dùng xác nhận là `false`
- **THEN** `skipped_reason` nêu điều kiện không thoả theo nghĩa nghiệp vụ, không còn nhắc tới việc chưa xác nhận

### Requirement: Lock từ chối khi còn cờ chưa xác nhận

`utd lock` SHALL từ chối khoá đặc tả khi bất kỳ module nào còn cờ ở `source: "default"`, và MUST nêu danh sách `sheet_name` cùng tên cờ còn thiếu. Điều kiện này độc lập với điều kiện câu hỏi PENDING và điều kiện nguồn câu trả lời.

#### Scenario: Còn cờ default thì không khoá được
- **WHEN** checklist có `has_unique_field` ở `source: "default"` và người dùng gõ `Chốt`
- **THEN** `utd lock` từ chối, không tạo `locked_spec.json`, và nêu tên cờ còn thiếu

#### Scenario: Đủ sáu cờ đã xác nhận thì khoá được
- **WHEN** cả sáu cờ ở mọi module đều có `source: "user"`
- **THEN** điều kiện cờ không chặn `utd lock`

### Requirement: Lock đối chiếu checklist đã verify

`utd lock` SHALL so sha256 của `checklist.json` hiện tại với `checklist_sha256` ghi trong `interview/verified.json`. Khi lệch, hệ thống MUST từ chối khoá và nêu rằng checklist đã thay đổi sau bước verify.

#### Scenario: Checklist sửa sau verify
- **WHEN** `checklist.json` bị sửa sau khi `interview --verify` đã chạy
- **THEN** `utd lock` từ chối và nêu sha mong đợi so với sha thực tế

#### Scenario: Checklist không đổi
- **WHEN** sha của checklist khớp `verified.json`
- **THEN** điều kiện này không chặn `utd lock`

### Requirement: Lock ghi cờ đã xác nhận vào đặc tả đã khoá

`utd lock` SHALL đọc `checklist.modules[].flags` và ghi đè giá trị cùng nguồn gốc của sáu cờ vào `locked_spec.modules[].flags` cho từng module khớp `id`. Bản `locked_spec.json` MUST phản ánh giá trị người dùng đã xác nhận, không phải giá trị còn trong `spec.json`.

#### Scenario: Cờ đúng tới được generate
- **WHEN** người dùng xác nhận `has_quota = true` và `utd lock` chạy thành công
- **THEN** `locked_spec.modules[*].flags.values.has_quota` là `true` với `source: "user"` ở mọi module có trong checklist

#### Scenario: Không mất cờ của module ngoài checklist
- **WHEN** `spec.json` có module không xuất hiện trong checklist
- **THEN** `locked_spec` giữ nguyên cờ của module đó như trong `spec.json`

### Requirement: Inventory cảnh báo khi chạy lại sau khi đã trả lời

`utd inventory` SHALL phát hiện checklist hiện có đã chứa câu trả lời và, nếu lần chạy này thêm câu hỏi mới, in cảnh báo rằng cần xuất lại `interview.html` để thấy câu mới.

#### Scenario: Có câu mới thì nhắc xuất lại
- **WHEN** `utd inventory` chạy lại và số câu hỏi tăng so với checklist cũ
- **THEN** lệnh in cảnh báo nêu số câu mới thêm và nhắc xuất lại giao diện

#### Scenario: Không có câu mới thì không cảnh báo
- **WHEN** `utd inventory` chạy lại và không có câu hỏi mới
- **THEN** lệnh không in cảnh báo xuất lại giao diện
