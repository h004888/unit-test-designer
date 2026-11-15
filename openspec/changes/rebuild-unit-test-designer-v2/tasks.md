# Tasks

## 1. Sao lưu và dựng nền

- [x] 1.1 Zip toàn bộ `unit-test-designer/` ra ngoài workspace và xác nhận file zip mở được, liệt kê đúng 98 file — verify: `unzip -l backup.zip | wc -l` khớp danh sách
- [x] 1.2 `git init` và commit `pre-v2` cho toàn bộ `temp_test`; xác nhận `git log --oneline` có đúng 1 commit — verify: `git status` sạch sau commit
- [x] 1.3 Tạo `unit-test-designer/utd/__init__.py`, `cli.py` rỗng với 8 subcommand stub in "not implemented"; verify: `python -m utd --help` liệt kê đủ 8 lệnh và exit 0
- [x] 1.4 Viết `utd/io.py`: `reconfigure_stdout()`, `atomic_write(path, text)`, `sha256_file(path)`; verify: test ghi file tiếng Việt trên `chcp 437` không ném `UnicodeEncodeError`
- [x] 1.5 Tạo `utd/state.py` đọc/ghi `.unittest-design/run.json` với sha256 từng artifact; verify: test đọc lại đúng giá trị đã ghi và phát hiện lệch khi sửa file

## 2. Canonical IR và ingest

- [x] 2.1 Viết `utd/canonical.py`: dataclass `Project`, `Module`, `Endpoint`, `Param`, `Constraints`, `Flags` + `validate()` trả danh sách lỗi; verify: test từ chối module thiếu `sheet_name` và chấp nhận spec mẫu hợp lệ
- [x] 2.2 Port `assets/rules_domain/*.json` sang `rules/` (giữ nguyên nội dung) và chuyển bảng `realistic_user_data` + `test_payloads` sang `data/realistic.json` + `data/payloads.json` bằng script một lần; verify: đếm được đúng 150 rule, 82 bản ghi, 701 payload và test so khớp với bản gốc
- [x] 2.3 Viết `utd/ingest/rawjson.py` (adapter `utd-v1`) đọc `modules[].methods[].api` → flattened `endpoints[]`, `constraints` hóa từ chuỗi ràng buộc; verify: `utd ingest --from utd-v1 --in assets/example_api_spec.json` sinh 2 module, 2 endpoint, exit 0
- [x] 2.4 Viết `utd/ingest/openapi.py` cho OpenAPI 3.x: `paths` → endpoints, `requestBody`/`parameters` → params với `in` đúng, `minimum`/`maximum`/`pattern`/`enum` → `constraints`; verify: test trên fixture OpenAPI 3.0 tối thiểu ra đúng số endpoint và constraints
- [x] 2.5 Viết `utd/ingest/swagger.py` cho Swagger 2.0; verify: test trên fixture Swagger 2.0 ra cùng shape với adapter OpenAPI cho cùng API
- [x] 2.6 Viết `utd/ingest/draft.py` validate draft do LLM viết và ghi nhãn trường thiếu; verify: test draft thiếu `params` thoát 3 và nêu đúng tên trường
- [x] 2.7 Cài exit code 2/3 cho mọi adapter và test phân biệt; verify: test sai cú pháp → 2, thiếu thông tin → 3
- [x] 2.8 Suy 3 cờ `has_status_field`, `is_multi_tenant`, `has_currency` với nhãn `inferred`; verify: test spec có param `currency` cho `has_currency=true, source=inferred`

## 3. Thông dịch rule

