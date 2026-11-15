"""utd.match.flags_questions - Sinh sáu câu hỏi cờ nghiệp vụ cho mỗi module.

Lỗi mà module này sửa: ba cờ `has_quota`, `has_dependencies`, `has_unique_field`
chưa bao giờ được hỏi, luôn ở `source: "default"` = false, khiến 5 rule phụ thuộc
chúng bị bỏ qua với lý do sai sự thật ("điều kiện không thoả").

Thiết kế (design.md D1): câu cờ là mục checklist bình thường, tier CRITICAL,
id `<sheet>_FLAG_<name>`, đi qua đúng đường ký như mọi câu khác.

Ba cờ `inferred` hiển thị giá trị đã suy đoán để người dùng xác nhận hoặc sửa.
Ba cờ còn lại hỏi trắng Có/Không, không tuyên bố giá trị hiện tại.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from ..canonical import FLAG_NAMES, INFERABLE_FLAGS, Module
from .tier import CRITICAL

NONCE_BYTES = 16

FLAG_RULE_PREFIX = "FLAG:"
FLAG_TARGET_PREFIX = "flag:"

YES = "Có"
NO = "Không"
AGREE = "Đồng ý"
FLIP = "Sửa thành {value}"


@dataclass(frozen=True)
class FlagMeta:
    name: str
    label: str
    inferred: bool
    question_when_known: str
    question_when_unknown: str


FLAG_META: dict[str, FlagMeta] = {
    "has_status_field": FlagMeta(
        name="has_status_field",
        label="trường trạng thái / vòng đời",
        inferred=True,
        question_when_known=(
            "Hệ thống có trường trạng thái hoặc vòng đời thực thể "
            "(ví dụ status, state, lifecycle) không? "
            "Hệ thống đã suy đoán từ đặc tả: {value}"
        ),
        question_when_unknown=(
            "Hệ thống có trường trạng thái hoặc vòng đời thực thể không?"
        ),
    ),
    "is_multi_tenant": FlagMeta(
        name="is_multi_tenant",
        label="phân tách theo tenant",
        inferred=True,
        question_when_known=(
            "Hệ thống có phân tách dữ liệu theo tenant / tổ chức / workspace không? "
            "Hệ thống đã suy đoán từ đặc tả: {value}"
        ),
        question_when_unknown=(
            "Hệ thống có phân tách dữ liệu theo tenant / tổ chức / workspace không?"
        ),
    ),
    "has_currency": FlagMeta(
        name="has_currency",
        label="xử lý tiền tệ",
        inferred=True,
        question_when_known=(
            "Hệ thống có xử lý tiền tệ hoặc số tiền (amount, price, total, currency) không? "
            "Hệ thống đã suy đoán từ đặc tả: {value}"
        ),
        question_when_unknown=(
            "Hệ thống có xử lý tiền tệ hoặc số tiền không?"
        ),
    ),
    "has_quota": FlagMeta(
        name="has_quota",
        label="giới hạn tồn kho / hạn mức",
        inferred=False,
        question_when_known="",
        question_when_unknown=(
            "Hệ thống có giới hạn số lượng hoặc hạn mức cần kiểm soát đồng thời "
            "(tồn kho, quota, credit limit, số dư) không?"
        ),
    ),
    "has_dependencies": FlagMeta(
        name="has_dependencies",
        label="phụ thuộc dịch vụ ngoài",
        inferred=False,
        question_when_known="",
        question_when_unknown=(
            "Hệ thống có gọi dịch vụ bên ngoài hoặc hệ thống phụ thuộc "
            "(payment gateway, đối tác, message broker, API bên thứ ba) không?"
        ),
    ),
    "has_unique_field": FlagMeta(
        name="has_unique_field",
        label="ràng buộc duy nhất",
        inferred=False,
        question_when_known="",
        question_when_unknown=(
            "Hệ thống có trường bắt buộc duy nhất trên toàn hệ thống "
            "(email, mã đơn, số CCCD, username) không?"
        ),
    ),
}


def _make_nonce() -> str:
    return secrets.token_hex(NONCE_BYTES)


def flag_question_id(sheet_name: str, flag_name: str) -> str:
    return f"{sheet_name}_FLAG_{flag_name}"


def flag_rule_id(flag_name: str) -> str:
    return f"{FLAG_RULE_PREFIX}{flag_name}"


def parse_flag_rule_id(rule_id: str) -> str | None:
    """Trả tên cờ nếu `rule_id` là câu hỏi cờ, ngược lại None."""
    if not isinstance(rule_id, str) or not rule_id.startswith(FLAG_RULE_PREFIX):
        return None
    name = rule_id[len(FLAG_RULE_PREFIX):]
    return name if name in FLAG_NAMES else None


def parse_flag_target(target: str | None) -> str | None:
    """Trả tên cờ nếu `target` dạng `flag:<name>`."""
    if not isinstance(target, str) or not target.startswith(FLAG_TARGET_PREFIX):
        return None
    name = target[len(FLAG_TARGET_PREFIX):]
    return name if name in FLAG_NAMES else None


POSITIVE_VALUES = {"có", "co", "yes", "y", "true", "1", "đồng ý", "dong y", "agree", "ok"}
NEGATIVE_VALUES = {"không", "khong", "no", "n", "false", "0"}


def coerce_flag_value(raw: Any, current: bool | None = None) -> bool | None:
    """Chuyển câu trả lời thành boolean. Không nhận diện được -> None.

    Với cờ đã có giá trị (`inferred`), lựa chọn "Đồng ý" nghĩa là giữ nguyên
    giá trị hiện tại — không phải "không xác định". `current` cung cấp giá trị
    đó. Không có `current` thì "Đồng ý" không quyết định được.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return bool(raw)

    text = str(raw or "").strip().lower()
    if not text:
        return None

    # "Sửa thành Không" / "Sửa thành Có" -> đảo giá trị (kiểm trước exact match)
    for prefix in ("sửa thành ", "sua thanh "):
        if text.startswith(prefix):
            rest = text[len(prefix):].strip()
            if rest in POSITIVE_VALUES:
                return True
            if rest in NEGATIVE_VALUES:
                return False

    # "Đồng ý — giữ giá trị Có" / "Đồng ý ..." -> giữ nguyên giá trị đã suy.
    # Kiểm trước exact match vì "đồng ý" trần không quyết định được khi
    # chưa biết giá trị hiện tại.
    if text.startswith("đồng ý") or text.startswith("dong y"):
        return current

    if text in POSITIVE_VALUES:
        return True
    if text in NEGATIVE_VALUES:
        return False
    return None


