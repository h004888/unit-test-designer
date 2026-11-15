# SCHEMA — Hợp đồng dữ liệu giữa các stage

Mọi stage chỉ trao đổi qua các shape dưới đây. Thay đổi shape = thay đổi schema version.

---

## 1. Canonical IR 2.0 — `canonical/spec.json`

`utd ingest` sinh ra. Nguồn: `utd/canonical.py`.

```json
{
  "schema_version": "2.0",
  "project": {
    "name": "", "code": "", "creator": "", "reviewer": "",
    "version": "v1.0", "issue_date": "", "reference": "", "environment": ""
  },
  "auth_global": { "type": "jwt|oauth|api_key|basic|other|none", "roles": [] },
  "modules": [{
    "id": "mod-001",
    "module_name": "Order API",
    "sheet_name": "POST_api_orders",
    "kind": "http|function",
    "description": "", "pre_condition": "", "source_doc": "",
    "flags": {
      "values":  {"has_status_field": false, "has_quota": false,
                  "has_dependencies": false, "is_multi_tenant": false,
                  "has_unique_field": false, "has_currency": false},
      "sources": {"has_status_field": "inferred|user|default", "...": "..."}
    },
    "endpoints": [{
      "id": "ep-001",
      "http_method": "POST",
      "path": "/api/orders",
      "kind": "http|function",
      "summary": "",
      "auth": { "type": "jwt", "roles": ["user"] },
      "params": [{
        "name": "quantity", "in": "body|query|path|header|formData",
        "type": "string|integer|number|boolean|array|object",
        "required": true,
        "format": null, "enum": null, "default": null,
        "constraints": { "min": 1, "max": 100, "pattern": null, "enum": null }
      }],
      "responses": [{ "status": 400, "error_code": "VALIDATION_ERROR", "condition": "" }],
      "rules": [{ "id": "BR-02", "text": "...", "source": "SRS 3.2.1.b" }]
    }]
  }]
}
```

Ràng buộc bắt buộc (validator trong `canonical.py`):

| Trường | Điều kiện | Lỗi |
|---|---|---|
| `schema_version` | phải là `"2.0"` | exit 2 |
| `modules` | không rỗng | exit 2 |
| `sheet_name` | không rỗng, không trùng | exit 2 |
| `endpoints` | không rỗng mỗi module | exit 2 |
| `path` | bắt buộc khi `kind: http` | exit 2 |
| `params[].in` | một trong 5 giá trị | exit 2 |
| `constraints.min/max` | `min <= max` | exit 2 |
| `params[].required` + không có constraints | cần hỏi người dùng | exit 3 |

`constraints` LUÔN là đối tượng có 4 khoá, `null` khi không ràng buộc. Không stage nào parse chuỗi để tìm biên.

`flags.sources` ghi nguồn gốc: `inferred` (máy suy), `user` (người dùng xác nhận), `default` (chưa hỏi). Ba cờ suy được: `has_status_field`, `is_multi_tenant`, `has_currency`. Ba cờ còn lại bắt buộc `user`.

---

## 2. Checklist — `interview/checklist.json`

`utd inventory` sinh ra. Nguồn: `utd/match/engine.py`.

```json
{
  "schema_version": 1,
  "session_state": "AWAITING_USER_INTERACTION|INTERACTION_IN_PROGRESS|ALL_COMPLETED",
  "project": { "...": "..." },
  "coverage": {
    "total_rules": 150, "matched": 92, "skipped": 58, "coverage_ok": true,
    "questions": 86, "critical": 76, "standard": 10, "parse_errors": 0
  },
  "modules": [{ "id": "", "sheet_name": "", "module_name": "", "flags": {} }],
  "skipped_rules": [{
    "rule_id": "H-IDEMP-WEBHOOK-SIG-01", "dimension": "", "category": "",
    "target_element": "webhook_endpoint", "trigger_condition": "endpoint.path.includes('webhook')",
    "skipped_reason": "điều kiện ... không thoả trên N ngữ cảnh đã kiểm"
  }],
  "warnings": [],
  "questions": [{
    "id": "row:POST_api_orders:param:quantity:string_param",
    "rule_id": "H-DATA-STR-01",
    "rule_ids": ["H-DATA-STR-01", "H-DATA-STR-02"],
    "tier": "CRITICAL|STANDARD",
    "dimension": "", "category": "",
    "module_id": "", "sheet_name": "", "endpoint_id": "", "endpoint_label": "POST /api/orders",
    "target": "param:quantity|endpoint",
    "param_name": "quantity",
    "question": "câu hỏi đã render template",
    "questions": ["câu 1", "câu 2"],
    "recommended_option": "", "alternative_options": [],
    "nonce": "32 ký tự hex (16 byte)",
    "status": "PENDING|ANSWERED",
    "answered_by": null,
    "answer": null,
    "evidence": null,
    "tier_reason": "dimension '...' thuộc nhóm nghiệp vụ",
    "flag_name": null,
    "flag_current": null,
    "flag_known": false
  }],
  "removed_questions": [],
  "previous_sha256": null,
  "added_question_ids": []
}
```