- [x] 3.1 Viết `utd/dsl.py` dùng `ast.parse(mode="eval")` + whitelist node (`Compare`, `BoolOp`, `Attribute`, `Call` giới hạn `includes`, `Constant`, `In`, `NotIn`, `Name`); verify: test 54 biểu thức hiện có trong `rules/` đều parse thành công
- [x] 3.2 Thêm validator từ chối biểu thức ngoài ngôn ngữ; verify: test `__import__('os').system('x')` bị từ chối và không thực thi gì
- [x] 3.3 Đánh giá ngữ cảnh thiếu trường trả `false` + cảnh báo; verify: test `foo.bar` cho `false` kèm cảnh báo, không dừng chương trình
- [x] 3.4 Viết `utd/match/tier.py` suy `CRITICAL`/`STANDARD` từ `strictness` + nhóm trong dữ liệu, không hardcode id; verify: test rule `MANDATORY` nhóm auth cho CRITICAL, `CONDITIONAL` nhóm transport cho STANDARD
- [x] 3.5 Viết `utd/match/engine.py` sinh checklist đã khử trùng lặp theo (`rule_id`,`endpoint_id`,`param_name`) và gộp `rule_ids`; verify: test 3 rule cùng tham số cho 1 mục với 3 `rule_ids`
- [x] 3.6 Sinh nonce 16 byte mỗi mục và ghi `interview/checklist.json`; verify: test 100 mục có 100 nonce duy nhất
- [x] 3.7 Báo cáo reachability 150/150 kèm `skipped_reason`; verify: test trên spec không có webhook ghi `skipped_reason` cho rule webhook, tổng matched + skipped = 150
- [x] 3.8 Kiểm chống tái phát: `tests/test_dsl_interpreter.py` khẳng định không `target_element` nào trong `rules/` thiếu đường đánh giá; verify: test fail nếu thêm rule dùng trường lạ

## 4. Interview và khoá

- [x] 4.1 Viết `utd/interview/export.py` sinh `interview.html` tự chứa (không CDN, không fetch) hiển thị mọi câu hỏi, ghi chú, và nút xuất; verify: mở file offline trong trình duyệt hiển thị đủ câu hỏi
- [x] 4.2 Cài chữ ký `sha256(id|value|nonce|salt)` trong HTML và `utd/interview/apply.py` kiểm lại; verify: test file sửa `value` sau khi ký bị từ chối exit 4
- [x] 4.3 Thêm đường `USER_CHAT` với `evidence` bắt buộc; verify: test thiếu `--evidence` bị từ chối, có evidence ghi đúng nhãn
- [x] 4.4 Viết `utd/interview/verify.py`: 0 khi sạch, 1 khi PENDING, 4 khi CRITICAL sai nguồn; verify: ba test tương ứng
- [x] 4.5 Viết `utd lock`: chỉ tạo `canonical/locked_spec.json` + `lock.sha256` khi có `verified.json` và chữ ký `Chốt`/`OK`; verify: test thiếu sign-off exit 1 và không tạo file
- [x] 4.6 Kiểm hash trước `generate`: sửa `locked_spec.json` → exit 5 nêu tên file; verify: test tương ứng

## 5. Sinh test case

- [x] 5.1 Viết `utd/generate/budget.py` tính slot từ `constraints` cấu trúc; verify: test `min=1,max=100` sinh đủ `min-1,min,min+1,max-1,max,max+1` và 1 Normal
- [x] 5.2 Bảo đảm không có `constraints.min|max` thì không sinh BVA và ghi lý do; verify: test tương ứng
- [x] 5.3 Viết `utd/generate/matrix.py` chạy trên **mọi** `modules[]`; verify: test spec 2 module sinh test case cho cả 2, mỗi module `Normal >= 1`
- [x] 5.4 Từ chối khi module có `Normal == 0` hoặc `endpoints == []`; verify: test thoát 1 nêu tên module
- [x] 5.5 Viết `utd/generate/data.py` cấp dữ liệu từ `data/realistic.json` + biến dị lỗi con người, không sinh giá trị mẫu; verify: test Input chứa họ tên tiếng Việt có dấu, không chứa `Nguyen Van A`/`P001`
- [x] 5.6 Báo thiếu danh mục dữ liệu thay vì rơi về giá trị mẫu; verify: test yêu cầu danh mục không tồn tại thoát 1
- [x] 5.7 Gán `rule_refs` và báo `uncovered_rules`; verify: test bỏ sót `BR-05` thoát 1 và liệt kê đúng
- [x] 5.8 Cài `--add-endpoint` cộng dồn không mất đợt trước và giữ mã `UTC` ổn định; verify: test SSOT 2 module + thêm module 3 vẫn giữ nguyên 13 mã cũ
- [x] 5.9 Kiểm chống tái phát: `tests/test_all_modules.py` khẳng định generator không dừng ở `modules[0]`; verify: test fail nếu chỉ có module đầu được xử lý

## 6. Audit chín cổng

