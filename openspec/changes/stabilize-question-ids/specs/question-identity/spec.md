# Spec Delta

## Purpose

Bảo đảm định danh câu hỏi không phụ thuộc vào rule nào tình cờ khớp trước, để câu trả lời của người dùng không bị mất khi cờ nghiệp vụ thay đổi và làm tập rule áp dụng co giãn.

## ADDED Requirements

### Requirement: Id câu hỏi dựa trên nhóm, không dựa trên rule đại diện

Hệ thống SHALL đặt `question_id` từ khóa gộp (`sheet_name`, `target_element`, `param_name`) thay vì từ `rule_id` của rule đại diện. Câu cấp endpoint MUST có dạng `row:<sheet>:endpoint:<target>`; câu cấp tham số MUST có dạng `row:<sheet>:param:<param>:<target>`.

#### Scenario: Id không đổi khi rule đại diện đổi
- **WHEN** hai rule cùng `target_element` áp dụng cho một endpoint, rule đầu tiên khớp thay đổi do cờ nghiệp vụ
- **THEN** `id` của câu hỏi nhóm đó giữ nguyên, chỉ `rule_id` và `rule_ids` thay đổi

#### Scenario: Id phân biệt câu endpoint và câu tham số
- **WHEN** cùng một endpoint có câu nhóm cấp endpoint và câu nhóm cho tham số `quantity`
- **THEN** hai câu có id khác nhau: một chứa `:endpoint:` và một chứa `:param:quantity:`

#### Scenario: Hai tham số cùng target không đụng id
- **WHEN** hai tham số `quantity` và `price` cùng có rule với `target_element = integer_or_number_param`
- **THEN** hai câu hỏi có id khác nhau, mỗi id chứa tên tham số tương ứng

### Requirement: Id ổn định qua các lần sinh lại

Khi cờ nghiệp vụ thay đổi, hệ thống SHALL bảo toàn `id` của mọi câu hỏi mà nhóm của nó vẫn tồn tại. Câu có id không đổi MUST giữ nguyên `nonce`, `status`, `answer`, và `answered_by`.

#### Scenario: Cờ bật làm nhóm mở rộng, id không đổi
- **WHEN** cờ `has_status_field` bật làm bốn rule mới cùng `target_element = state_machine_endpoint` áp dụng
- **THEN** câu nhóm `state_machine_endpoint` giữ nguyên id, `nonce`, và câu trả lời đã có; `rule_ids` của nó tăng lên

#### Scenario: Cờ tắt làm nhóm biến mất
- **WHEN** cờ `has_currency` tắt và không còn rule nào với `target_element = financial_endpoint` áp dụng
- **THEN** câu nhóm đó biến mất khỏi checklist và id của nó được ghi vào `removed_questions`

### Requirement: Cảnh báo khi nội dung câu đã trả lời mở rộng

Khi một câu đã `ANSWERED` có `rule_ids` tăng sau lần sinh lại, hệ thống SHALL in cảnh báo nêu id câu, số rule mới, và danh sách rule mới, kèm nhắc rằng câu trả lời hiện có được áp dụng cho cả các rule mới.

#### Scenario: Câu trả lời cũ phủ rule mới
- **WHEN** câu `row:POST_api_orders:endpoint:state_machine_endpoint` đã ANSWERED với 1 rule, sau đó cờ bật làm nó có 5 rule
- **THEN** `utd inventory` in cảnh báo nêu id câu, 4 rule mới, và nhắc trả lời lại nếu cần

#### Scenario: Câu chưa trả lời không cảnh báo
- **WHEN** câu có `rule_ids` tăng nhưng `status` vẫn là `PENDING`
- **THEN** không in cảnh báo mở rộng, vì người dùng sẽ trả lời một lần cho cả nhóm

### Requirement: Đo được là không mất id khi cờ đổi

Trên bộ dữ liệu kiểm chứng `assets/example_api_spec.json`, khi bật cả sáu cờ nghiệp vụ, hệ thống SHALL không làm mất id của bất kỳ câu hỏi nào mà nhóm của nó vẫn còn ít nhất một rule áp dụng.

#### Scenario: Sáu cờ bật không mất câu trả lời
- **WHEN** bật cả 6 cờ trên spec fixture và chạy lại đánh giá
- **THEN** số id biến mất là 0; số câu mới là 8; số câu giữ id với `rule_ids` tăng là 6
