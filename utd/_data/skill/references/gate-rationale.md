# Chín cổng kiểm toán — vì sao có và chặn gì

Cổng chạy ở `utd audit`; `utd emit` từ chối xuất bản nếu bất kỳ cổng nào FAIL.
Mỗi cổng trả lời một câu hỏi khác nhau. Không cổng nào thay được cổng khác.

---

## G1 — EP (Equivalence Partitioning)

**Câu hỏi:** Tham số bắt buộc đã có test case kiểm thử trường hợp thiếu/null chưa?

**Chặn gì:** Endpoint khai `required: true` nhưng bộ test không có case nào bỏ hẳn
hoặc truyền `null` cho tham số đó. Đây là lỗi phổ biến nhất khi viết test: chỉ test
happy path.

**Cách kiểm:** mỗi param `required` phải có ít nhất một case `type: "Abnormal"` mà
chuỗi `input` không chứa `name=` hoặc chứa `name=null`, hoặc `note` ghi `missing`/`null`.

**Sửa:** thêm case Abnormal bỏ hẳn tham số.

---

## G2 — BVA (Boundary Value Analysis)

**Câu hỏi:** Tham số có biên đã được kiểm ở `min-1` và `max+1` chưa?

**Chặn gì:** khai `constraints: {min: 1, max: 100}` nhưng không test `0` và `101`.
Lỗi off-by-one sống chính ở hai điểm này.

**Cách kiểm:** tìm `name=min-1` và `name=max+1` trong `input` của mọi case.

**Sửa:** thêm hai case biên. Không có `min`/`max` thì cổng bỏ qua tham số đó —
không sinh yêu cầu vô nghĩa.

---

## G3 — DUAL-PATH

**Câu hỏi:** Mỗi business rule đã được kiểm ở *cả hai* chiều chưa?

**Chặn gì:** rule `BR-04` chỉ có case hợp lệ mà không có case vi phạm (hoặc ngược
lại). Rule một chiều là rule chưa thực sự được kiểm — không biết code có chặn khi
vi phạm hay không.

**Cách kiểm:** với mỗi `rule.id` trong `api.rules`, phải có ≥1 case
`Normal|Boundary` và ≥1 case `Abnormal` cùng tham chiếu nó trong `rule_refs`.

**Sửa:** bổ sung chiều còn thiếu. Đây là cổng bản cũ đã có nhưng hay bị lách bằng
cách gắn `rule_refs` bừa.

---

## G4 — HTTP-STATUS

**Câu hỏi:** Mỗi mã HTTP khai báo trong `responses` đã có test case kiểm chứng chưa?

**Chặn gì:** đặc tả khai `404`, `409`, `403` nhưng bộ test chỉ kiểm `200` và `400`.
Mã lỗi khai mà không test là mã lỗi chưa được cam kết.

**Cách kiểm:** regex `HTTP\s*/?\s*<status>\b` trong `expected` của ít nhất một case.

**Sửa:** thêm case cho từng mã. Nếu đặc tả khai mã mà không nêu điều kiện kích
hoạt, `budget` ghi vào `notes` thay vì sinh case giả — case giả có Expected Results
sai còn tệ hơn không có case.

---

## G5 — ANTI-SLOP (danh sách đen)

**Câu hỏi:** Dữ liệu test có chứa chuỗi mẫu vô nghĩa không?

**Chặn gì:** `John Doe`, `test@example.com`, `123 Main St`, `1111111111`.
Đây là danh sách hẹp, cố tình giữ để tương thích với bộ công cụ cũ.

**Sửa:** thay bằng dữ liệu từ `data/realistic.json`.

---

## G6 — SECURITY

**Câu hỏi:** Endpoint yêu cầu auth đã có case 401 chưa?

**Chặn gì:** endpoint `auth.type: jwt` mà không test thiếu/hết hạn token. Đây là
lỗ hổng bảo mật hay bị bỏ qua nhất trong unit test.

**Cách kiểm:** `expected` chứa `401` hoặc `note` chứa `unauthorized`/`token`.

**Sửa:** thêm case thiếu Authorization.

---

## G7 — SOURCE-RULE-COVERAGE

**Câu hỏi:** Toàn bộ kho rule nguồn đã được đánh giá chưa?

**Chặn gì:** rule nằm trong `rules/*.json` mà không matched endpoint nào và cũng
không có `skipped_reason`. Đây là cổng quan trọng nhất — nó bắt đúng lỗi của bản cũ.

**Vì sao cần:** bản cũ kiểm `uncovered_rules == []` chỉ trên các rule **đã sinh ra**.
Nếu 67 rule không bao giờ được sinh (vì bộ lọc bỏ qua chúng), `uncovered_rules` vẫn
rỗng và cổng PASS. G7 đối chiếu với **150 rule nguồn**, nên rule chết bị phát hiện.

**Cách kiểm:** `matched + skipped_có_lý_do == total_rules`. Rule `trigger: "true"`
không bao giờ được phép skip.

**Sửa:** hoặc bổ sung endpoint phù hợp, hoặc khai lý do bỏ qua rõ ràng.

---

## G8 — EP-PROPER

**Câu hỏi:** Case thể hiện "thiếu tham số" có đúng `type: Abnormal` không?

**Chặn gì:** case `Normal` viết sai định dạng Input (tình cờ thiếu tên param) được
G1 tính là "đã phủ". Đây là lỗ hổng thật của bản cũ: `verify_ep` quét mọi test case
bất kể `type`.

**Cách kiểm:** duyệt case **không phải** `Abnormal`; nếu `input` thiếu tên param
required, hoặc `note` ghi `missing`/`thiếu`, thì FAIL.

**Sửa:** đổi `type` thành `Abnormal`, hoặc sửa Input cho đúng.

---

## G9 — NO-SLOP-PROPERTY

**Câu hỏi:** Giá trị test có vi phạm thuộc tính dữ liệu giả không?

**Chặn gì:** những thứ G5 bỏ sót vì blacklist chỉ có 5 chuỗi:

| Thuộc tính | Ví dụ |
|---|---|
| định danh giả dạng `P001` | `productId=P001` |
| định danh giả gán cho tham số id | `orderId=1`, `userId=001` |
| ký tự đơn lặp ≥6 lần | `phone=1111111111` |
| placeholder chưa thay | `field=<quantity>` |
| chuỗi placeholder | `abc`, `foo`, `test1` |

**Vì sao cần:** bản cũ sinh fixture cứng `productId=P001`, `orderId=1` rồi gate
tự PASS chính sản phẩm của mình. G9 và `matrix` phải sửa cùng lúc — bản này sửa
`matrix` để lấy dữ liệu thật, giữ G9 chặt.

**Sửa:** thay bằng giá trị thật. Không nới cổng để lọt.

---

## Thứ tự chặn

```
G7  rule chết          -> audit FAIL, không sinh test case
G1  thiếu case null    -> emit bị chặn
G8  sai type           -> emit bị chặn (bắt trước G1 mới đúng)
G2  thiếu biên         -> emit bị chặn
G3  rule một chiều     -> emit bị chặn
G4  mã HTTP chưa test  -> emit bị chặn
G6  thiếu case 401     -> emit bị chặn
G5  slop blacklist     -> emit bị chặn
G9  slop property      -> emit bị chặn
```

`utd emit` kiểm thêm: `audit/report.json` tồn tại VÀ `passed: true` VÀ sha256 của
SSOT khớp giá trị đã audit. SSOT sửa tay sau audit → exit 5.
