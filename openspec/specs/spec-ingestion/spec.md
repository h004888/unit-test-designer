# spec-ingestion Specification

## Purpose
Chuẩn hoá mọi định dạng đầu vào (OpenAPI, Swagger, spec JSON bản cũ, văn xuôi) về một Canonical IR duy nhất để các stage sau chỉ phải hiểu một hình dạng dữ liệu, và từ chối đầu vào không hợp lệ bằng exit code phân loại thay vì đoán.

## Requirements

### Requirement: Canonical IR contract

Hệ thống SHALL định nghĩa Canonical IR phiên bản 2.0 gồm `schema_version`, `project`, `auth_global`, và `modules[]`. Mỗi module MUST có `id`, `module_name`, `sheet_name`, `kind`, `flags`, và `endpoints[]`. Mỗi endpoint MUST có `id`, `http_method` hoặc `kind: function`, `auth`, `params[]`, `responses[]`, `rules[]`.

#### Scenario: Spec hợp lệ được chấp nhận
- **WHEN** `utd ingest --from openapi --in petstore.yaml` chạy trên OpenAPI 3.0 hợp lệ có 3 path
- **THEN** hệ thống ghi `canonical/spec.json` với `schema_version: "2.0"`, đúng 3 endpoint, và exit code 0

#### Scenario: Spec thiếu module bị từ chối
- **WHEN** `utd ingest` chạy trên file JSON không có mảng `modules` hoặc `modules` rỗng
- **THEN** hệ thống không ghi artifact nào và thoát với exit code 2

### Requirement: Ingest adapters cho bốn loại nguồn

Hệ thống SHALL hỗ trợ bốn giá trị `--from`: `openapi`, `swagger`, `utd-v1`, và `draft`. Bốn adapter MUST cùng sinh ra một hình dạng Canonical IR. Adapter `utd-v1` MUST đọc được spec JSON do bản cũ sinh ra mà người dùng không phải sửa file tay.

#### Scenario: OpenAPI được chuyển đổi
- **WHEN** `utd ingest --from openapi --in api.yaml` gặp `paths./orders.post` có `requestBody` và `parameters`
- **THEN** mỗi path trở thành một endpoint, mỗi schema property trở thành một phần tử `params[]` với `in` tương ứng (`body`, `query`, `path`, `header`)

#### Scenario: Spec bản cũ được nâng phiên bản
- **WHEN** `utd ingest --from utd-v1 --in legacy_spec.json` chạy trên file có `modules[].methods[].api`
- **THEN** `methods[]` được làm phẳng thành `endpoints[]`, mỗi method kế thừa `sheet_name` của module chứa nó, và exit code là 0

#### Scenario: Văn xuôi không đủ dữ liệu
- **WHEN** LLM viết `draft.spec.json` từ SRS nhưng thiếu `endpoints[].params`
- **THEN** `utd ingest --from draft` từ chối với exit code 3 và liệt kê chính xác trường còn thiếu

### Requirement: Ràng buộc dạng cấu trúc, không phải chuỗi tự do

Mỗi phần tử `params[]` SHALL chứa `constraints` dạng đối tượng với các khóa `min`, `max`, `pattern`, và `enum`, dùng `null` khi không ràng buộc. Hệ thống MUST NOT suy ra biên bằng cách phân tích chuỗi mô tả ở bất kỳ stage nào sau ingest.

#### Scenario: Biên số được chuẩn hoá ngay cổng vào
- **WHEN** OpenAPI khai `quantity: {type: integer, minimum: 1, maximum: 100}`
- **THEN** `params[quantity].constraints` là `{"min":1,"max":100,"pattern":null,"enum":null}` và không stage nào phải đọc lại chuỗi để tìm biên

#### Scenario: Không ràng buộc
- **WHEN** tham số không khai `minimum`, `maximum`, `pattern` hay `enum`
- **THEN** cả bốn khóa `constraints` tồn tại với giá trị `null`, không bị bỏ khóa

### Requirement: Cờ nghiệp vụ được phân định nguồn gốc

Mỗi module SHALL có `flags` gồm sáu khóa: `has_status_field`, `has_quota`, `has_dependencies`, `is_multi_tenant`, `has_unique_field`, `has_currency`. Ba cờ đầu tiên (`has_status_field`, `is_multi_tenant`, `has_currency`) SHALL được suy tự động từ dữ liệu spec và ghi nhãn `inferred`. Ba cờ còn lại MUST được lấy từ câu trả lời của người dùng ở stage interview, không được suy đoán.

#### Scenario: Cờ suy được tự động
- **WHEN** endpoint có tham số tên chứa `currency` hoặc response chứa trường tiền tệ
- **THEN** `has_currency` được đặt `true` với nhãn `inferred` và xuất hiện trong checklist để người dùng xác nhận

#### Scenario: Cờ không suy được phải hỏi
- **WHEN** module chưa có câu trả lời cho `has_unique_field`
- **THEN** checklist chứa câu hỏi CRITICAL tương ứng và stage lock từ chối tiến hành khi câu này còn PENDING

### Requirement: Exit code phân loại cho ingest

`utd ingest` SHALL thoát với `0` khi thành công, `2` khi đầu vào không hợp lệ về cấu trúc, và `3` khi đầu vào hợp lệ nhưng thiếu thông tin không thể suy ra. Mọi mã khác MUST NOT được dùng cho lỗi đầu vào.

#### Scenario: Phân biệt lỗi cấu trúc và lỗi thiếu tin
- **WHEN** file đầu vào sai cú pháp YAML
- **THEN** exit code là 2 và thông báo nêu vị trí dòng lỗi

#### Scenario: Thiếu thông tin nhưng cấu trúc đúng
- **WHEN** file đọc được nhưng endpoint không có `auth` và không có `params`
- **THEN** exit code là 3 và thông báo liệt kê các trường buộc phải bổ sung