- [x] 6.1 Port G1–G6 từ `test_technique_gatekeeper.py` sang `utd/audit/gates.py`, giữ thông điệp tiếng Việt; verify: chạy trên `example_api_spec.json` cho cùng 8 vi phạm như bản cũ
- [x] 6.2 Cài G8 EP-PROPER: case thiếu tham số phải `type=Abnormal`; verify: test case Normal viết sai Input không còn được tính là đã phủ
- [x] 6.3 Cài G9 NO-SLOP-PROPERTY: phát hiện `P001`, `id=1` với tham số khai uuid, chuỗi lặp đơn điệu; verify: test bắt được 2 mẫu giả và không chặn họ tên tiếng Việt
- [x] 6.4 Cài G7 SOURCE-RULE-COVERAGE trên 150 rule nguồn; verify: test 51 rule không lý do thì G7 FAIL liệt kê đủ 51
- [x] 6.5 Ghi `audit/report.json` + `audit/report.md` nhóm theo cổng kèm hành động; verify: test số lượng vi phạm hai file khớp nhau
- [x] 6.6 Cài exit 0/1 và chặn `emit` khi thiếu `passed:true` hoặc lệch sha256; verify: hai test tương ứng (exit 1 và exit 5)

## 7. Emit tài liệu

- [x] 7.1 Viết `utd/emit/xlsx.py` theo đúng `references/layout-xlsx.md`: 4 sheet hệ thống, 16 cột, màu, công thức, dropdown 4 giá trị, cột ẩn; verify: test đọc lại `.xlsx` khớp từng ô đặc tả
- [x] 7.2 Bọc công thức phần trăm trong `IF(Total=0,0,...)`; verify: test module 0 test case cho 0% không lỗi
- [x] 7.3 Viết `utd/emit/markdown.py` sinh `.md` mỗi module + `index.md` với API spec, Summary, 16 cột, ma trận truy vết; verify: test rule thiếu case vẫn xuất hiện và được đánh dấu
- [x] 7.4 Kiểm khớp nội dung giữa `.md` và sheet tương ứng; verify: test so số test case và mã `UTC` hai đầu
- [x] 7.5 Cập nhật `run.json` sau mỗi lệnh emit; verify: test `stage`, danh sách artifact và sha256 đúng

## 8. Skill, tài liệu và dọn bản cũ

- [x] 8.1 Viết `SCHEMA.md`: Canonical IR v2, checklist, answers, audit report, run.json, exit code; verify: mọi shape trong SCHEMA khớp validator trong `canonical.py`
- [x] 8.2 Viết `references/gate-rationale.md` giải thích 9 cổng và cổng nào chặn gì; verify: đủ 9 mục G1–G9
- [x] 8.3 Chuyển `references/template-layout.md` → `references/layout-xlsx.md` giữ nguyên nội dung; verify: `diff` chỉ khác tên file
- [x] 8.4 Viết `SKILL.md` mới ≤ 120 dòng: 8 lệnh, điều kiện dừng, GATE-1, và ghi rõ ngoại lệ cấm `codebase-memory-mcp` ở S0–S6; verify: `wc -l` ≤ 120 và có đủ 8 lệnh
- [x] 8.5 Xoá `scripts/`, `tests/` cũ, `SKILL.md` cũ, `heuristic_matrix.json`, `test_knowledge.db`, `download_*.py`; verify: `find` xác nhận không còn file cũ và `git status` cho thấy chỉ còn cấu trúc mới
- [x] 8.6 Chạy toàn bộ test mới; verify: `pytest -q` 0 failed
- [x] 8.7 Chạy end-to-end trên `example_api_spec.json`: ingest → inventory → interview (giả lập) → lock → generate → audit → emit; verify: mọi stage exit 0 và sinh đủ `.xlsx` + `.md`

## 9. Kiểm chứng chống tái phát

- [x] 9.1 `tests/test_dsl_interpreter.py` — không rule nào thiếu đường đánh giá; verify: pass trên 150 rule hiện tại
- [x] 9.2 `tests/test_all_modules.py` — generator và budget xử lý mọi module; verify: pass với spec 3 module
- [x] 9.3 `tests/test_hash_chain.py` — sửa artifact ngoài luồng bị phát hiện ở stage sau; verify: exit 5
- [x] 9.4 `tests/test_gates.py` — 9 cổng, mỗi cổng có 1 case pass và 1 case fail; verify: 18 assertion đúng
- [x] 9.5 `tests/test_cli_e2e.py` — luồng đầy đủ bằng subprocess trên fixture; verify: exit 0 toàn chuỗi và artifact tồn tại

## Workflow follow-up

- Archive change sau khi review xong.
- Kiểm chứng lại kết quả đã archive.
