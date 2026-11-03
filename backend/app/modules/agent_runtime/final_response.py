from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.modules.agent_runtime.contracts import ChatCompletion, ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S

FINAL_RESPONSE_TOOL_NAME = "final_response"
ASK_USER_TOOL_NAME = "ask_user"


TerminalIntentKind = Literal["final_response", "ask_user"]


class FinalResponseProtocolError(ValueError):
    """The model did not satisfy the user-response tool contract."""


@dataclass(frozen=True)
class TerminalIntent:
    kind: TerminalIntentKind
    question: str | None = None
    content: str | None = None


def ask_user_tool() -> ToolDefinition:
    return ToolDefinition(
        name=ASK_USER_TOOL_NAME,
        description=(
            "向用户提出一个简洁问题，获取继续工作所需的最少信息、选择或确认。"
            "会话中已有的信息不要再问。"
            "此工具必须单独调用，不可与其他工具并行，也不得在问题中混入最终答复。"
        ),
        parameters=S.object(
            {
                "question": S.string(
                    "面向用户的单一澄清问题；应短、可回答，且只问缺失信息。",
                    min_length=1,
                )
            },
            required=("question",),
        ),
    )


def final_response_tool() -> ToolDefinition:
    return ToolDefinition(
        name=FINAL_RESPONSE_TOOL_NAME,
        description=(
            "在尚未写出用户可见答复、且需要进入无工具作答轮时调用。"
            "优先传空参数，由 Final Renderer 撰写并流式输出答复。"
            "已输出完整用户答复后不要再调用；可选 content 仅作短答兼容路径。"
            "此工具必须单独调用。"
        ),
        parameters=S.object(
            {
                "content": S.string(
                    "可选的短答正文兼容字段；优先省略以便 Final Renderer 生成。",
                    min_length=1,
                )
            }
        ),
    )


def terminal_intent_from(completion: ChatCompletion) -> TerminalIntent | None:
    calls = completion.tool_calls
    terminal_calls = [
        call for call in calls if call.name in {FINAL_RESPONSE_TOOL_NAME, ASK_USER_TOOL_NAME}
    ]
    if not terminal_calls:
        return None
    if len(calls) != 1 or completion.content:
        raise FinalResponseProtocolError("terminal intent must be the only model output")
    call = terminal_calls[0]
    if call.name == FINAL_RESPONSE_TOOL_NAME:
        content = call.arguments.get("content")
        if set(call.arguments) == {"content"} and isinstance(content, str) and content.strip():
            return TerminalIntent(kind="final_response", content=content.strip())
        if not call.arguments:
            return TerminalIntent(kind="final_response")
        raise FinalResponseProtocolError("final_response.content must be a non-empty string")
    question = call.arguments.get("question")
    if not isinstance(question, str) or not question.strip() or set(call.arguments) != {"question"}:
        raise FinalResponseProtocolError("ask_user.question is required")
    return TerminalIntent(kind="ask_user", question=question.strip())
