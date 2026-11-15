# rule-evaluation Specification

## Purpose
Đánh giá chính xác biểu thức điều kiện kích hoạt mà mỗi heuristic rule đã khai trong dữ liệu, thay vì ánh xạ nhãn sang if-chain, để mọi rule trong kho tri thức đều có cơ hội áp dụng và mọi rule bị bỏ qua đều có lý do kiểm chứng được.

## Requirements

### Requirement: Biểu thức điều kiện được thông dịch, không được lập trình lại

Hệ thống SHALL đọc trường `trigger_condition` từ mỗi rule trong `rules/*.json` và đánh giá nó trên ngữ cảnh `endpoint`, `param`, và `flags` của module. Hệ thống MUST NOT dùng chuỗi `if`/`elif` dài để tái hiện logic này, và MUST NOT thêm rule mới bằng cách sửa mã Python.

#### Scenario: Rule áp cho mọi endpoint
- **WHEN** rule có `trigger_condition` là `"true"`
- **THEN** rule được đánh giá áp dụng cho mọi endpoint của mọi module

#### Scenario: Rule theo method
- **WHEN** rule có `trigger_condition` là `method in ['PUT', 'PATCH']` và endpoint là `POST`
- **THEN** rule không áp dụng cho endpoint đó và được ghi nhận là đã đánh giá

#### Scenario: Rule theo tên tham số
- **WHEN** rule có `trigger_condition` là `param.name.includes('price') || param.name.includes('amount')` và endpoint có tham số `total_amount`
- **THEN** rule áp dụng và checklist sinh ra câu hỏi gắn với tham số `total_amount`

### Requirement: Đánh giá an toàn trên dữ liệu không tin cậy

Bộ thông dịch SHALL chỉ chấp nhận các dạng biểu thức trong ngôn ngữ đóng đã khai: so sánh `==`, `!=`, thành viên `in`, kiểm tra `null`, so khớp chuỗi `.includes(...)`, và phép `&&`/`||`. Bộ thông dịch MUST NOT dùng `eval` hoặc `exec` trên chuỗi thô từ file rule.

#### Scenario: Biểu thức hợp lệ được chấp nhận
- **WHEN** rule khai `endpoint.auth.includes('jwt')`
- **THEN** bộ thông dịch đánh giá đúng giá trị boolean mà không gọi `eval` trên toàn chuỗi

#### Scenario: Biểu thức ngoài ngôn ngữ bị từ chối
- **WHEN** file rule chứa `trigger_condition` là `__import__('os').system('x')`
- **THEN** hệ thống từ chối file rule, báo rule id vi phạm, và không thực thi bất kỳ mã nào từ chuỗi đó

#### Scenario: Trường không xác định
- **WHEN** `trigger_condition` tham chiếu `foo.bar` không tồn tại trong ngữ cảnh
- **THEN** đánh giá cho kết quả `false` và ghi cảnh báo kèm rule id, không làm dừng toàn bộ quá trình

### Requirement: Reachability được báo cáo đầy đủ

Hệ thống SHALL báo cáo cho mỗi rule một trong hai trạng thái: đã áp dụng cho ít nhất một endpoint, hoặc không áp dụng cho endpoint nào. Rule không áp dụng MUST kèm `skipped_reason` nêu điều kiện đã không thoả.

#### Scenario: Toàn bộ kho rule được đánh giá
- **WHEN** `utd inventory` chạy trên spec có 2 module và kho 150 rule
- **THEN** báo cáo chứa đúng 150 mục, mỗi mục có `rule_id` và một trong `matched` hoặc `skipped_reason`

#### Scenario: Rule không áp dụng có lý do
- **WHEN** rule `H-IDEMP-WEBHOOK-SIG-01` có `trigger_condition` chứa `endpoint.path.includes('webhook')` và spec không có path webhook
- **THEN** mục của rule đó ghi `skipped_reason` nêu điều kiện path không khớp, và tổng đã áp dụng + đã bỏ qua bằng 150

### Requirement: Phân tầng CRITICAL và STANDARD theo dữ liệu

Hệ thống SHALL gán `tier` cho mỗi câu hỏi sinh ra dựa trên `strictness` và danh sách rule CRITICAL khai trong dữ liệu, không dựa trên danh sách id viết cứng trong mã. Câu hỏi CRITICAL MUST được trả lời bởi người dùng; câu hỏi STANDARD MAY được phê duyệt theo lô.

#### Scenario: Rule MANDATORY nghiệp vụ là CRITICAL
- **WHEN** rule có `strictness: "MANDATORY"` và thuộc nhóm auth, null/missing, state transition, numeric bounds, hoặc fintech
- **THEN** câu hỏi sinh ra có `tier: "CRITICAL"`

#### Scenario: Chuẩn kỹ thuật là STANDARD
- **WHEN** rule có `strictness: "CONDITIONAL"` thuộc nhóm header, transport, DoS baseline
- **THEN** câu hỏi sinh ra có `tier: "STANDARD"` và đủ điều kiện phê duyệt theo lô

### Requirement: Khử trùng lặp câu hỏi

Hệ thống SHALL sinh tối đa một câu hỏi cho mỗi cặp (`rule_id`, `endpoint_id`, `param_name`). Khi nhiều rule cùng nhãn `target_element` áp dụng cho cùng một tham số, hệ thống MUST gộp thành một mục checklist với danh sách `rule_ids` thay vì lặp câu hỏi.

#### Scenario: Gộp câu hỏi trùng chủ đề
- **WHEN** ba rule cùng áp dụng cho tham số `quantity` của endpoint `POST /api/orders`
- **THEN** checklist có một mục với `param_name: "quantity"` và `rule_ids` chứa cả ba id

#### Scenario: Không gộp khác tham số
- **WHEN** rule áp dụng cho cả `quantity` và `price`
- **THEN** checklist có hai mục riêng biệt, mỗi mục gắn đúng `param_name`
