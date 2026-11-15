# Spec Delta

## Purpose

Sinh bộ test case hộp đen cho toàn bộ module trong một đặc tả đã khoá, với số lượng do ngân sách định lượng quyết định, dữ liệu lấy từ nguồn thực tế, và mỗi test case truy vết được về rule đã chốt.

## ADDED Requirements

### Requirement: Xử lý toàn bộ module

Hệ thống SHALL sinh test case cho mọi phần tử trong `modules[]`, không dừng ở module đầu tiên. Với mỗi module, nó MUST xử lý mọi endpoint và mọi method.

#### Scenario: Spec nhiều module
- **WHEN** `locked_spec.json` có 2 module và `utd generate` chạy
- **THEN** `unit_test_spec.json` chứa test case cho cả 2 module và mỗi module có ít nhất 1 test case

#### Scenario: Module không có endpoint
- **WHEN** một module có `endpoints: []`
- **THEN** module đó bị báo lỗi gate với exit code 1 và không được bỏ qua im lặng

### Requirement: Ngân sách kiểm thử định lượng trước khi sinh

Hệ thống SHALL tính ngân sách cho từng endpoint trước khi sinh test case, gồm số slot theo loại Normal, Boundary, Abnormal, và mục tiêu kỹ thuật của từng slot. Ngân sách MUST dựa trên `constraints` dạng cấu trúc và danh sách `rules`, không dựa trên việc phân tích chuỗi mô tả.

#### Scenario: Biên sinh đúng số slot
- **WHEN** endpoint có tham số `quantity` với `constraints.min=1`, `constraints.max=100`, và 2 rule gắn với nó
- **THEN** ngân sách chứa slot cho các biên `min-1`, `min`, `min+1`, `max-1`, `max`, `max+1` cùng ít nhất 1 slot Normal

#### Scenario: Không ràng buộc thì không sinh biên
- **WHEN** tham số không có `constraints.min` và `constraints.max`
- **THEN** ngân sách không sinh slot BVA cho tham số đó và ghi lý do

### Requirement: Mỗi module có ít nhất một happy path

Hệ thống SHALL bảo đảm mỗi module có ít nhất một test case `type: "Normal"` đại diện luồng thành công nằm giữa vùng hợp lệ. Nó MUST từ chối sinh bộ test mà module nào có `Normal == 0`.

#### Scenario: Module chỉ có case biên
- **WHEN** mọi test case của một module đều là `Boundary`
- **THEN** `utd generate` thoát 1 và nêu tên module thiếu Normal

#### Scenario: Happy path mặc định
- **WHEN** generator chạy trên endpoint chưa có test case
- **THEN** slot đầu tiên được tạo là `Normal` với toàn bộ tham số required ở giá trị hợp lệ

### Requirement: Dữ liệu kiểm thử lấy từ nguồn thực tế, không sinh chuỗi mẫu

Hệ thống SHALL cấp dữ liệu cho cột Input từ kho dữ liệu thực tế và bộ biến dị lỗi con người. Nó MUST NOT tự sinh các giá trị mẫu như `"John Doe"`, `"test@example.com"`, `"123 Main St"`, `"1111111111"`, hay `"P001"`.

#### Scenario: Lấy tên thật theo locale
- **WHEN** generator cần giá trị cho tham số loại `name` với locale `vi`
- **THEN** Input chứa giá trị đọc từ kho thực tế, ví dụ một họ tên tiếng Việt có dấu hoặc tên dân tộc, không phải `Nguyen Van A`

#### Scenario: Biến dị lỗi gõ
- **WHEN** generator cần dữ liệu cho case lỗi định dạng email
- **THEN** giá trị Input sinh ra từ phép biến dị lỗi con người và ghi rõ loại lỗi trong cột Note

#### Scenario: Kho dữ liệu thiếu danh mục
- **WHEN** generator cần danh mục dữ liệu không có trong kho
- **THEN** nó báo thiếu và thoát 1 thay vì rơi về giá trị mẫu

### Requirement: Truy vết rule tới test case

Mỗi test case SHALL có `rule_refs` liệt kê các `BR-xx` mà nó kiểm chứng. Mỗi rule trong spec MUST được ít nhất một test case tham chiếu; danh sách rule chưa được phủ MUST rỗng trước khi emit.

#### Scenario: Rule được phủ
- **WHEN** spec có rule `BR-02` và generator sinh case cho biên `quantity`
- **THEN** case đó có `BR-02` trong `rule_refs`

#### Scenario: Rule bị bỏ sót
- **WHEN** sau khi sinh, `BR-05` không xuất hiện trong bất kỳ `rule_refs` nào
- **THEN** `utd generate` báo `uncovered_rules: ["BR-05"]` và thoát 1

### Requirement: Cộng dồn theo đợt, giữ nguyên đợt trước

Khi thêm endpoint mới vào dự án đã có `unit_test_spec.json`, hệ thống SHALL hợp nhất endpoint mới vào SSOT mà không mất hoặc thay đổi test case của các đợt trước.

#### Scenario: Thêm API ở đợt sau
- **WHEN** `utd generate --add-endpoint new_api.json` chạy trên SSOT đã có 2 module
- **THEN** SSOT có 3 module, 2 module cũ giữ nguyên số test case và nội dung từng case

#### Scenario: Trùng mã module
- **WHEN** endpoint mới có `sheet_name` trùng module đã tồn tại
- **THEN** hệ thống thoát 1 và yêu cầu đặt tên khác, không tự ghi đè

### Requirement: Đánh số và định danh ổn định

Hệ thống SHALL đánh `UTC001`, `UTC002`… liên tục trong phạm vi từng sheet và giữ nguyên mã đã cấp cho test case cũ khi chạy lại.

#### Scenario: Chạy lại không đổi mã cũ
- **WHEN** `utd generate` chạy lại trên SSOT đã có `UTC001`–`UTC013` ở một sheet
- **THEN** mười ba mã đó giữ nguyên và case mới nhận `UTC014` trở đi

#### Scenario: Thêm case vào giữa
- **WHEN** người dùng thêm một test case vào giữa danh sách của sheet
- **THEN** case mới nhận mã mới ở cuối dải và không làm đổi mã của case phía sau
