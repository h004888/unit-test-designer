# Design

## Context

Xem `proposal.md` — Why để biết động cơ. Phần dưới chỉ ghi hiện trạng kỹ thuật đã đo được và các ràng buộc chi phối cách làm.

Hiện trạng đo được của `unit-test-designer`:

- `scripts/` 11 file ~4195 dòng; `tests/` 26 file ~1559 dòng; `SKILL.md` 350 dòng.
- Kho tri thức đúng: 150 rule / 10 domain trong `assets/rules_domain/*.json`; 701 payload; 82 bản ghi dữ liệu thực tế. Số liệu khớp giữa `SKILL.md` và SQLite.
- Mỗi rule mang `trigger_condition` — 54 biểu thức khác nhau trên ngôn ngữ đóng (so sánh method, kiểm tra `param.type`, `.includes(...)` trên `path`/`name`, và 6 cờ boolean). 59 rule có điều kiện `"true"`.
- `match_dynamic_context` bỏ qua `trigger_condition`, dùng if-chain phủ 37/72 `target_element`; đo trên một API "maximal" đạt 83/150 rule; 36 `target_element` không có nhánh nào → 51 rule không thể kích hoạt.
- `test_matrix_generator.py` và `test_budget_calculator.py` chỉ đọc `modules[0].methods[0]`.
- `--answered-by` mặc định `USER`; `verify_gate` chấp nhận giá trị đó.
- `print(json.dumps(..., ensure_ascii=False))` crash trên code page 437.
- 9/63 test fail vì hardcode `C:\Users\ADMIN\.gemini\config\skills\unit-test-designer`.
- Repo không có `.git`. Xoá là không khôi phục được.
- Python 3.12.9; `openpyxl` 3.1.5 đã cài; `pytest` có sẵn.

Ràng buộc:

- Ngôn ngữ artifact và giao diện: tiếng Việt. Giữ heading cấu trúc và `SHALL`/`MUST` bằng tiếng Anh.
- GATE-1 cấm đọc mã nguồn dự án từ ingest tới emit; chỉ reconcile được mở.
- Hooks/hệ thống ngoài có thể yêu cầu dùng `codebase-memory-mcp`; skill này cấm nó trong S0–S6. Xung đột này phải được ghi rõ trong `SKILL.md` để không mơ hồ.
- Không được thêm dependency nặng; `openpyxl` là dependency duy nhất ở runtime cho emit.

## Goals / Non-Goals

**Goals:**

- Reachability 150/150 rule, mỗi rule không áp dụng có lý do kiểm chứng được.
- Một CLI, một Canonical IR, exit code phân loại cho mọi stage.
- Câu trả lời phỏng vấn kiểm chứng được bằng mật mã, không bằng lời khai.
- Mọi module được xử lý; emit bị chặn nếu SSOT đã đổi sau audit.
- Chạy đúng trên Windows cp437, không cần biến môi trường.
- Bộ test mới chặn tái phát đúng ba lỗi gốc.

**Non-Goals:**

- Không viết lại bố cục Excel/Markdown; giữ nguyên đặc tả trong `references/layout-xlsx.md`.
- Không thay đổi nội dung 150 rule, 701 payload, 82 bản ghi dữ liệu.
- Không hỗ trợ song song v1 qua CLI flag cũ; chỉ đọc được dữ liệu cũ qua adapter.
- Không thêm web server, không thêm database; HTML tự chứa, dữ liệu là JSON.
- Không tự động sửa mã nguồn dự án ở stage reconcile; chỉ báo cáo.

## Decisions

### D1. Thông dịch `trigger_condition` thay vì if-chain

**Chọn:** `utd/dsl.py` ~60 dòng, dùng `ast.parse(mode="eval")` + whitelist node, đánh giá trên ngữ cảnh `{endpoint, param, flags}`.

**Vì:** 54 biểu thức là ngôn ngữ đóng; đánh giá trực tiếp đạt 100% reachability và thêm rule chỉ cần thêm JSON. Cognitive complexity từ 40 xuống dưới 10.

