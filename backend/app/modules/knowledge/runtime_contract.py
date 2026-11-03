from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S


def knowledge_search_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="knowledge_search",
        description=(
            "在当前知识型 Agent 已绑定且生效的知识空间中检索。"
            "初始证据不足，或需要更窄的跟进查询时使用。"
            "运行时会再次施加租户、Agent 绑定与内容状态过滤；"
            "同一意图在已取得可用证据后禁止无新理由的重复或近义检索。"
        ),
        parameters=S.object(
            {
                "query": S.string(
                    "检索查询，应具体到实体、策略名或问题焦点。",
                    min_length=1,
                    max_length=1_000,
                ),
                "limit": S.integer(
                    "返回条数上限；需要更少噪声时可传 3–6。",
                    minimum=1,
                    maximum=12,
                ),
            },
            required=("query",),
        ),
    )
