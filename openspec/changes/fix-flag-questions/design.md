# Design

## Context

Xem `proposal.md` — Why. Phần dưới chỉ ghi hiện trạng kỹ thuật đã đo và các ràng buộc chi phối cách sửa.

Hiện trạng của `unit-test-designer` (sau change `rebuild-unit-test-designer-v2`):

- `utd/match/engine.py:403` sinh `nonce` mới ở mọi lần dựng câu hỏi: `nonce=_make_nonce()`.
- `utd/interview/apply.py:94-95` từ chối khi `nonce` trong answers khác checklist.
- `utd/interview/signature.py` ký `sha256(id|value|nonce|salt)` — nên đổi nonce là vô hiệu chữ ký.
- `utd/match/engine.py` chỉ **đọc** `flags` qua `build_context()`; không có chỗ nào gọi `flags.set(...)` ngoài `utd/ingest/flags.py:58-60` (3 cờ inferred).
- `utd/lock.py:62-135` đọc `spec.json` rồi ghi `locked_spec.json`; **không đọc checklist**, nên flags trong checklist (nếu có) không bao giờ tới được `generate`.
- `utd/lock.py` không kiểm `checklist_sha256`; nó chỉ kiểm `verified.json` tồn tại và `verified: true`.
- `utd/match/engine.py:_skip_reason()` sinh câu dựa trên `trigger_condition` + `checked` — không phân biệt "cờ chưa xác nhận" với "điều kiện nghiệp vụ không thoả".

Đo trên `assets/example_api_spec.json`:

```
flags sources (2 module)  : has_quota/has_dependencies/has_unique_field = "default"
rules phụ thuộc 3 cờ đó   : 5  (H-STATE-STOCK-QUOTA-01, H-CONC-RACE-01,
                               H-DIST-CIRCUIT-BREAKER-01, H-DIST-TIMEOUT-FALLBACK-01,
                               H-STATE-UNIQUE-01)
set 3 cờ = true           : matched 92 -> 97, skipped 58 -> 53, questions 86 -> 92
```

`question_id` hiện tại = `sheet_name + "_" + rule_id + "_" + param_name` — tất định từ dữ liệu, không phụ thuộc thời điểm. Đây là nền để merge theo id.

## Goals / Non-Goals

**Goals:**

- Sáu câu cờ/module, tier CRITICAL, nằm trong checklist và đi qua đúng đường ký như mọi câu khác.
- Trả lời cờ cập nhật `flags` và làm rule mới áp dụng **mà không mất câu trả lời đã có**.
- `lock` không thể khoá khi còn cờ chưa xác nhận, và cờ đã xác nhận phải tới được `generate`.
- `skipped_reason` không còn che giấu việc cờ chưa được hỏi.

**Non-Goals:**

- Không sửa artifact của `rebuild-unit-test-designer-v2` (giữ làm lịch sử).
- Không hỏi cờ ở cấp endpoint; cờ là thuộc tính module.
- Không tự động suy thêm cờ mới ngoài 6 cờ đã định nghĩa.
- Không đổi cơ chế chữ ký, không đổi shape `answers.json`.
- Không xử lý trường hợp nhiều người dùng cùng lúc trên một checklist.

## Decisions

### D1. Câu cờ là mục checklist bình thường, không phải kênh phụ

**Chọn:** sinh `Question` với `rule_id = "FLAG:<name>"`, `tier = CRITICAL`, `target = "flag:<name>"`, `nonce` như mọi câu khác, id = `<sheet_name>_FLAG_<name>`.

**Vì:** đi qua đúng đường ký hiện có; không cần cơ chế xác nhận thứ hai; `verify` và `lock` đã coi mọi mục CRITICAL như nhau nên không phải sửa logic tier.

**Loại bỏ:**
- *Block `flags` riêng trong checklist với nonce riêng* — tạo kênh thứ hai phải ký, tăng bề mặt lỗi.
- *Dùng `apply_batch_consent` cho cờ* — vi phạm chính lý do tồn tại của cờ: người dùng phải chủ động xác nhận.

### D2. Sinh lại kiểu append-merge, không rebuild

