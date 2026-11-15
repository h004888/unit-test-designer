"""utd.generate.budget - Định lượng slot kiểm thử từ `constraints` cấu trúc.

Bản cũ dùng `_extract_range` với 3 pattern regex dự phòng trên chuỗi mô tả.
Bản mới đọc thẳng `constraints.min` / `constraints.max` đã chuẩn hoá ở ingest.

Mỗi endpoint sinh các slot:
  - 1 Normal (happy path)          -> bắt buộc cho mọi endpoint
  - BVA quanh biên (nếu có min/max) -> min-1, min, min+1, max-1, max, max+1
  - EP invalid (nếu có enum)        -> giá trị ngoài enum
  - Dual-path theo rule (nếu có)    -> mỗi rule cần 1 Normal/Boundary + 1 Abnormal
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..canonical import Endpoint, Module, Param

NORMAL = "Normal"
BOUNDARY = "Boundary"
ABNORMAL = "Abnormal"


@dataclass
class Slot:
    slot_id: str
    type: str
    target: str
    technique: str
    param_name: str | None = None
    param_value: Any = None
    rule_refs: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "slot_id": self.slot_id,
            "type": self.type,
            "target": self.target,
            "technique": self.technique,
            "param_name": self.param_name,
            "param_value": self.param_value,
            "rule_refs": self.rule_refs,
            "note": self.note,
        }


@dataclass
class Budget:
    method_name: str
    endpoint_id: str
    sheet_name: str
    slots: list[Slot] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_slots(self) -> int:
        return len(self.slots)

    def counts(self) -> dict[str, int]:
        result = {NORMAL: 0, BOUNDARY: 0, ABNORMAL: 0}
        for slot in self.slots:
            result[slot.type] = result.get(slot.type, 0) + 1
        return result

    def to_dict(self) -> dict[str, Any]:
        return {
            "method_name": self.method_name,
            "endpoint_id": self.endpoint_id,
            "sheet_name": self.sheet_name,
            "total_slots": self.total_slots,
            "normal_count": self.counts()[NORMAL],
            "boundary_count": self.counts()[BOUNDARY],
            "abnormal_count": self.counts()[ABNORMAL],
            "slots": [s.to_dict() for s in self.slots],
            "notes": self.notes,
        }


def _numeric_bounds(param: Param) -> tuple[int | float, int | float] | None:
    if not param.constraints.has_bounds():
        return None
    return param.constraints.min, param.constraints.max


def _string_length_bounds(param: Param) -> tuple[int, int] | None:
    if param.type != "string":
        return None
    if not param.constraints.has_bounds():
        return None
    lowest = param.constraints.min
    highest = param.constraints.max
    if isinstance(lowest, int) and isinstance(highest, int):
        return lowest, highest
    return None


def _bva_values(param: Param) -> list[int | float]:
    bounds = _numeric_bounds(param)
    if bounds is not None:
        lowest, highest = bounds
        candidates = [lowest - 1, lowest, lowest + 1, highest - 1, highest, highest + 1]
        unique: list[int | float] = []
        for value in candidates:
            if value not in unique:
                unique.append(value)
        return unique

    length_bounds = _string_length_bounds(param)
    if length_bounds is not None:
        lowest, highest = length_bounds
        return [lowest - 1, lowest, lowest + 1, highest - 1, highest, highest + 1]
    return []


def calculate_budget(module: Module, endpoint: Endpoint) -> Budget:
    """Tính slot cho MỘT endpoint."""
    method_name = endpoint.summary or endpoint.id or endpoint.path
    budget = Budget(
        method_name=method_name,
        endpoint_id=endpoint.id,
        sheet_name=module.sheet_name,
    )

    # 1. Happy path bắt buộc
    budget.slots.append(
        Slot(
            slot_id=f"{endpoint.id}-S01",
            type=NORMAL,
            target="endpoint:happy_path",
            technique="EP: Happy Path tiêu chuẩn",
            rule_refs=[r.id for r in endpoint.rules[:3]],
            note="luồng thành công tiêu biểu giữa vùng hợp lệ",
        )
    )

    index = 2

    # 2. BVA quanh biên của từng tham số có ràng buộc
    for param in endpoint.params:
        values = _bva_values(param)
        if not values:
            if param.required and param.constraints.is_empty():
                budget.notes.append(
                    f"tham số '{param.name}' required nhưng không có biên — "
                    f"không sinh BVA (cần hỏi người dùng để có ràng buộc)"
                )
            continue

        for value in values:
            kind = BOUNDARY
            # min-1 và max+1 là vi phạm biên -> Abnormal
            bounds = _numeric_bounds(param) or _string_length_bounds(param)
            if bounds is not None:
                lowest, highest = bounds
                if value < lowest or value > highest:
                    kind = ABNORMAL
            budget.slots.append(
                Slot(
                    slot_id=f"{endpoint.id}-S{index:02d}",
                    type=kind,
                    target=f"param:{param.name}",
                    technique=f"BVA: {param.name}={value}",
                    param_name=param.name,
                    param_value=value,
                    note=f"biên {value} của {param.name}",
                )
            )
            index += 1

    # 3. EP invalid cho enum
    for param in endpoint.params:
        if param.constraints.enum:
            budget.slots.append(
                Slot(
                    slot_id=f"{endpoint.id}-S{index:02d}",
                    type=ABNORMAL,
                    target=f"param:{param.name}",
                    technique=f"EP: {param.name} ngoài enum",
                    param_name=param.name,
                    param_value="__NOT_IN_ENUM__",
                    note=f"giá trị không thuộc enum {param.constraints.enum}",
                )
            )
            index += 1

    # 4. Dual-path: mỗi rule cần 1 case hợp lệ + 1 case vi phạm
    for rule in endpoint.rules:
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=NORMAL,
                target=f"rule:{rule.id}",
                technique=f"Rule hợp lệ: {rule.text[:60]}",
                rule_refs=[rule.id],
                note="kiểm chứng rule ở trạng thái thoả",
            )
        )
        index += 1
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=ABNORMAL,
                target=f"rule:{rule.id}",
                technique=f"Rule vi phạm: {rule.text[:60]}",
                rule_refs=[rule.id],
                note="kiểm chứng rule ở trạng thái vi phạm",
            )
        )
        index += 1

    # 5. Response exhaustion (cổng G4): chỉ sinh case cho mã 4xx/5xx mà đặc tả
    #    MÔ TẢ được điều kiện kích hoạt. Mã không có điều kiện là "không thể
    #    kiểm chứng từ đặc tả" — sinh case giả cho nó sẽ tạo Expected Results sai.
    declared: list[int] = []
    for response in endpoint.responses:
        if 200 <= response.status < 300:
            continue
        if response.status in declared:
            continue
        declared.append(response.status)
        if not (response.condition or "").strip():
            budget.notes.append(
                f"HTTP {response.status} được khai báo nhưng đặc tả không nêu điều kiện "
                f"kích hoạt — cổng G4 sẽ coi là không kiểm chứng được"
            )
            continue
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=ABNORMAL,
                target=f"status:{response.status}",
                technique=f"HTTP {response.status}: {response.condition[:60]}",
                note=response.condition or "",
            )
        )
        index += 1

    # 6. Missing/Null cho từng tham số required (cổng G1 và G8)
    for param in endpoint.params:
        if not param.required:
            continue
        if "authorization" in param.name.lower():
            continue  # đã có slot endpoint:auth
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=ABNORMAL,
                target=f"missing:{param.name}",
                technique=f"EP invalid: thiếu hẳn '{param.name}'",
                param_name=param.name,
                note=f"không truyền {param.name}",
            )
        )
        index += 1
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=ABNORMAL,
                target=f"null:{param.name}",
                technique=f"EP invalid: '{param.name}' = null",
                param_name=param.name,
                param_value="null",
                note=f"{param.name} truyền null",
            )
        )
        index += 1

    # 7. Security: endpoint có auth cần case 401 nếu chưa được khai báo
    if endpoint.auth.is_protected() and 401 not in declared:
        budget.slots.append(
            Slot(
                slot_id=f"{endpoint.id}-S{index:02d}",
                type=ABNORMAL,
                target="endpoint:auth",
                technique="Security: thiếu token -> 401",
                note="kiểm chứng missing Authorization",
            )
        )
        index += 1

    return budget


def calculate_budgets(modules: list[Module]) -> list[Budget]:
    """Tính ngân sách cho MỌI module và MỌI endpoint (chống bug modules[0])."""
    budgets: list[Budget] = []
    for module in modules:
        for endpoint in module.endpoints:
            budgets.append(calculate_budget(module, endpoint))
    return budgets


def summarise(budgets: list[Budget]) -> dict[str, Any]:
    totals = {NORMAL: 0, BOUNDARY: 0, ABNORMAL: 0}
    for budget in budgets:
        for key, count in budget.counts().items():
            totals[key] = totals.get(key, 0) + count
    return {
        "endpoints": len(budgets),
        "total_slots": sum(b.total_slots for b in budgets),
        **totals,
    }
