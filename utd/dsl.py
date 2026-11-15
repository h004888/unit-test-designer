"""utd.dsl - Thông dịch `trigger_condition` của rule bằng AST an toàn.

Vấn đề gốc của bản cũ: 150 rule đều khai `trigger_condition`, nhưng mã Python
bỏ qua nó và dùng if-chain phủ 37/72 `target_element`, khiến 51 rule nằm im.

Giải pháp: đọc và đánh giá đúng biểu thức đã có, với ngôn ngữ đóng:
  so sánh   ==  !=  <  <=  >  >=
  thành viên in / not in
  logic     and / or / not
  chuỗi     name.includes('x')  |  name.startswith('x')  |  name.endswith('x')
  hằng     true / false / null / 'literal' / 123

File rule là dữ liệu người dùng sửa được -> TUYỆT ĐỐI không dùng eval() thô.
Chỉ ast.parse(mode='eval') + whitelist node, rồi tự đệ quy đánh giá.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

# Ngôn ngữ đóng: chỉ những node này được phép xuất hiện trong biểu thức.
ALLOWED_NODES = {
    "Expression",
    "BoolOp",
    "And",
    "Or",
    "UnaryOp",
    "Not",
    "Compare",
    "Eq",
    "NotEq",
    "Lt",
    "LtE",
    "Gt",
    "GtE",
    "In",
    "NotIn",
    "Attribute",
    "Call",
    "Name",
    "Constant",
    "Tuple",
    "List",
    "Load",
}

# Chỉ những method chuỗi này được gọi trong biểu thức.
ALLOWED_METHODS = {"includes", "startswith", "endswith", "lower", "upper", "strip"}

# Tên của các toán tử so sánh -> hàm áp dụng.
_COMPARE_OPS = {
    "Eq": lambda a, b: a == b,
    "NotEq": lambda a, b: a != b,
    "Lt": lambda a, b: _safe_compare(a, b, lambda x, y: x < y),
    "LtE": lambda a, b: _safe_compare(a, b, lambda x, y: x <= y),
    "Gt": lambda a, b: _safe_compare(a, b, lambda x, y: x > y),
    "GtE": lambda a, b: _safe_compare(a, b, lambda x, y: x >= y),
    "In": lambda a, b: _safe_in(a, b),
    "NotIn": lambda a, b: not _safe_in(a, b),
}


class DSLSyntaxError(ValueError):
    """Biểu thức nằm ngoài ngôn ngữ đóng của DSL."""

    def __init__(self, message: str, expression: str = ""):
        self.expression = expression
        super().__init__(message)


@dataclass
class EvalResult:
    value: bool
    warnings: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.value


def _safe_compare(a: Any, b: Any, op) -> bool:
    try:
        return bool(op(a, b))
    except TypeError:
        return False


def _safe_in(a: Any, b: Any) -> bool:
    try:
        if b is None:
            return False
        return a in b
    except TypeError:
        return False


def _node_name(node: ast.AST) -> str:
    return type(node).__name__


def _normalise(expression: str) -> str:
    """Đổi cú pháp JS của dữ liệu sang cú pháp Python tương đương.

    Rule dùng `||` cho OR và `&&` cho AND (kiểu JavaScript). Python dùng
    `or` / `and`. Chuỗi literal được giữ nguyên: chỉ thay ký hiệu ngoài chuỗi.
    """
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(expression):
        char = expression[index]

        if quote:
            result.append(char)
            if char == "\\" and index + 1 < len(expression):
                result.append(expression[index + 1])
                index += 2
                continue
            if char == quote:
                quote = None
            index += 1
            continue

        if char in ("'", '"'):
            quote = char
            result.append(char)
            index += 1
            continue

        if expression.startswith("||", index):
            result.append(" or ")
            index += 2
            continue
        if expression.startswith("&&", index):
            result.append(" and ")
            index += 2
            continue
        if char == "!" and not expression.startswith("!=", index):
            result.append(" not ")
            index += 1
            continue

        result.append(char)
        index += 1

    return "".join(result)


def validate_syntax(expression: str) -> None:
    """Kiểm tra biểu thức thuộc ngôn ngữ đóng; ném DSLSyntaxError nếu không."""
    if not isinstance(expression, str):
        raise DSLSyntaxError(f"trigger_condition phải là chuỗi, nhận {type(expression).__name__}")
    text = expression.strip()
    if not text:
        raise DSLSyntaxError("trigger_condition rỗng")

    normalised = _normalise(text)

    try:
        tree = ast.parse(normalised, mode="eval")
    except SyntaxError as exc:
        raise DSLSyntaxError(f"cú pháp không hợp lệ: {exc.msg}", text) from exc

    for node in ast.walk(tree):
        name = _node_name(node)
        if name not in ALLOWED_NODES:
            raise DSLSyntaxError(f"node '{name}' nằm ngoài ngôn ngữ DSL", text)
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            raise DSLSyntaxError(f"không cho phép thuộc tính riêng tư '{node.attr}'", text)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr not in ALLOWED_METHODS:
                raise DSLSyntaxError(
                    f"method '{node.func.attr}' không được phép "
                    f"(chỉ: {', '.join(sorted(ALLOWED_METHODS))})",
                    text,
                )
    return None


def _resolve(node: ast.AST, context: dict[str, Any], warnings: list[str]) -> Any:
    """Đọc giá trị của một biểu thức con từ ngữ cảnh."""
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Name):
        name = node.id
        if name == "true":
            return True
        if name == "false":
            return False
        if name in ("null", "none", "None"):
            return None
        if name in context:
            value = context[name]
            if isinstance(value, dict):
                return _Namespace(value)
            return value
        warnings.append(f"trường không xác định: '{name}' -> coi là null")
        return None

    if isinstance(node, ast.Attribute):
        base_node = node.value
        base = _resolve(base_node, context, warnings)
        path = _attribute_path(base_node)
        if base is None:
            warnings.append(f"không đọc được thuộc tính '{path}' -> coi là null")
            return None
        if isinstance(base, _Namespace):
            return base.get(node.attr, warnings, path or node.attr)
        if isinstance(base, dict):
            return base.get(node.attr)
        # Thuộc tính truy cập trên giá trị vô hướng -> không xác định
        warnings.append(f"'{path}' không phải object -> coi là null")
        return None

    if isinstance(node, ast.List):
        return [_resolve(elt, context, warnings) for elt in node.elts]

    if isinstance(node, ast.Tuple):
        return tuple(_resolve(elt, context, warnings) for elt in node.elts)

    if isinstance(node, ast.Call):
        return _call(node, context, warnings)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not bool(_eval_node(node.operand, context, warnings))

    if isinstance(node, ast.Compare):
        return _eval_node(node, context, warnings)

    if isinstance(node, ast.BoolOp):
        return _eval_node(node, context, warnings)

    warnings.append(f"không hỗ trợ node '{_node_name(node)}' -> coi là false")
    return None


def _attribute_path(node: ast.AST) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _call(node: ast.Call, context: dict[str, Any], warnings: list[str]) -> Any:
    if not isinstance(node.func, ast.Attribute):
        warnings.append("chỉ được gọi method chuỗi -> coi là false")
        return None
    method = node.func.attr
    target = _resolve(node.func.value, context, warnings)
    args = [_resolve(arg, context, warnings) for arg in node.args]

    if isinstance(target, _Namespace):
        # `endpoint.auth.includes('jwt')` -> so khớp trên mọi giá trị con.
        flattened = " ".join(str(v) for v in target.flat_values())
        return _string_op(method, flattened, args, warnings)

    if isinstance(target, dict):
        flattened = " ".join(str(v) for v in target.values())
        return _string_op(method, flattened, args, warnings)

    if isinstance(target, (list, tuple)):
        flattened = " ".join(str(v) for v in target)
        return _string_op(method, flattened, args, warnings)

    if not isinstance(target, str):
        if target is None:
            return False
        try:
            target = str(target)
        except Exception:
            return False

    return _string_op(method, target, args, warnings)


def _string_op(method: str, target: str, args: list[Any], warnings: list[str]) -> Any:
    if method == "includes":
        if not args:
            return False
        needle = str(args[0] if args[0] is not None else "")
        return needle.lower() in target.lower()
    if method == "startswith":
        if not args:
            return False
        return target.lower().startswith(str(args[0]).lower())
    if method == "endswith":
        if not args:
            return False
        return target.lower().endswith(str(args[0]).lower())
    if method == "lower":
        return target.lower()
    if method == "upper":
        return target.upper()
    if method == "strip":
        return target.strip()

    warnings.append(f"method '{method}' không được phép")
    return None


def _eval_node(node: ast.AST, context: dict[str, Any], warnings: list[str]) -> bool:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, context, warnings)

    if isinstance(node, ast.Constant):
        return bool(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, context, warnings)

    if isinstance(node, ast.BoolOp):
        if isinstance(node.op, ast.And):
            for value in node.values:
                if not _eval_node(value, context, warnings):
                    return False
            return True
        # Or
        for value in node.values:
            if _eval_node(value, context, warnings):
                return True
        return False

    if isinstance(node, ast.Compare):
        left = _resolve(node.left, context, warnings)
        for op, comparator in zip(node.ops, node.comparators):
            right = _resolve(comparator, context, warnings)
            op_name = _node_name(op)
            comparator_fn = _COMPARE_OPS.get(op_name)
            if comparator_fn is None:
                warnings.append(f"toán tử '{op_name}' không được hỗ trợ -> coi là false")
                return False
            if not comparator_fn(left, right):
                return False
            left = right
        return True

    if isinstance(node, ast.Name):
        value = _resolve(node, context, warnings)
        return bool(value)

    if isinstance(node, ast.Attribute):
        return bool(_resolve(node, context, warnings))

    if isinstance(node, ast.Call):
        return bool(_call(node, context, warnings))

    if isinstance(node, (ast.List, ast.Tuple)):
        return True

    warnings.append(f"không hỗ trợ node '{_node_name(node)}' -> coi là false")
    return False


class _Namespace:
    """Bọc dict để truy cập thuộc tính lồng nhau, ví dụ `endpoint.auth.type`."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]):
        self._data = data

    def get(self, key: str, warnings: list[str] | None = None, path: str = "") -> Any:
        if key not in self._data:
            if warnings is not None:
                warnings.append(f"trường không xác định: '{path or key}' -> coi là null")
            return None
        value = self._data[key]
        if isinstance(value, dict):
            return _Namespace(value)
        return value

    def flat_values(self) -> list[Any]:
        """Mọi giá trị con (đủ sâu) — dùng cho `object.includes('x')`."""
        values: list[Any] = []
        stack: list[Any] = [self._data]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                stack.extend(current.values())
            elif isinstance(current, (list, tuple)):
                stack.extend(current)
            elif current is not None:
                values.append(current)
        return values

    def __repr__(self) -> str:  # pragma: no cover - chỉ để debug
        return f"_Namespace({self._data!r})"


def evaluate(expression: str, context: dict[str, Any]) -> EvalResult:
    """Đánh giá biểu thức trên ngữ cảnh; không bao giờ ném vì thiếu trường.

    Ném DSLSyntaxError nếu biểu thức nằm ngoài ngôn ngữ đóng.
    """
    validate_syntax(expression)
    warnings: list[str] = []
    text = expression.strip()

    if text in ("true", "True"):
        return EvalResult(value=True, warnings=warnings)
    if text in ("false", "False"):
        return EvalResult(value=False, warnings=warnings)

    try:
        tree = ast.parse(_normalise(text), mode="eval")
        value = _eval_node(tree.body, context, warnings)
    except DSLSyntaxError:
        raise
    except Exception as exc:  # lỗi bất ngờ trong đánh giá -> false + cảnh báo
        warnings.append(f"lỗi đánh giá: {exc} -> coi là false")
        value = False
    return EvalResult(value=bool(value), warnings=warnings)


def compile_expression(expression: str) -> str:
    """Kiểm tra biểu thức parse được; trả lại chính chuỗi đã strip."""
    validate_syntax(expression)
    return expression.strip()