**Chọn:** `reconcile_checklist(old, new)` merge theo `id`: mục có trong `old` được giữ **nguyên đối tượng** (kể cả `nonce`, `status`, `answer`, `answered_by`, `evidence`); mục chỉ có trong `new` được thêm vào cuối; mục chỉ có trong `old` được chuyển sang `removed_questions` (không xoá, để `apply` nhận diện).

**Vì:** nonce là đầu vào của chữ ký. Rebuild = mọi chữ ký cũ vô hiệu = người dùng phải ký lại 86 câu. Append-merge giữ đúng bất biến "extraordinary claims cần chữ ký mới, câu cũ không cần".

**Loại bỏ:**
- *Giữ nonce cũ khi id không đổi (biến thể C1)* — tương đương về kết quả nhưng khó giải thích: "nonce ngẫu nhiên nhưng cố định" là mâu thuẫn từ ngữ. Append-merge nói đúng bản chất: câu cũ không bị đụng tới.
- *Rebuild + xuất lại HTML (C2)* — người dùng phải ký lại toàn bộ, không chấp nhận được với 86 câu.

### D3. `removed_questions` là bản ghi, không phải thùng rác

**Chọn:** checklist giữ `removed_questions: [{id, rule_id, removed_reason}]`. `apply` bỏ qua mục answers có id nằm trong danh sách này **và** `answers.json.checklist_sha256` khớp `checklist.previous_sha256`.

**Vì:** cần phân biệt hai trường hợp có cùng triệu chứng "id không có trong checklist":
1. Hợp lệ: cờ đổi làm rule biến mất → phải bỏ qua.
2. Tấn công: ai đó thêm id rác → phải từ chối.

Dùng sha của checklist làm bằng chứng: nếu answers được ký trên checklist trước khi sinh lại, sha trong đó là bằng chứng hợp lệ.

**Loại bỏ:**
- *Bỏ qua mọi id lạ* — mở đường cho chèn câu trả lời không tồn tại.
- *Từ chối mọi id lạ* — chặn nhầm kịch bản hợp lệ của chính C3.

### D4. `lock` đọc checklist làm nguồn cờ

**Chọn:** trong `lock_spec`, sau khi qua các điều kiện, đọc `checklist.modules[]`, map theo `id`, ghi `flags` (cả `values` và `sources`) vào module tương ứng của `locked_spec`. Module không có trong checklist giữ nguyên flags từ `spec.json`.

**Vì:** checklist là bản ghi phỏng vấn; `spec.json` là đầu ra của ingest, có trước khi ai trả lời. Nếu `lock` chỉ copy `spec.json`, cờ đã xác nhận không bao giờ tới `generate` — đúng lỗi verify-change chỉ ra nhưng chưa nêu hệ quả.

**Loại bỏ:**
- *`apply` ghi thẳng vào `spec.json`* — phá bất biến "spec.json là output của ingest, không bị sửa sau đó", và làm `lock` không còn là điểm hợp nhất duy nhất.
- *`generate` đọc thêm checklist* — thêm một nguồn nữa cho `generate`, phá nguyên tắc "generate chỉ đọc locked_spec".

### D5. `skipped_reason` phân biệt hai loại nguyên nhân

**Chọn:** trước khi gọi `_skip_reason`, kiểm `trigger_condition` có tham chiếu cờ nào còn `source == "default"`. Nếu có, lý do = `"cờ <name> chưa được xác nhận — cần trả lời câu FLAG:<name>"`. Ngược lại giữ lý do hiện tại.

**Vì:** đây chính là chỗ lỗi CRITICAL ẩn nấp. Câu "điều kiện không thoả" đúng về hình thức nhưng che giấu nguyên nhân thật.

**Loại bỏ:**
- *Chỉ thêm hậu tố vào lý do cũ* — vẫn còn câu gây hiểu nhầm phía trước.
- *Đánh dấu cả rule trong `skipped_rules` bằng cờ `blocked_by_flag`* — thêm field cho một thông tin đã diễn đạt được bằng `skipped_reason`.

### D6. `lock` kiểm `checklist_sha256`