Bất biến: `matched + skipped == total_rules`; mỗi `nonce` duy nhất; câu hỏi gộp theo (`endpoint_id`, `param_name`, `target_element`).

### Định danh câu hỏi

`id` là định danh **nhóm câu hỏi**, không phải định danh rule. Dạng:

```
row:<sheet>:endpoint:<target_element>
row:<sheet>:param:<param_name>:<target_element>

ví dụ:
  row:POST_api_orders:endpoint:state_machine_endpoint
  row:POST_api_orders:param:quantity:integer_or_number_param
```

Câu hỏi cờ dùng dạng riêng `<sheet>_FLAG_<flag_name>` (xem mục dưới).

Phân biệt hai trường:

| Trường | Ý nghĩa | Ổn định? |
|---|---|---|
| `id` | định danh nhóm câu hỏi; khoá để merge và giữ câu trả lời | có, miễn nhóm còn rule áp dụng |
| `rule_id` | rule đầu tiên khớp trong nhóm — chỉ để tham khảo/tra cứu | **không** — đổi khi cờ nghiệp vụ thay đổi |
| `rule_ids` | mọi rule trong nhóm; tăng khi cờ bật thêm rule | tăng dần |

Vì id ổn định, khi cờ bật làm nhóm mở rộng, câu trả lời cũ được giữ và áp dụng
cho cả rule mới. `utd inventory` in cảnh báo liệt kê rule mới cho mỗi câu đã trả lời
bị mở rộng, để người dùng biết và trả lời lại nếu cần.

### Tương thích ngược: checklist sinh trước khi đổi dạng id

Checklist có id dạng cũ (`<sheet>_<rule-id>_<param>`) sẽ **không khớp** id mới. Lần
`utd inventory` đầu tiên sau khi nâng cấp sẽ coi mọi câu là câu mới và đưa câu cũ vào
`removed_questions`. Không có migration: người dùng chạy lại `inventory` và trả lời lại.
Lý do: id cũ không chứa `target_element`, muốn map phải suy từ `rules/*.json` — logic
chỉ dùng một lần và có thể sai khi rule bị sửa.

### Sáu câu hỏi cờ

Mỗi module sinh đúng 6 mục có `rule_id` dạng `FLAG:<name>`, `tier: "CRITICAL"`,
`target: "flag:<name>"`, và ba trường bổ sung:

| Trường | Ý nghĩa |
|---|---|
| `flag_name` | tên cờ (`has_quota`, `has_dependencies`, `has_unique_field`, …) |
| `flag_current` | giá trị hiện tại (`true` / `false` / `null`) |
| `flag_known` | `true` khi cờ đã có giá trị (`inferred` hoặc `user`) |

Ba cờ `inferred` (`has_status_field`, `is_multi_tenant`, `has_currency`) hiển thị giá
trị đã suy và lựa chọn "Đồng ý" / "Sửa thành …". Ba cờ còn lại hỏi trắng Có/Không.
Câu trả lời được chuyển thành boolean qua `coerce_flag_value` (Có/Không, yes/no,
true/false, 1/0, "Đồng ý …", "Sửa thành …").

### `removed_questions` và `previous_sha256`

Khi cờ thay đổi làm một rule ngừng áp dụng, câu hỏi của nó KHÔNG bị xoá hẳn mà chuyển
vào `removed_questions` kèm `removed_reason`. `previous_sha256` ghi sha của checklist
ngay trước lần sinh lại; `added_question_ids` liệt kê câu mới thêm.

