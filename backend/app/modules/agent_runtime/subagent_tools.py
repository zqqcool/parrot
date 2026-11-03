from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S


def subagent_dispatch_tool(
    max_tasks: int = 5,
    max_supporting_skills: int = 3,
) -> ToolDefinition:
    if not 1 <= max_tasks <= 5:
        raise ValueError("max_tasks must be between 1 and 5")
    if not 0 <= max_supporting_skills <= 8:
        raise ValueError("max_supporting_skills must be between 0 and 8")

    skill_reference = S.object(
        {
            "skill_id": S.string("已绑定 Skill id。"),
            "skill_version": S.integer("Skill 版本号，从 1 起。", minimum=1),
        },
        required=("skill_id", "skill_version"),
        description="固定版本的 Skill 引用。",
    )
    capability_scope = S.object(
        {
            "primary_skill": skill_reference,
            "supporting_skills": S.array(
                skill_reference,
                description="辅助 Skill 列表。",
                max_items=max_supporting_skills,
            ),
            "mcp_capability_ids": S.array(
                S.string(), description="允许的 MCP 能力 id 列表。", max_items=8
            ),
            "knowledge_enabled": S.boolean("是否允许子任务使用知识检索。"),
        },
        description="子任务可用能力范围；只能选择当前 Agent 已绑定的能力。",
    )
    source_span = S.object(
        {
            "start": S.integer("起始下标，含，从 0 开始。", minimum=0),
            "end": S.integer("结束下标，不含，必须大于 start。", minimum=1),
        },
        required=("start", "end"),
        description="source_quote 在最新用户请求中的 [start, end) 字符下标。",
    )
    task = S.object(
        {
            "id": S.string("任务稳定 id，供 depends_on 引用；省略时由运行时生成。"),
            "title": S.string("可选短标题，便于进度展示。"),
            "objective": S.string("子任务目标，应可独立完成并产出可汇总结果。"),
            "kind": S.string(
                "任务类型，用于运行时预算与能力裁剪。",
                enum=(
                    "general",
                    "information_lookup",
                    "code_read",
                    "code_review",
                    "code_change",
                    "test",
                    "document",
                ),
            ),
            "depends_on": S.array(S.string(), description="依赖的其他任务 id 列表。"),
            "required": S.boolean("为 true 时该任务失败会阻断父任务汇总。"),
            "capability_scope": capability_scope,
            "budget": S.object(
                {
                    "timeout_seconds": S.integer("超时秒数。", minimum=1),
                    "max_tool_calls": S.integer("最大工具调用次数。", minimum=1),
                },
                description="不得超过父任务剩余额度的可选执行预算。",
            ),
            "result_schema": S.open_object("期望子任务结果的 JSON Schema 片段。"),
            "tool_hints": S.array(S.string(), description="建议优先尝试的工具名提示。"),
            "source_hints": S.array(S.string(), description="可选来源提示，例如文档名或模块路径。"),
            "source_role": S.string("来源角色。", const="latest_user_request"),
            "source_quote": S.string("最新用户请求中的原文片段。"),
            "source_span": source_span,
            "dedupe_key": S.string("可选去重键。"),
        },
        required=("objective", "source_role", "source_quote", "source_span"),
        description="单个有界子任务。",
    )
    return ToolDefinition(
        name="subagent_dispatch",
        description=(
            "派发 1 到 5 个有界子任务；运行时用当前 Agent 配置创建子交互。"
            "每个任务必须引用最新用户请求中的原文片段（source_quote + source_span）。"
            "仅在可并行拆分、且子任务彼此独立或有明确 depends_on 时使用；"
            "不要为单一简单步骤派发子代理。"
        ),
        parameters=S.object(
            {
                "tasks": S.array(
                    task,
                    description="子任务列表。",
                    min_items=1,
                    max_items=max_tasks,
                )
            },
            required=("tasks",),
        ),
    )
