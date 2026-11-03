from typing import cast

import pytest

from app.modules.agent_runtime.time_runtime import BuiltinTimeRuntime


@pytest.mark.asyncio
async def test_time_runtime_parses_and_shifts_an_explicit_timezone() -> None:
    runtime = BuiltinTimeRuntime("Asia/Shanghai")

    result = await runtime.handle(
        {
            "action": "add",
            "value": "2026-07-13T10:00:00",
            "duration": "1d2h",
            "timezone": "Asia/Shanghai",
        }
    )

    assert result["status"] == "ok"
    payload = cast(dict[str, object], result["result"])
    shifted = cast(dict[str, object], payload["result"])
    assert shifted["iso"] == "2026-07-14T12:00:00+08:00"


@pytest.mark.asyncio
async def test_time_runtime_rejects_invalid_timezone() -> None:
    runtime = BuiltinTimeRuntime("UTC")

    result = await runtime.handle({"action": "now", "timezone": "Not/A_Timezone"})

    assert result["status"] == "rejected"
    assert result["code"] == "TIME_INPUT_INVALID"