**Loại bỏ:**
- *Viết 72 matcher function* — vẫn là luật trong code, mỗi rule mới phải sửa Python; đúng lỗi cũ ở quy mô lớn hơn.
- *`eval()` thô* — file rule là dữ liệu người dùng sửa được, `eval` thô là RCE.
- *Thư viện biểu thức ngoài* — thêm dependency cho 54 biểu thức đơn giản là không tương xứng.

### D2. Canonical IR 2.0 là contract duy nhất

**Chọn:** mọi adapter (`openapi`, `swagger`, `utd-v1`, `draft`) sinh cùng một shape; `constraints` là object `{min,max,pattern,enum}`; `flags` gồm 6 khóa có nhãn `inferred` khi suy tự động.

**Vì:** loại bỏ hoàn toàn `_extract_range` với 3 pattern regex dự phòng; stage sau không phải đoán định dạng.

**Loại bỏ:**
- *Giữ spec JSON cũ làm chuẩn* — không chứa `constraints` cấu trúc, buộc mọi stage phải parse chuỗi.
- *pydantic* — thêm dependency; dataclass + validator tay ~150 dòng là đủ.

### D3. Nonce + chữ ký thay vì `answered_by`

**Chọn:** mỗi câu hỏi có `nonce` 16 byte; `interview.html` sinh `answers.json` với `sig = sha256(id|value|nonce|salt)`; `apply` tính lại và từ chối khi lệch (exit 4). Đường chat dùng `USER_CHAT` + `evidence` nguyên văn, được audit đánh dấu riêng.

**Vì:** AI chạy `--answer-id` không có nonce và không có salt của giao diện → không tạo được chữ ký hợp lệ. Chặn bằng toán học, không bằng luật cấm.

**Loại bỏ:**
- *Chỉ bỏ default của `--answered-by`* — vẫn là self-report, AI chỉ cần gõ đúng chuỗi.
- *Bắt buộc mở HTML* — không khả thi khi môi trường không có trình duyệt; đường chat có evidence là trung thực và minh bạch hơn.

### D4. Hash chain trong `run.json`

**Chọn:** sau mỗi stage ghi sha256 của artifact; stage sau đối chiếu trước khi đọc; lệch → exit 5.

**Vì:** phát hiện sửa tay SSOT sau audit, và làm `emit` không thể chạy trên dữ liệu chưa được kiểm.

**Loại bỏ:** *chỉ dựa timestamp* — không phát hiện sửa nội dung giữ nguyên mtime; *khoá file* — không giúp gì ngoài phạm vi một tiến trình.

### D5. Bỏ SQLite, dùng JSON

**Chọn:** `data/realistic.json` (82) + `data/payloads.json` (701); xoá `build_knowledge_db.py` và `test_knowledge.db`.

**Vì:** bỏ hẳn một stage compile và một bước "chạy build DB trước"; 800 bản ghi nạp vào bộ nhớ nhanh hơn tra SQLite.

**Loại bỏ:** *giữ SQLite* — thêm bước build, thêm file derived, thêm đường hỏng.

### D6. Cấu trúc package và CLI

```
utd/cli.py      dispatcher: ingest inventory interview lock generate audit emit reconcile
utd/io.py       utf-8 reconfigure, atomic write, sha256 helper
utd/state.py    run.json read/write/verify
utd/canonical.py dataclass + validate
utd/dsl.py      trigger_condition interpreter
utd/ingest/     openapi.py swagger.py rawjson.py draft.py
utd/match/      engine.py tier.py
utd/interview/  build.py export.py apply.py verify.py
utd/generate/   budget.py matrix.py data.py
utd/audit/      gates.py
utd/emit/       xlsx.py markdown.py
```

Exit code: `0` pass, `1` gate block, `2` input invalid, `3` insufficient info, `4` tamper, `5` hash mismatch.

**Vì:** một entry point cho phép test end-to-end bằng subprocess, và giữ `SKILL.md` chỉ cần mô tả 8 lệnh thay vì 11 script với flag rời rạc.