**Chọn:** `lock` tính sha của checklist hiện tại (cùng hàm `sha256_text(json.dumps(sort_keys=True))` mà `verify_file` dùng) và so với `verified.json.checklist_sha256`. Lệch → exit 1, nêu cả hai giá trị.

**Vì:** nếu không, ai đó sửa checklist sau `verify` (ví dụ bật cờ bằng tay, sửa `answered_by`) là qua được cổng. Đây là khe hở mới mà D4 mở ra nếu không đóng.

**Loại bỏ:**
- *Bỏ điều kiện này, tin `verified: true`* — `verified.json` chỉ nói "tại thời điểm verify, nó sạch", không nói "bây giờ nó sạch".
- *Hash nội dung checklist trừ `previous_sha256`* — không cần; `previous_sha256` chỉ ghi khi sinh lại, và lúc đó `verify` phải chạy lại (đã là yêu cầu ngầm của luồng).

### D7. Cảnh báo re-run ở `inventory`

**Chọn:** `utd inventory` so checklist cũ (nếu có) với mới: nếu có mục mới thêm **và** checklist cũ đã có mục `ANSWERED`, in cảnh báo kèm số câu mới.

**Vì:** nếu không nhắc, người dùng mở lại HTML cũ và không thấy câu mới — họ sẽ tưởng đã xong và đi tiếp, đúng loại bỏ sót khó phát hiện.

**Loại bỏ:**
- *Tự động xuất lại HTML* — `inventory` không nên ghi ra file giao diện khi người dùng chưa yêu cầu; và tên file có thể khác nhau giữa các lần.

## Risks / Trade-offs

- **[Checklist phình dần qua nhiều lần sinh lại]** `removed_questions` và câu cũ không bị xoá → file lớn dần. Mitigation: chỉ giữ `removed_questions` của lần sinh gần nhất, kèm `previous_sha256`; nếu chuỗi sinh lại nhiều lần, id trùng sẽ được thay thế chứ không nhân bản.
- **[Lenient rule bị lạm dụng]** Kẻ tấn công có thể sửa `checklist_sha256` trong `answers.json` để khớp. Mitigation: chấp nhận — sha không phải chữ ký số của checklist, chỉ là dấu hiệu; công cụ này chạy nội bộ, không phải mặt trận công khai. Ghi rõ trong `SCHEMA.md`.
- **[Cờ inferred bị sửa ngược làm mất câu]** `has_currency` true→false làm `H-FIN-EXCHANGE-DRIFT-01` biến mất. Mitigation: `removed_questions` ghi rõ `removed_reason: "cờ has_currency chuyển sang false"`, và `inventory` in cảnh báo.
- **[Lock chặt hơn có thể chặn luồng cũ]** Checklist snapshot từ trước change này không có câu `FLAG_*` → `lock` chặn. Mitigation: đúng ý định — đó là checklist chưa hỏi cờ. Ghi trong `SCHEMA.md`.
- **[Sha checklist tính trên toàn bộ JSON]** Mọi thay đổi nhỏ (thứ tự key, thêm field) đều đổi sha. Mitigation: dùng đúng `sort_keys=True` như `verify_file`, và `apply` phải ghi checklist qua cùng code path để sha ổn định.

## Migration Plan

1. Thêm sinh câu `FLAG_*` + merge append-merge; chạy test trên fixture để xác nhận 6 câu/module.
2. Thêm đường ghi flags ở `apply`; kiểm rule mới xuất hiện sau khi trả lời cờ.
3. Siết `lock` ba điều kiện (sha, default-flag, copy flags).
4. Sửa `_skip_reason`; xác nhận 5 rule đổi lý do từ "không thoả" sang "chưa xác nhận".
5. Thêm cảnh báo re-run ở `inventory`.
6. Chạy lại e2e trên `example_api_spec.json`: kỳ vọng 92→97 matched, 86→92 questions.

Rollback: revert các file đã sửa; không có migration dữ liệu (checklist cũ vẫn đọc được, chỉ bị `lock` chặn).

## Open Questions

Không có. Ba quyết định phương án (1 = hỏi xác nhận cho cả 6 cờ, C = sinh lại khi apply, C3 = append-merge) đã chốt trước khi mở change này.
