# Design

## Context

Xem `proposal.md` — Why. Dưới đây là hiện trạng kỹ thuật quyết định cách sửa.

Hiện trạng sau `fix-flag-questions`:

- `utd/match/engine.py:301-302` sinh khoá gộp từ `(endpoint_id, param_name, target_element)`.
- `utd/match/engine.py:376-381` đặt `question_id` từ `(sheet_name, rule["id"], param_name)` — tức từ **rule đại diện**, không từ khoá gộp.
- `utd/match/reconcile_checklist.py:63` merge theo `id`, giữ nguyên byte khi id trùng.
- `utd/lock.py:124-125` tính `checklist_digest` để so với `verified.json`.

Đo thực tế trên fixture khi bật 6 cờ:

```
id biến mất                    : 6
rule trong câu biến mất        : 7 (tất cả VẪN áp dụng)
câu mới                        : 8
câu giữ id, rule_ids tăng      : 6
```

Mô phỏng id theo khoá gộp: id biến mất 0, câu mới 8, rule_ids tăng 6.

## Goals / Non-Goals

**Goals:**

- Id câu hỏi không đổi khi cờ thay đổi, miễn nhóm còn rule.
- Không thay đổi số câu, cách gộp, hay bất kỳ cơ chế ký/merge nào.
- Cảnh báo rõ khi câu trả lời cũ bắt đầu phủ rule mới.

**Non-Goals:**

- Không đổi từ gộp theo `target_element` sang gộp theo `category` hay `rule_id`. Đo: gộp theo `rule_id` làm câu tăng từ 94 lên 203 trên fixture.
- Không đổi `answers.json`, `removed_questions`, `previous_sha256`.
- Không tự động trả lời lại cho rule mới; chỉ cảnh báo.
- Không migration checklist cũ; id cũ coi như câu mới.

## Decisions

### D1. Id từ khoá gộp, dạng `row:<sheet>:<kind>:<...>:<target>`

**Chọn:** hai hàm thuần:

```
endpoint_id(sheet, target)        -> f"row:{sheet}:endpoint:{target}"
param_id(sheet, param, target)    -> f"row:{sheet}:param:{param}:{target}"
```

**Vì:** khoá gộp là `(endpoint_id, param_name, target_element)` — id chỉ cần phản ánh ba thành phần đó, không phản ánh rule nào tình cờ đứng đầu. Tiền tố `row:` nói rõ đây là định danh nhóm, không phải định danh rule; `:endpoint:` / `:param:` phân biệt hai cấp.

**Loại bỏ:**
- *`sheet + "_" + target`* — dài dòng hơn nhưng không phân biệt được câu endpoint và câu param khi một target xuất hiện ở cả hai cấp; và dễ đụng khi tên param trùng tên target.
- *Giữ id cũ, thêm thuộc tính `group_key` riêng để merge* — merge theo `id` là bất biến của `reconcile_checklist`; thêm khoá thứ hai đòi hỏi sửa toàn bộ đường merge và `removed_questions`, rủi ro cao hơn lợi ích.
- *Id dạng hash của khoá gộp* — ổn định nhưng không đọc được, khó debug và khó đối chiếu khi người đọc mở checklist.

### D2. Giữ nguyên cách gộp và số câu

**Chọn:** không đụng `group_key`; chỉ đổi `question_id`.

**Vì:** vấn đề là id, không phải gộp. Đổi cách gộp sẽ đổi số câu (đo: 94 → 203 nếu bỏ gộp) và làm loãng câu hỏi — mỗi rule một câu thì người dùng phải trả lời 203 lần cho cùng một chủ đề đạo đức như `all_endpoints` với 22 category khác nhau.

**Loại bỏ:**
- *Gộp theo `category`* — đã thử ở change trước, `all_endpoints` có 22 category nên không giảm được gì; và category do người viết rule đặt, không ổn định.
- *Không gộp* — 203 câu, trải nghiệm tệ.

### D3. Cảnh báo khi `rule_ids` của câu đã trả lời tăng

**Chọn:** trong `utd inventory` và trong `_regenerate_after_flags`, so `rule_ids` cũ/mới của mọi câu; nếu câu đã `ANSWERED` và `rule_ids` mới ⊃ `rule_ids` cũ, in một dòng cho mỗi câu: id, số rule mới, danh sách rule mới, và nhắc rằng câu trả lời hiện có đang được áp dụng cho cả rule mới.

**Vì:** giữ câu trả lời (không làm mất công người dùng) nhưng không im lặng mở rộng phạm vi câu trả lời. Đây là điểm cân bằng giữa A (giữ + báo) và B (đánh dấu chưa đủ).

