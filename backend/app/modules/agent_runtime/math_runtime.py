from __future__ import annotations

import ast
from importlib import import_module
from typing import Any, Protocol, cast

sp = cast(Any, import_module("sympy"))
sympy_parser = cast(Any, import_module("sympy.parsing.sympy_parser"))
parse_expr = sympy_parser.parse_expr

_MAX_EXPRESSION_CHARS = 1_000
_MAX_RESULT_CHARS = 4_000
_MAX_SYMBOLS = 20
_MAX_ORDER = 10
_MAX_EXPONENT = 1_000
_CONSTANTS: dict[str, Any] = {"pi": sp.pi, "E": sp.E, "e": sp.E, "I": sp.I}
_FUNCTIONS: dict[str, Any] = {
    "Abs": sp.Abs,
    "acos": sp.acos,
    "asin": sp.asin,
    "atan": sp.atan,
    "cos": sp.cos,
    "exp": sp.exp,
    "floor": sp.floor,
    "log": sp.log,
    "sin": sp.sin,
    "sqrt": sp.sqrt,
    "tan": sp.tan,
}


class MathRuntimePort(Protocol):
    async def handle(self, arguments: dict[str, object]) -> dict[str, object]: ...


class BuiltinMathRuntime:
    async def handle(self, arguments: dict[str, object]) -> dict[str, object]:
        try:
            return _handle(arguments)
        except ValueError as error:
            return {"status": "rejected", "code": "MATH_INPUT_INVALID", "message": str(error)}
        except Exception:
            return {"status": "rejected", "code": "MATH_EXECUTION_FAILED"}


def _handle(arguments: dict[str, object]) -> dict[str, object]:
    action = _text(arguments.get("action"), "action").casefold()
    if action == "evaluate":
        expression = _expression(arguments.get("expression"))
        exact = sp.simplify(expression.subs(_variables(arguments.get("variables"))))
        return _success(action, {"exact": _render(exact), "approx": _render(sp.N(exact))})
    if action == "simplify":
        return _success(
            action, {"result": _render(sp.simplify(_expression(arguments.get("expression"))))}
        )
    if action == "solve":
        equations = _equations(arguments)
        symbols = _symbols(arguments, equations)
        solution = sp.solve(equations, symbols[0] if len(symbols) == 1 else symbols, dict=True)
        return _success(action, {"solutions": _render(solution)})
    expression = _expression(arguments.get("expression"))
    variable = _symbol(_text(arguments.get("variable", "x"), "variable"))
    if action == "differentiate":
        order = arguments.get("order", 1)
        if not isinstance(order, int) or isinstance(order, bool) or not 1 <= order <= _MAX_ORDER:
            raise ValueError("order must be between 1 and 10")
        return _success(action, {"result": _render(sp.diff(expression, variable, order))})
    if action == "integrate":
        lower, upper = arguments.get("lower"), arguments.get("upper")
        if (lower is None) != (upper is None):
            raise ValueError("Both lower and upper are required for definite integration")
        result = (
            sp.integrate(expression, variable)
            if lower is None
            else sp.integrate(expression, (variable, _value(lower), _value(upper)))
        )
        return _success(action, {"result": _render(result)})
    raise ValueError("Unsupported math action")


def _equations(arguments: dict[str, object]) -> tuple[Any, ...]:
    raw = arguments.get("equations")
    values = cast(list[object], raw) if isinstance(raw, list) else [arguments.get("equation")]
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("equation or equations is required")
    return tuple(_equation(cast(str, item)) for item in values)


def _equation(value: str) -> Any:
    parts = value.split("=")
    if len(parts) == 1:
        return sp.Eq(_expression(parts[0]), 0)
    if len(parts) != 2:
        raise ValueError("An equation may contain only one equals sign")
    return sp.Eq(_expression(parts[0]), _expression(parts[1]))


