from __future__ import annotations

from typing import cast

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S


def schedule_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="schedule",
        description=(
            "创建、列出、更新或取消当前用户在本 Agent 下的定时任务。"
            "create/update/cancel 有副作用：仅在最新用户请求明确要求时调用，"
            "并附带原文引用 source_quote 与字符跨度 source_span。"
            "仅查询已有任务时用 list，无需 provenance。"
        ),
        parameters=S.object(
            {
                "action": S.string("操作类型。", enum=("create", "list", "update", "cancel")),
                "task_id": S.string("已有任务 id；update/cancel 必填。"),
                "title": S.string("任务标题；create 建议提供，update 可选。"),
                "input_text": S.string("到期执行时交给 Agent 的输入正文。"),
                "schedule_type": S.string("调度类型。", enum=("recurring", "once")),
                "cron_expr": S.string("周期任务的 cron 表达式，例如 '0 9 * * 1'。"),
                "run_at": S.string("一次性执行时间，ISO 8601，例如 '2026-07-22T09:00:00+08:00'。"),
                "timezone": S.string("IANA 时区，例如 'Asia/Shanghai'。"),
                "source_role": S.string("副作用操作的来源角色。", const="latest_user_request"),
                "source_quote": S.string("最新用户请求中的原文片段。"),
                "source_span": S.object(
                    {
                        "start": S.integer("起始下标，含，从 0 开始。", minimum=0),
                        "end": S.integer("结束下标，不含，必须大于 start。", minimum=1),
                    },
                    required=("start", "end"),
                    description="source_quote 在最新用户请求中的 [start, end) 字符下标。",
                ),
            },
            required=("action",),
        ),
    )


def validate_user_provenance(arguments: dict[str, object], user_text: str) -> None:
    if arguments.get("source_role") != "latest_user_request":
        raise ValueError("schedule changes must cite the latest user request")
    quote = arguments.get("source_quote")
    span = arguments.get("source_span")
    if not isinstance(quote, str) or not quote or len(quote) > 8_000:
        raise ValueError("schedule source quote is invalid")
    if not isinstance(span, dict):
        raise ValueError("schedule source span is invalid")
    typed_span = cast(dict[str, object], span)
    start, end = typed_span.get("start"), typed_span.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
        raise ValueError("schedule source span is invalid")
    if end > len(user_text) or user_text[start:end] != quote:
        raise ValueError("schedule source does not match the latest user request")