**Loại bỏ:**
- *Im lặng* — người dùng không biết câu trả lời của mình giờ phủ thêm rule, vi phạm tinh thần minh bạch của toàn bộ dự án.
- *Tự đánh dấu PENDING* — mất câu trả lời cũ, ngược D2 của `fix-flag-questions`.
- *Chặn lock cho tới khi trả lời lại* — quá nghiêm; người dùng có thể đồng ý với câu trả lời cũ cho rule mới.

### D4. Không migration checklist cũ

**Chọn:** checklist sinh trước change này có id dạng `..._<rule-id>`; sau change, mọi id đổi sang `row:...`. Lần `inventory` đầu tiên sau khi nâng cấp sẽ coi toàn bộ câu là **mới**, và câu cũ vào `removed_questions`.

**Vì:** migration ngược cần map id cũ sang nhóm, mà id cũ không chứa `target_element` — phải tra `rules/*.json` để suy ra. Đó là logic phức tạp chỉ dùng một lần, và có thể sai khi rule bị sửa. Người dùng chạy lại `inventory` và trả lời lại là đủ, vì công cụ đang ở giai đoạn nội bộ.

**Loại bỏ:**
- *Adapter đọc id cũ* — thêm code vĩnh viễn cho một lần chuyển đổi.
- *Giữ song song hai dạng id* — hai nguồn sự thật cho cùng một câu.

### D5. Id không phụ thuộc thứ tự rule trong file

**Chọn:** id chỉ chứa `sheet_name`, `param_name`, `target_element` — ba thứ đến từ spec và dữ liệu rule, không từ thứ tự khớp. Test khoá điều này bằng cách đảo thứ tự rule trong ruleset rồi so id.

**Vì:** nếu id còn phụ thuộc thứ tự, thêm một rule mới vào giữa file `rules/*.json` sẽ đổi id hàng loạt — đúng loại lỗi D1 đang sửa, chỉ ở tầng khác.

**Loại bỏ:** *dùng index rule trong danh sách* — rõ ràng sai, và không cần bàn.

## Risks / Trade-offs

- **[Id dài hơn]** `row:POST_api_orders:param:quantity:integer_or_number_param` dài hơn `POST_api_orders_H-DATA-NUM-01_quantity`. Mitigation: `interview.html` hiển thị id ở cỡ nhỏ; id chỉ dùng định danh, không dùng cho người đọc chính.
- **[Cột `rule_id` giữ nguyên nghĩa "đại diện"]** Câu hỏi vẫn có `rule_id` (rule đầu tiên) để báo cáo và tra cứu; nhưng giờ nó có thể đổi giữa các lần chạy. Mitigation: ghi rõ trong `SCHEMA.md` rằng `id` là định danh ổn định, `rule_id` chỉ là thông tin tham khảo.
- **[Người dùng mất câu trả lời khi nâng cấp]** D4. Mitigation: ghi trong `SCHEMA.md` mục tương thích; cảnh báo ở lần chạy đầu nếu phát hiện `removed_questions` lớn bất thường (toàn bộ checklist).
- **[Cảnh báo quá nhiều dòng]** Nếu nhiều câu cùng mở rộng. Mitigation: in tối đa 10 dòng kèm tổng số còn lại.
- **[`rule_ids` tăng nhưng câu trả lời không còn đúng]** Cảnh báo không đảm bảo người dùng đọc. Mitigation: đây là giới hạn của công cụ dòng lệnh; `verify` vẫn là cổng chặn cuối, và người dùng luôn có thể xuất lại HTML để xem.

## Migration Plan

1. Thêm `endpoint_question_id` / `param_question_id` trong module mới hoặc trong `engine.py`.
2. Đổi `_build_question` dùng hai hàm đó; giữ nguyên phần gộp.
3. Thêm so sánh `rule_ids` cũ/mới trong `utd inventory` và `_regenerate_after_flags`.
4. Cập nhật `SCHEMA.md` (dạng id, ý nghĩa `rule_id` vs `id`, tương thích ngược).
5. Chạy test cũ: kỳ vọng một số test dùng id cũ phải cập nhật. Đặc biệt `tests/test_flag_apply.py` có id cứng `POST_orders_FLAG_has_quota` (câu cờ không đổi dạng, vẫn `<sheet>_FLAG_<name>`).
6. Đo trên fixture: id biến mất 6 → 0.

Rollback: revert các file đã sửa; checklist cũ vẫn đọc được (mọi câu thành "mới").

## Open Questions

Không có. Ba quyết định — (c) đổi id theo khoá gộp, A (giữ câu trả lời + cảnh báo), A3 (dạng `row:<sheet>:endpoint|param:<...>:<target>`) — đã chốt trước khi mở change.