`utd interview --apply` dùng hai trường này để bỏ qua câu trả lời cho mục đã biến mất
CHỈ KHI `answers.json.checklist_sha256` khớp `checklist.previous_sha256`. Id lạ không
khớp vẫn bị từ chối với exit 4.

> **Giới hạn cần biết:** `checklist_sha256` là dấu hiệu, KHÔNG phải chữ ký số. Ai sửa
> được `answers.json` cũng sửa được sha đó. Cơ chế này phân biệt "câu hỏi biến mất hợp
> lệ" với "id gõ nhầm", không chống được kẻ có quyền ghi cả hai file.

---

## 3. Answers — `interview/answers.json`

`interview.html` sinh ra khi người dùng bấm xuất. Nguồn: `utd/interview/export.py`.

```json
{
  "schema_version": 1,
  "salt": "32 ký tự hex (sinh mỗi lần xuất, nằm trong HTML)",
  "createdAt": "ISO-8601",
  "answers": [
    { "id": "POST_api_orders_H-SEC-AUTH-01",
      "value": "trả lời của người dùng",
      "nonce": "nonce của câu hỏi",
      "sig": "sha256(id|value|nonce|salt)" }
  ]
}
```

`utd interview --apply` tính lại `sig` và từ chối toàn bộ file nếu lệch (exit 4). Không mục nào được ghi khi có một mục sai.

### Nguồn câu trả lời hợp lệ

| `answered_by` | Điều kiện | Áp cho CRITICAL? |
|---|---|---|
| `USER_UI` | có `sig` khớp | có |
| `USER_CHAT` | có `evidence` là nguyên văn | có |
| `STANDARD_BATCH` | qua `--batch-consent` | **không** |

---

## 4. Locked spec — `canonical/locked_spec.json` + `lock.sha256`

`utd lock` sinh ra từ `spec.json` sau khi `interview/verified.json` tồn tại và người dùng gõ `Chốt`/`OK`.

```json
{
  "schema_version": "2.0", "project": {}, "auth_global": {}, "modules": [],
  "interview": {
    "locked_at": "ISO-8601",
    "signoff": "USER",
    "answers_sha256": "sha256 của checklist đã verify",
    "answers": [{ "id": "", "rule_ids": [], "tier": "",
                  "param_name": null, "answer": "", "answered_by": "", "evidence": null }]
  }
}
```

`lock.sha256` chứa sha256 của `locked_spec.json` (chuẩn hoá newline). `utd generate` từ chối nếu lệch (exit 5).

---

## 5. SSOT — `canonical/unit_test_spec.json`

`utd generate` sinh ra, `utd audit` và `utd emit` đọc. Đây là nguồn duy nhất cho tài liệu.

```json
{
  "project": { "...": "..." },
  "stats_round": 3,
  "modules": [{
    "module_name": "", "sheet_name": "", "description": "", "pre_condition": "",
    "methods": [{
      "name": "createOrder",
      "endpoint_id": "ep-001",
      "api": { "http_method": "", "path": "", "summary": "", "source": "",
               "auth": "jwt", "request": [], "responses": [], "rules": [] },
      "test_cases": [{
        "id": "UTC001",
        "pre": "", "input": "",
        "expected": { "return": "", "exception": "", "log": "" },
        "type": "Normal|Abnormal|Boundary",
        "rule_refs": ["BR-01"],
        "note": ""
      }]
    }]
  }],
  "uncovered_rules": [],
  "zero_normal_sheets": [],
  "budgets": [],
  "meta": { "generated_modules": 2, "total_cases": 44, "total_rules": 11 }
}
```

Bất biến khi `utd generate` thành công: `uncovered_rules == []`, `zero_normal_sheets == []`, mỗi module có ít nhất một case `Normal`, mã `UTC` liên tục và ổn định trong từng sheet.

---

## 6. Audit report — `audit/report.json` + `audit/report.md`

Nguồn: `utd/audit/gates.py`.

```json
{
  "passed": true,
  "total_issues": 0,
  "gates": [{
    "gate": "G1", "name": "EP", "passed": true,
    "issue_count": 0,
    "issues": [{
      "gate": "G1", "gate_name": "EP", "sheet": "", "method": "",
      "message": "", "action": "", "case_id": "UTC003"
    }]
  }],
  "context": {
    "modules": 2,
    "coverage": { "total_rules": 150, "matched": 92, "skipped": 58, "unaccounted": 0 },
    "uncovered_rules": [],
    "zero_normal_sheets": []
  }
}
```