def _symbols(arguments: dict[str, object], equations: tuple[Any, ...]) -> tuple[Any, ...]:
    raw = arguments.get("symbols")
    if isinstance(raw, list) and raw:
        values: tuple[Any, ...] = tuple(
            _symbol(_text(item, "symbol")) for item in cast(list[object], raw)
        )
    elif arguments.get("variable") is not None:
        values = (_symbol(_text(arguments.get("variable"), "variable")),)
    else:
        discovered: set[Any] = set()
        for equation in equations:
            discovered.update(cast(set[Any], equation.free_symbols))
        values = tuple(sorted(discovered, key=str))
    if not values or len(values) > _MAX_SYMBOLS:
        raise ValueError("solve requires one to twenty symbols")
    return values


def _expression(value: object) -> Any:
    source = _text(value, "expression")
    if len(source) > _MAX_EXPRESSION_CHARS:
        raise ValueError("expression is too long")
    tree = ast.parse(source, mode="eval")
    names = _validate_syntax(tree)
    symbols = {name: sp.Symbol(name) for name in names if name not in _CONSTANTS | _FUNCTIONS}
    if len(symbols) > _MAX_SYMBOLS:
        raise ValueError("expression has too many symbols")
    return parse_expr(
        source,
        local_dict={**_CONSTANTS, **_FUNCTIONS, **symbols},
        global_dict={"__builtins__": {}, "Integer": sp.Integer, "Float": sp.Float},
    )


def _validate_syntax(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        _validate_node_type(node)
        if isinstance(node, ast.Name):
            names.add(_validated_name(node))
        if isinstance(node, ast.Call):
            _validate_call(node)
        if isinstance(node, ast.BinOp):
            _validate_exponent(node)
    return names


def _validate_node_type(node: ast.AST) -> None:
    allowed_nodes = (
        ast.Expression,
        ast.BinOp,
        ast.UnaryOp,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Pow,
        ast.USub,
        ast.UAdd,
        ast.Mod,
        ast.Call,
        ast.Name,
        ast.Load,
        ast.Constant,
    )
    if not isinstance(node, allowed_nodes):
        raise ValueError("expression contains unsupported syntax")
    if isinstance(node, ast.Constant) and (
        isinstance(node.value, bool) or not isinstance(node.value, (int, float, complex))
    ):
        raise ValueError("expression constant is invalid")


def _validated_name(node: ast.Name) -> str:
    if not node.id.isidentifier() or node.id.startswith("_"):
        raise ValueError("expression symbol is invalid")
    return node.id


def _validate_call(node: ast.Call) -> None:
    if not isinstance(node.func, ast.Name):
        raise ValueError("expression function is invalid")
    if node.func.id not in _FUNCTIONS:
        raise ValueError("expression function is unavailable")


def _validate_exponent(node: ast.BinOp) -> None:
    if not isinstance(node.op, ast.Pow) or not isinstance(node.right, ast.Constant):
        return
    exponent = node.right.value
    if isinstance(exponent, (int, float)) and abs(exponent) > _MAX_EXPONENT:
        raise ValueError("expression exponent is too large")


def _variables(value: object) -> dict[Any, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("variables must be an object")
    values: dict[Any, Any] = {}
    for key, item in cast(dict[object, object], value).items():
        values[_symbol(_text(key, "variable"))] = _value(item)
    return values


def _value(value: object) -> Any:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError("math value is invalid")
    return _expression(value) if isinstance(value, str) else sp.sympify(value)


def _symbol(value: str) -> Any:
    if not value.isidentifier() or value.startswith("_"):
        raise ValueError("symbol is invalid")
    return sp.Symbol(value)


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _render(value: object) -> str:
    rendered = str(value)
    if len(rendered) > _MAX_RESULT_CHARS:
        raise ValueError("math result is too large")
    return rendered


def _success(action: str, result: dict[str, object]) -> dict[str, object]:
    return {"status": "ok", "action": action, "result": result}