def _yes_no(value: bool) -> str:
    return YES if value else NO


def _value_label(value: bool) -> str:
    return YES if value else NO


def build_flag_question(module: Module, flag_name: str) -> Any:
    """Sinh một Question cho cặp (module, cờ).

    Import `Question` cục bộ để tránh vòng import engine <-> flags_questions.
    """
    from .engine import Question

    meta = FLAG_META[flag_name]
    current_value = module.flags.get(flag_name)
    source = module.flags.source(flag_name)
    is_known = source != "default"

    if meta.inferred and is_known and source != "user":
        # Cờ đã suy tự động: hiển thị giá trị để xác nhận hoặc sửa.
        question_text = meta.question_when_known.format(value=_value_label(current_value))
        recommended = f"(Recommended) {AGREE} — giữ giá trị {_value_label(current_value)}"
        alternatives = [FLIP.format(value=_value_label(not current_value))]
        tier_reason = f"cờ suy tự động (nguồn: {source}) — cần người dùng xác nhận"
    elif is_known:
        # Cờ đã được người dùng xác nhận trước đó: cho đổi lại nếu cần.
        question_text = meta.question_when_unknown
        recommended = f"(Recommended) {YES} — giữ giá trị {_value_label(current_value)}"
        alternatives = [FLIP.format(value=_value_label(not current_value))]
        tier_reason = f"cờ đã xác nhận (nguồn: {source}) — có thể sửa lại"
    else:
        question_text = meta.question_when_unknown
        recommended = f"(Recommended) {NO} — không áp dụng"
        alternatives = [YES]
        tier_reason = "cờ nghiệp vụ — chưa có căn cứ trong đặc tả, bắt buộc hỏi"

    return Question(
        id=flag_question_id(module.sheet_name or module.id, flag_name),
        rule_id=flag_rule_id(flag_name),
        rule_ids=[flag_rule_id(flag_name)],
        tier=CRITICAL,
        dimension="0. Cờ nghiệp vụ (Module Flags)",
        category=meta.label,
        module_id=module.id,
        sheet_name=module.sheet_name,
        endpoint_id="",
        endpoint_label="(module)",
        target=f"{FLAG_TARGET_PREFIX}{flag_name}",
        param_name=None,
        question=question_text,
        questions=[question_text],
        recommended_option=recommended,
        alternative_options=alternatives,
        nonce=_make_nonce(),
        tier_reason=tier_reason,
        flag_name=flag_name,
        flag_current=current_value,
        flag_known=is_known,
    )


def build_flag_questions(module: Module) -> list[Any]:
    """Sinh đủ sáu câu cờ cho một module, đúng thứ tự FLAG_NAMES."""
    return [build_flag_question(module, name) for name in FLAG_NAMES]


def inferable_flags() -> tuple[str, ...]:
    return INFERABLE_FLAGS
