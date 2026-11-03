from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI, Request
from starlette.types import Scope

from app.core.error_messages import PUBLIC_ERROR_MESSAGES, public_error_message
from app.core.errors import AppError, handle_app_error


def test_every_literal_application_error_code_has_a_public_chinese_message() -> None:
    app_root = Path(__file__).resolve().parents[1] / "app"
    codes = {code for path in app_root.rglob("*.py") for code in _literal_app_error_codes(path)}
    codes.update(
        _literal_call_codes(
            app_root / "api" / "routes" / "im.py",
            "_send_error",
            argument_index=2,
        )
    )
    codes.update(
        _literal_call_codes(
            app_root / "api" / "routes" / "im_websocket.py",
            "_send_error",
            argument_index=2,
        )
    )
    codes.update(
        _literal_call_codes(
            app_root / "modules" / "agent_runtime" / "durable.py",
            "_fail",
            argument_index=2,
        )
    )

    assert codes
    assert not codes - PUBLIC_ERROR_MESSAGES.keys()
    assert all(_contains_chinese(PUBLIC_ERROR_MESSAGES[code]) for code in codes)


@pytest.mark.asyncio
async def test_app_error_response_uses_reviewed_chinese_message() -> None:
    response = await handle_app_error(
        _request(),
        AppError(
            "SKILL_BUILD_REQUIRED",
            "Executable Skill drafts must complete a current build before publishing",
        ),
    )

    body = json.loads(cast(bytes, response.body))
    assert body["code"] == "SKILL_BUILD_REQUIRED"
    assert body["message"] == (
        "可执行 Skill 的草稿尚未完成当前构建，请先点击“构建草稿”，构建成功后再发布。"
    )
    assert "Executable" not in body["message"]


def test_unknown_error_code_uses_safe_chinese_fallback() -> None:
    assert public_error_message("UNREGISTERED_ERROR") == (
        "请求处理失败，请稍后重试；如持续出现请提供请求编号。"
    )


def _literal_app_error_codes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    codes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "AppError" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            codes.add(first.value)
    return codes


def _literal_call_codes(path: Path, function_name: str, argument_index: int) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    codes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or len(node.args) <= argument_index:
            continue
        name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
        if name != function_name:
            continue
        argument = node.args[argument_index]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            codes.add(argument.value)
    return codes


def _contains_chinese(value: str) -> bool:
    return any("\u4e00" <= character <= "\u9fff" for character in value)


def _request() -> Request:
    scope: Scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": FastAPI(),
        "client": ("127.0.0.1", 1),
        "server": ("test", 80),
        "scheme": "http",
    }
    request = Request(scope)
    request.state.request_id = "req_test"
    return request