**Loại bỏ:** *giữ 11 script* — không có chỗ đặt contract chung; *make/just* — thêm công cụ ngoài mà không giải quyết vấn đề contract.

### D7. Tái dùng những gì đã đúng

Giữ nguyên: 10 file `rules/`, `data/realistic.json`, `data/payloads.json`, `raw_sources/`, `example_*.json` (dùng làm fixture), và toàn bộ đặc tả bố cục trong `references/layout-xlsx.md`. Phần `emit/xlsx.py` và `emit/markdown.py` được viết lại từ `build_unit_test_doc.py` nhưng đối chiếu từng mục với `layout-xlsx.md` để không mất chi tiết đã đúng.

**Vì:** phần emit là phần duy nhất của bản cũ chạy đúng và có 54 test pass; rủi ro nằm ở ingest/match/interview.

## Risks / Trade-offs

- **[Mất dữ liệu khi xoá]** repo không có git, xoá 5754 dòng không khôi phục được → Mitigation: task đầu tiên bắt buộc sao lưu `unit-test-designer/` ra ngoài workspace (zip hoặc copy), và `git init` + commit trước khi xoá bất kỳ file nào.
- **[Viết lại emit làm lệch bố cục]** đặc tả bố cục dài, dễ bỏ sót chi tiết như dropdown hay ẩn cột → Mitigation: test so từng sheet/ô với `layout-xlsx.md`; giữ `.xlsx` vàng từ bản cũ để so bằng mắt nếu có.
- **[DSL bị lạm dụng]** người viết rule có thể thêm biểu thức ngoài ngôn ngữ → Mitigation: validator từ chối file rule chứa node lạ, báo rule id; test kiểm 54 biểu thức hiện có parse được.
- **[Chữ ký không bảo vệ được đường chat]** `USER_CHAT` vẫn do AI ghi → Mitigation: `evidence` nguyên văn + nhãn riêng trong audit; không giả vờ nó mạnh bằng `USER_UI`.
- **[Không tương thích ngược CLI]** script/CI cũ gọi `interview_orchestrator.py` sẽ hỏng → Mitigation: adapter `utd ingest --from utd-v1` đọc dữ liệu cũ; CLI cũ không được duy trì, ghi rõ trong `SKILL.md`.
- **[Xung đột luật dùng MCP]** CLAUDE.md toàn cục buộc dùng `codebase-memory-mcp`, skill cấm nó ở S0–S6 → Mitigation: ghi rõ trong `SKILL.md` rằng lệnh cấm áp dụng trong phạm vi skill này và lý do (độc lập đặc tả), để người đọc biết đây là ngoại lệ có chủ đích, không phải thiếu sót.
- **[Cờ `inferred` sai]** 3 cờ tự suy có thể đặt sai → Mitigation: mọi cờ `inferred` xuất hiện trong checklist và người dùng xác nhận ở S2; 3 cờ còn lại bắt buộc hỏi.

## Migration Plan

1. Sao lưu: zip `unit-test-designer/` ra ngoài workspace; `git init` + commit toàn bộ `temp_test`.
2. Dựng `utd/` song song, chưa xoá gì; port dữ liệu (`rules/`, `data/`, `references/layout-xlsx.md`).
3. Viết `dsl.py` + test reachability; chỉ khi 150/150 mới tiếp.
4. Port `generate`/`audit`/`emit`, chạy trên `example_api_spec.json` để so kết quả với bản cũ.
5. Xoá `scripts/`, `tests/` cũ, `SKILL.md` cũ, `heuristic_matrix.json`, `test_knowledge.db`.
6. Viết `SKILL.md` mới ~120 dòng và `SCHEMA.md`.

Rollback: bản zip ở bước 1; ngoài ra giữ commit `pre-v2` để `git checkout` nếu đã init.

## Open Questions

Không có. Câu hỏi về nguồn 3 cờ nghiệp vụ đã được chốt: `has_status_field`, `is_multi_tenant`, `has_currency` suy tự động có nhãn `inferred`; `has_quota`, `has_dependencies`, `has_unique_field` hỏi người dùng ở S2.
