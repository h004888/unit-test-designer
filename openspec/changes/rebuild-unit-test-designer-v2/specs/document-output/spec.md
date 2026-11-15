# Spec Delta

## Purpose

Xuất bản bộ tài liệu Unit Test từ một nguồn sự thật duy nhất, giữ nguyên bố cục báo cáo mà tổ chức đang dùng, và ghi lại trạng thái từng bước bằng chuỗi hash để bất kỳ ai cũng kiểm tra được tài liệu có khớp đặc tả đã chốt hay không.

## ADDED Requirements

### Requirement: Ba định dạng xuất từ một nguồn

Hệ thống SHALL sinh từ `canonical/unit_test_spec.json`: một file `.xlsx` tổng thể, một file `.md` cho mỗi module, và một `index.md` tổng hợp. Không định dạng nào được sinh trực tiếp từ nguồn khác.

#### Scenario: Sinh đồng bộ ba đầu ra
- **WHEN** `utd emit --xlsx .unittest-design/unit_test.xlsx --md-dir .unittest-design/docs` chạy trên SSOT có 2 module
- **THEN** file `.xlsx` có sheet `Cover`, `Test Cases`, `Test Statistics` và 2 sheet module; `docs/` có 2 file module cùng `index.md`

#### Scenario: Sửa SSOT rồi xuất lại
- **WHEN** người dùng sửa một test case trong SSOT và chạy lại emit
- **THEN** cả `.xlsx` và `.md` phản ánh nội dung mới, không file nào còn dữ liệu cũ

### Requirement: Giữ nguyên bố cục báo cáo đang dùng

File `.xlsx` SHALL giữ đúng bố cục trong `references/layout-xlsx.md`: thứ tự sheet, 16 cột bảng chi tiết, tiêu đề và màu nền, công thức thống kê, dropdown kết quả, và ẩn cột nguồn dropdown. Hệ thống MUST NOT kế thừa các lỗi đã ghi nhận của file mẫu gốc.

#### Scenario: Bảng chi tiết đủ 16 cột
- **WHEN** mở sheet module trong file xuất
- **THEN** header hàng 11 có đúng 16 cột từ `Test Case ID` tới `Note` theo thứ tự đã quy định

#### Scenario: Công thức thống kê an toàn chia cho 0
- **WHEN** một module có 0 test case
- **THEN** ô phần trăm hiển thị 0 chứ không hiển thị lỗi chia cho 0

#### Scenario: Dropdown có đủ bốn kết quả
- **WHEN** mở dropdown ở cột Round 1
- **THEN** danh sách gồm `Passed`, `Failed`, `Pending`, `N/A`

### Requirement: Markdown khớp nội dung Excel

Mỗi file `.md` module SHALL chứa: tiêu đề và thông tin chung, bảng đặc tả API khi có block `api`, bảng Summary, bảng chi tiết test case đúng 16 cột, và ma trận truy vết rule khi có `rules`. Nội dung MUST khớp với sheet module tương ứng trong `.xlsx`.

#### Scenario: Ma trận truy vết
- **WHEN** module có 5 rule và mỗi rule có ít nhất một test case
- **THEN** file `.md` có mục Traceability Matrix liệt kê đủ 5 rule kèm mã test case tương ứng

#### Scenario: Rule chưa có test case
- **WHEN** một rule không có test case tham chiếu
- **THEN** ma trận đánh dấu rule đó là còn thiếu, không bỏ khỏi bảng

### Requirement: Trạng thái từng bước có chuỗi hash

Hệ thống SHALL ghi `.unittest-design/run.json` chứa: stage hiện tại, đường dẫn từng artifact, sha256 của từng artifact, kết quả từng cổng, và thời điểm. Mọi stage MUST cập nhật file này sau khi ghi artifact.

#### Scenario: Ghi nhận sau mỗi stage
- **WHEN** `utd inventory` chạy xong
- **THEN** `run.json` có `stage: "inventory"` và sha256 của `interview/checklist.json`

#### Scenario: Phát hiện lệch hash
- **WHEN** một artifact bị sửa ngoài luồng
- **THEN** stage kế tiếp phát hiện sha256 khác giá trị trong `run.json`, thoát 5, và nêu tên file

### Requirement: Ghi file an toàn và mã hoá nhất quán

Hệ thống SHALL ghi mọi artifact bằng cách ghi file tạm rồi thay thế nguyên tử, dùng UTF-8 không BOM. Nó MUST cấu hình stdout về UTF-8 ngay khi khởi động để không gặp lỗi mã hoá trên console Windows.

#### Scenario: Không để lại file dở
- **WHEN** quá trình ghi bị ngắt giữa chừng
- **THEN** không tồn tại file đích ở trạng thái nửa vời, chỉ còn file tạm hoặc file cũ nguyên vẹn

#### Scenario: Tiếng Việt trên console mặc định
- **WHEN** chạy `utd` trên Windows với code page 437
- **THEN** lệnh in đúng tiếng Việt có dấu cho `get --category name` mà không ném `UnicodeEncodeError`

### Requirement: Tài liệu đối chiếu khi mở mã nguồn

Khi người dùng yêu cầu ở stage reconcile, hệ thống SHALL sinh `reconcile/gap_report.md` phân loại từng rule và test case theo bốn nhóm: `Match`, `Mismatch`, `Missing in code`, `Extra in code`. Việc mở mã nguồn MUST chỉ xảy ra ở stage này.

#### Scenario: Phân loại đủ bốn nhóm
- **WHEN** `utd reconcile` chạy trên dự án có 10 rule
- **THEN** báo cáo gán mỗi rule vào đúng một trong bốn nhóm và cộng lại bằng 10

#### Scenario: Không mở mã nguồn trước reconcile
- **WHEN** bất kỳ stage nào từ ingest tới emit chạy
- **THEN** không file mã nguồn nào của dự án bị đọc, và `run.json` ghi nhận không có truy cập mã nguồn
