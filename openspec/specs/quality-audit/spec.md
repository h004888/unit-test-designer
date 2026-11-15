# quality-audit Specification

## Purpose
Là cổng máy kiểm duy nhất quyết định bộ test case có đủ tiêu chuẩn kỹ thuật để xuất bản hay không, với kết quả phân loại được thay cho việc tin vào lời tuyên bố trong tài liệu hướng dẫn.

## Requirements

### Requirement: Chín cổng kiểm toán độc lập

Hệ thống SHALL chạy chín cổng trên toàn bộ SSOT: `G1 EP`, `G2 BVA`, `G3 DUAL-PATH`, `G4 HTTP-STATUS`, `G5 ANTI-SLOP`, `G6 SECURITY`, `G7 SOURCE-RULE-COVERAGE`, `G8 EP-PROPER`, `G9 NO-SLOP-PROPERTY`. Mỗi cổng MUST báo cáo độc lập, kèm danh sách vi phạm nêu rõ module, endpoint, và test case liên quan.

#### Scenario: Toàn bộ cổng đạt
- **WHEN** `utd audit --strict` chạy trên SSOT đạt cả chín cổng
- **THEN** lệnh thoát 0 và ghi `audit/report.json` với `passed: true` và `issues: []`

#### Scenario: Vi phạm ở một cổng
- **WHEN** cổng G3 phát hiện rule `BR-04` chưa có test case vi phạm
- **THEN** báo cáo có một mục `gate: "G3"` nêu module, endpoint, và `BR-04`, và lệnh thoát 1

### Requirement: Phủ rule nguồn, không chỉ rule đã sinh

Cổng `G7` SHALL đối chiếu toàn bộ rule trong kho `rules/*.json` với báo cáo reachability, và PASS chỉ khi mỗi rule nguồn hoặc đã áp dụng cho ít nhất một endpoint, hoặc có `skipped_reason` không rỗng. Nó MUST NOT chỉ kiểm tra các rule đã xuất hiện trong spec.

#### Scenario: Rule chết bị phát hiện
- **WHEN** 51 rule không áp dụng cho bất kỳ endpoint nào và không có `skipped_reason`
- **THEN** G7 FAIL và liệt kê đủ 51 rule id

#### Scenario: Rule bỏ qua có lý do hợp lệ
- **WHEN** rule cần path webhook và spec không có webhook, `skipped_reason` được ghi
- **THEN** G7 PASS cho rule đó và báo cáo ghi tổng áp dụng + bỏ qua có lý do bằng tổng số rule

### Requirement: Cổng EP phải phân biệt loại test case

Cổng `G8` SHALL coi một tham số required là đã được kiểm thử thiếu/null chỉ khi tồn tại test case có `type: "Abnormal"` thể hiện rõ điều đó. Nó MUST NOT chấp nhận một test case `Normal` chỉ vì chuỗi Input tình cờ không chứa tên tham số.

#### Scenario: Case Normal không đủ điều kiện
- **WHEN** test case duy nhất thiếu `id` là một case `Normal` viết sai định dạng Input
- **THEN** G8 FAIL và nêu tham số `id` chưa có case Abnormal

#### Scenario: Case Abnormal hợp lệ
- **WHEN** có test case `type: "Abnormal"` với Input cố ý bỏ `id` và Note ghi `missing required`
- **THEN** G8 PASS cho tham số đó

### Requirement: Chống slop theo thuộc tính, không theo danh sách đen

Cổng `G9` SHALL phát hiện dữ liệu giả tạo bằng quy tắc thuộc tính: giá trị lặp ký tự đơn điệu, chuỗi mẫu phổ biến, định danh tăng dần đơn giản như `P001`/`id=1`, và giá trị không phù hợp định dạng đã khai. Nó MUST NOT chỉ dựa vào danh sách năm chuỗi cấm.

#### Scenario: Định danh giả bị phát hiện
- **WHEN** Input chứa `productId=P001` hoặc `orderId=1` trong khi tham số khai kiểu uuid
- **THEN** G9 FAIL và nêu test case id cùng giá trị vi phạm

#### Scenario: Dữ liệu thật không bị chặn nhầm
- **WHEN** Input chứa họ tên tiếng Việt có dấu lấy từ kho thực tế
- **THEN** G9 PASS và không báo vi phạm

### Requirement: Exit code phân loại cho audit và emit

`utd audit` SHALL thoát 0 khi pass và 1 khi có vi phạm. `utd emit` MUST từ chối chạy nếu chưa có `audit/report.json` với `passed: true`, và MUST từ chối nếu sha256 của SSOT khác giá trị đã audit.

#### Scenario: Emit bị chặn khi audit chưa chạy
- **WHEN** `utd emit --xlsx` chạy mà không có `audit/report.json`
- **THEN** lệnh thoát 1 và ghi rõ cần chạy `utd audit` trước

#### Scenario: Emit bị chặn khi SSOT đổi sau audit
- **WHEN** `unit_test_spec.json` bị sửa tay sau khi audit pass
- **THEN** `utd emit` thoát 5 và nêu sha256 mong đợi so với sha256 thực tế

### Requirement: Báo cáo audit đọc được bởi người và máy

Hệ thống SHALL ghi cả `audit/report.json` cho máy đọc và `audit/report.md` cho người đọc. Bản Markdown MUST nhóm vi phạm theo cổng và nêu hành động cần làm cho từng mục.

#### Scenario: Báo cáo có cả hai định dạng
- **WHEN** `utd audit` chạy xong
- **THEN** cả hai file tồn tại và nội dung vi phạm khớp nhau về số lượng và id

#### Scenario: Báo cáo nêu hành động
- **WHEN** có vi phạm `G3: BR-04 chưa có case vi phạm`
- **THEN** bản Markdown ghi rõ cần thêm test case `Abnormal` tham chiếu `BR-04`
