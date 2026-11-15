"""utd.match.question_id - Định danh câu hỏi ổn định qua các lần sinh lại.

Vấn đề được sửa: id cũ đặt theo **rule đại diện** (`sheet_ruleid_param`). Rule
đại diện là rule đầu tiên khớp trong nhóm, mà cờ nghiệp vụ quyết định rule nào
khớp — nên bật/tắt cờ làm id đổi dù nhóm không đổi. Câu trả lời cũ mất.

Giải pháp: id đặt theo **khoá gộp** (`sheet`, `target_element`, `param_name`),
là ba thứ đến từ spec và dữ liệu rule chứ không từ thứ tự khớp.

Dạng id (design.md D1, phương án A3):

    row:<sheet>:endpoint:<target>
    row:<sheet>:param:<param>:<target>

Câu hỏi cờ giữ dạng `<sheet>_FLAG_<name>` (xem `flags_questions.py`) để không
phá change `fix-flag-questions`.
"""

from __future__ import annotations

ID_PREFIX = "row"
ENDPOINT_KIND = "endpoint"
PARAM_KIND = "param"


def _clean(text: object) -> str:
    """Thay ký tự phân cách bằng gạch dưới để id không bị cắt sai."""
    raw = str(text or "").strip()
    return raw.replace(":", "_").replace("|", "_") or "unknown"


def endpoint_question_id(sheet_name: str, target_element: str) -> str:
    """Id cho câu hỏi cấp endpoint."""
    return ":".join(
        [ID_PREFIX, _clean(sheet_name), ENDPOINT_KIND, _clean(target_element)]
    )


def param_question_id(sheet_name: str, param_name: str, target_element: str) -> str:
    """Id cho câu hỏi gắn với một tham số."""
    return ":".join(
        [
            ID_PREFIX,
            _clean(sheet_name),
            PARAM_KIND,
            _clean(param_name),
            _clean(target_element),
        ]
    )


def build_question_id(sheet_name: str, target_element: str,
                      param_name: str | None = None) -> str:
    """Chọn dạng id theo việc câu hỏi có gắn tham số hay không."""
    if param_name:
        return param_question_id(sheet_name, param_name, target_element)
    return endpoint_question_id(sheet_name, target_element)


def parse_question_id(question_id: str) -> dict[str, str | None]:
    """Tách id thành các thành phần; trả dict rỗng nếu không phải dạng `row:`."""
    if not isinstance(question_id, str) or not question_id.startswith(ID_PREFIX + ":"):
        return {}
    parts = question_id.split(":")
    if len(parts) < 4:
        return {}
    kind = parts[2]
    if kind == ENDPOINT_KIND and len(parts) >= 4:
        return {
            "kind": ENDPOINT_KIND,
            "sheet_name": parts[1],
            "target_element": ":".join(parts[3:]),
            "param_name": None,
        }
    if kind == PARAM_KIND and len(parts) >= 5:
        return {
            "kind": PARAM_KIND,
            "sheet_name": parts[1],
            "param_name": parts[3],
            "target_element": ":".join(parts[4:]),
        }
    return {}
