from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S


def capability_tools() -> tuple[ToolDefinition, ...]:
    return (
        ToolDefinition(
            name="capability_search",
            description=(
                "查找或加载当前 Agent 显式绑定的 Skill 或 MCP 工具。"
                "优先使用 action=find_and_load 并提供非空 query，一次完成排序并加载顶部 Skill；"
                "仅需列出候选时用 find；已知 capability_id 时用 load。"
                "不要猜测未绑定的外部能力。"
            ),
            parameters=S.object(
                {
                    "action": S.string(
                        "操作类型。",
                        enum=("find", "load", "find_and_load"),
                    ),
                    "query": S.string("能力检索语句，应描述目标技能用途。"),
                    "capability_id": S.string("已发现的能力 id；load 时必填。"),
                    "role": S.string(
                        "Skill 加载角色；MCP 无需设置。",
                        enum=("primary", "supporting"),
                    ),
                },
                required=("action",),
            ),
        ),
        ToolDefinition(
            name="capability_execute",
            description=(
                "使用已加载的 Skill，或执行已发现且绑定到本 Agent 的 MCP 工具。"
                "instruction-only Skill 只返回指令文本，不会启动沙盒；"
                "可执行包仅通过配置的沙盒运行。"
                "调用前须先通过 capability_search 加载或确认 capability_id。"
            ),
            parameters=S.object(
                {
                    "capability_id": S.string(
                        "已加载或已发现的能力 id，必须来自 capability_search 结果。"
                    ),
                    "input": S.open_object(
                        "传给 Skill/MCP 的输入对象；字段须符合该能力自身 schema。"
                    ),
                },
                required=("capability_id",),
            ),
        ),
    )
