import pytest

from app.modules.agent_runtime.math_runtime import BuiltinMathRuntime


@pytest.mark.asyncio
async def test_math_runtime_evaluates_and_solves_safe_expressions() -> None:
    runtime = BuiltinMathRuntime()

    evaluated = await runtime.handle(
        {"action": "evaluate", "expression": "x**2 + 1", "variables": {"x": 3}}
    )
    solved = await runtime.handle({"action": "solve", "equation": "x**2 - 4 = 0"})

    assert evaluated["status"] == "ok"
    assert evaluated["result"] == {"exact": "10", "approx": "10.0000000000000"}
    assert solved["status"] == "ok"
    assert "-2" in str(solved["result"])
    assert "2" in str(solved["result"])


@pytest.mark.asyncio
async def test_math_runtime_rejects_python_execution_syntax() -> None:
    runtime = BuiltinMathRuntime()

    result = await runtime.handle({"action": "evaluate", "expression": "__import__('os')"})

    assert result["status"] == "rejected"
    assert result["code"] == "MATH_INPUT_INVALID"