Chín cổng: `G1 EP`, `G2 BVA`, `G3 DUAL-PATH`, `G4 HTTP-STATUS`, `G5 ANTI-SLOP`, `G6 SECURITY`, `G7 SOURCE-RULE-COVERAGE`, `G8 EP-PROPER`, `G9 NO-SLOP-PROPERTY`.

---

## 7. Run state — `.unittest-design/run.json`

Nguồn: `utd/state.py`.

```json
{
  "version": 1,
  "stage": "ingest|inventory|interview|lock|generate|audit|emit|reconcile|null",
  "artifacts": {
    "spec":        { "path": ".unittest-design/canonical/spec.json", "sha256": "..." },
    "checklist":   { "path": "...", "sha256": "..." },
    "locked_spec": { "path": "...", "sha256": "..." },
    "ssot":        { "path": "...", "sha256": "..." },
    "audit_report":{ "path": "...", "sha256": "..." },
    "emit:index.md": { "path": "...", "sha256": "..." }
  },
  "gates": {
    "reachability": { "passed": true, "issues": [] },
    "interview":    { "passed": true, "issues": [] },
    "generate":     { "passed": true, "issues": [] },
    "audit":        { "passed": true, "issues": [] }
  },
  "updated_at": "ISO-8601"
}
```

`sha256` tính trên nội dung đã chuẩn hoá newline về `\n`, nên cùng nội dung trên Windows và Unix cho cùng hash.

### Điều kiện của `utd lock`

Ngoài `verified.json` tồn tại với `verified: true`, `lock` còn kiểm ba điều kiện:

1. `verified.json.checklist_sha256` khớp sha của `checklist.json` hiện tại — chặn
   sửa checklist sau bước verify.
2. Không còn cờ nào ở `source: "default"` trong `checklist.modules[].flags.sources`.
3. Cờ đã xác nhận (`source: "user"`) từ checklist được ghi đè vào
   `locked_spec.modules[].flags`; module không có trong checklist giữ nguyên cờ từ
   `spec.json`.

Điều kiện 3 là bắt buộc: thiếu nó, cờ xác nhận không tới được `generate`, và hai
điều kiện trên trở nên vô nghĩa.

### `source_access` (marker tự khai)

`run.json` ghi `source_access` để đánh dấu stage có đọc mã nguồn dự án hay không
(`"none"` cho ingest→emit, `"read"` sau reconcile). Đây là marker do chính skill ghi,
KHÔNG phải bằng chứng kiểm chứng được — đừng dùng nó để tuyên bố "đã không đọc code".

---

## 8. Exit code

| Mã | Ý nghĩa | Stage dùng |
|---|---|---|
| `0` | pass | mọi stage |
| `1` | gate block (còn PENDING, audit fail, thiếu report) | inventory, interview, lock, generate, audit, emit |
| `2` | input invalid (cấu trúc hỏng, thiếu file, thiếu module) | ingest, inventory, generate, emit |
| `3` | insufficient info (đầu vào đúng cấu trúc nhưng thiếu trường không suy được) | ingest (draft) |
| `4` | tamper (chữ ký sai, nguồn CRITICAL không hợp lệ) | interview |
| `5` | hash mismatch (artifact bị sửa ngoài luồng) | generate, emit |

---

## 9. Bảng tra nhanh: stage nào đọc/ghi gì

| Stage | Đọc | Ghi |
|---|---|---|
| `ingest` | file nguồn | `canonical/spec.json` |
| `inventory` | `canonical/spec.json`, `rules/*.json`, `data/tiers.json` | `interview/checklist.json` |
| `interview` | `interview/checklist.json`, `answers.json` | `checklist.json` (cập nhật), `interview.html`, `verified.json` |
| `lock` | `spec.json`, `checklist.json`, `verified.json` | `locked_spec.json`, `lock.sha256` |
| `generate` | `locked_spec.json`, `lock.sha256`, `data/realistic.json` | `unit_test_spec.json` |
| `audit` | `unit_test_spec.json`, `checklist.json` | `audit/report.json`, `audit/report.md` |
| `emit` | `unit_test_spec.json`, `audit/report.json` | `.xlsx`, `docs/*.md`, `docs/index.md` |
| `reconcile` | SSOT + mã nguồn dự án | `reconcile/gap_report.md` |
