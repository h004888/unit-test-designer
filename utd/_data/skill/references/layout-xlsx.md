# Cấu trúc template Unit Test Document

Tài liệu được phân tích từ file mẫu `Report-5.1_Unit_Test.xls`. Script `scripts/build_unit_test_doc.py` tái tạo cấu trúc này. Font toàn file: **Tahoma 10** (tiêu đề sheet cỡ 20 đậm).

Thứ tự sheet trong file `.xlsx` tổng thể của dự án: `Cover` → `Test Cases` → `Test Statistics` → **các sheet API/hàm (mỗi API là 1 sheet riêng biệt, được cộng dồn qua từng đợt từ file spec JSON gốc của dự án)**.

## 1. Cover
| Vùng | Nội dung |
|---|---|
| B2:F2 (merge) | Tiêu đề `UNIT TEST DOCUMENT` |
| A4/B4:D4 | Project Name / giá trị |
| E4/F4 | Creator / giá trị |
| A5/B5:D5 | Project Code / giá trị |
| E5/F5 | Issue Date / giá trị |
| A6/B6:D6 | Document Code = `=B5&"_UnitTest_"&F6` |
| E6/F6 | Version / giá trị |
| A9 | `Record of change` |
| Hàng 10 (nền navy 000080, chữ trắng) | Effective Date, Version, Change Item, `*A,D,M`, Change description, Reference |
| Hàng 11+ | Các dòng lịch sử thay đổi (A = Add, D = Delete, M = Modify) |

## 2. Test Cases (danh sách module)
- D1: tiêu đề `TEST CASE LIST`.
- B3:C3 `Project Name` → D3:F3 `=Cover!B4`; B4:C4 `Project Code` → D4:F4 `=Cover!B5` (chữ xanh lá = lấy từ sheet khác).
- B5:C5 `Test Environment Setup Description` → D5:F5 mô tả môi trường (nhiều dòng).
- Hàng 8 (nền indigo 333399): `No | Module Name | Sheet Name | Description | Pre-Condition` (cột B-F).
- Hàng 9+: mỗi module một dòng; Sheet Name là hyperlink nội bộ tới sheet module.

## 3. Test Statistics
- A2:I2: tiêu đề `UNIT TEST STATISTICS`.
- Hàng 4-6: Project Name (`=Cover!B4`), Creator (`=Cover!F4`), Project Code (`=Cover!B5`), Reviewer/Approver, Document Code (`=B5&"_Test Report_"&Cover!F6`), Issue Date (`=Cover!F5`).
- Hàng 7: Notes (liệt kê các module trong đợt release).
- Hàng 11 (nền navy): `No | Function code | Passed | Failed | Untested | N | A | B | Total Test Cases`. N/A/B = Normal/Abnormal/Boundary.
- Hàng 12+: mỗi module một dòng, lấy dữ liệu từ sheet module:
  - Passed/Failed/Untested = `'Sheet'!B7 / C7 / D7` (hàng của Round 3; đổi bằng `stats_round`)
  - N/A/B = `'Sheet'!B9 / C9 / D9`; Total = `'Sheet'!B3`
- Dòng `Sub total` = `SUM` từng cột.
- 5 chỉ số % bên dưới (tính trên dòng Sub total):
  - Test coverage = (Passed + Failed) × 100 / Total
  - Test successful coverage = Passed × 100 / Total
  - Normal / Abnormal / Boundary case = N, A, B × 100 / Total

## 4. Sheet module
**Phần Summary (hàng 2-9, cột A-D)**

| Ô | Nội dung |
|---|---|
| A2 / B2:D2 | `Code Module` / tên module |
| A3 / B3 | `Number of TCs` / `=COUNTIF(A12:A1005,"UTC*")` |
| Hàng 4 | `Testing Round`, Passed, Failed, Pending |
| Hàng 5-7 | Round 1/2/3: `=COUNTIF($F$12:$F$1003,B$4)` (Round 2 dùng cột I, Round 3 dùng cột L) |
| Hàng 8 | `Testing Type`, Normal, Abnormal, Boundary |
| Hàng 9 | `Count`: `=COUNTIF($E$12:$E$1003,B$8)` |

**Bảng chi tiết (header hàng 11, nền xanh lá 339966, 16 cột A-P)**

| Cột | Tiêu đề | Ghi chú |
|---|---|---|
| A | Test Case ID | `UTC001`... đánh số liên tục trong module |
| B | Pre-conditions | `N/A` nếu không có |
| C | Input parameters | `a=1; b=-2` |
| D | Expected Results | 3 dòng: `Return:` / `Exception:` / `Log Message:` |
| E | Type | dropdown Normal/Abnormal/Boundary |
| F, G, H | Round 1, Test date, Tester | F dropdown Passed/Failed/Pending/N/A |
| I, J, K | Round 2, Test date, Tester | J-K gom nhóm và thu gọn (ẩn) |
| L, M, N | Round 3, Test date, Tester | M-N gom nhóm và thu gọn (ẩn) |
| O | Defect IDs | |
| P | Note | tên test `TênHàm_KịchBản_KếtQuả` + kỹ thuật thiết kế |

- Hàng nhóm tên hàm: nền aqua CCFFFF, chữ đậm, trải A-P; các test case của hàm đó nằm ngay bên dưới.
- Cột T (ẩn) chứa danh sách `Passed, Failed, Pending, N/A` làm nguồn cho dropdown.

## Lỗi trong file mẫu gốc đã được sửa (không bắt chước)
1. `Test Cases!D3`, `D4` là `=#REF!` (tham chiếu hỏng) → nay trỏ `=Cover!B4`, `=Cover!B5`.
2. Danh sách dropdown kết quả chỉ có `Passed, Pending, N/A`, thiếu `Failed` → đã thêm `Failed`.
3. Công thức đếm không nhất quán (`E$10:E$1003` ở một ô, `$E12:$E1003` ở ô khác) → thống nhất `$E$12:$E$1003`.
4. Dòng module thứ hai trong Test Statistics nhập tay số liệu thay vì công thức → mọi dòng đều là công thức.
5. Công thức % không bảo vệ chia cho 0 → bọc `IF(Total=0,0,...)`.
6. Document Code là chuỗi placeholder `vx.x` cố định → ghép từ Project Code và Version thật.

---

# Output Markdown theo từng API (`--md-dir`)

Mỗi API/hàm ghi ra một file `.md` (tên `POST_api_orders.md`; không có block `api` thì `<Sheet>_<tênHàm>.md`), cộng `index.md`. Bố cục file giống tab module trong Excel:

1. **Tiêu đề + thông tin chung**: project, module, version, nguồn đặc tả.
2. **API Specification** (chỉ khi có block `api`): mô tả, auth, bảng Request parameters, bảng Responses, bảng Business rules.
3. **Summary**: Code Module, Number of TCs, bảng Testing Round (Passed/Failed/Pending cho Round 1-3, mặc định toàn bộ Pending) và bảng Testing Type (Normal/Abnormal/Boundary). Bảng Markdown không có công thức nên cập nhật Round thủ công.
4. **Test Case Details**: đúng 16 cột như sheet module, hàng nhóm in đậm tên hàm, Expected Results xuống dòng bằng `<br>`, ký tự `|`, `<`, `>` được escape.
5. **Traceability Matrix** (khi có `rules`): mỗi Rule ID kèm các TC kiểm chứng; rule chưa có TC được đánh dấu để bổ sung.

`index.md` liệt kê mọi API (liên kết tới file), số TC theo loại, tổng cộng, và danh sách rule chưa có test case nếu còn.
