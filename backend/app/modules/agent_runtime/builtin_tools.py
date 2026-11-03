from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S
from app.modules.knowledge.runtime_contract import knowledge_search_tool_definition
from app.modules.memory.runtime_contract import memory_tool_definition
from app.modules.schedules.runtime_contract import schedule_tool_definition


def runtime_builtin_tools() -> tuple[ToolDefinition, ...]:
    return (
        memory_tool_definition(),
        ToolDefinition(
            name="todo",
            description=(
                "维护本轮交互的有界进度清单（最多 20 项）。"
                "多步骤任务开始时创建，推进时更新状态；"
                "不要用它记录最终答复或替代 Memory。"
            ),
            parameters=S.object(
                {
                    "todos": S.array(
                        S.object(
                            {
                                "id": S.string("清单项稳定 id，同轮次内唯一。"),
                                "content": S.string("待办内容，应是可检查的一步动作。"),
                                "status": S.string(
                                    "状态。",
                                    enum=(
                                        "pending",
                                        "in_progress",
                                        "completed",
                                        "cancelled",
                                    ),
                                ),
                            },
                            required=("id", "content", "status"),
                        ),
                        description="待合并或整体替换的清单项；merge=true 时按 id 合并。",
                        max_items=20,
                    ),
                    "merge": S.boolean("true=按 id 合并更新；false 或不传则按传入列表整体替换。"),
                }
            ),
        ),
        ToolDefinition(
            name="time",
            description=(
                "读取、解析、比较、加减、时区转换或格式化日期时间。"
                "需要精确时间计算或时区处理时使用；不要猜测当前时间，应调用 action=now。"
            ),
            parameters=S.object(
                {
                    "action": S.string(
                        "时间操作类型。",
                        enum=(
                            "now",
                            "parse",
                            "diff",
                            "add",
                            "subtract",
                            "convert_timezone",
                            "format",
                        ),
                    ),
                    "value": S.scalar_union(
                        "string",
                        "number",
                        description="主时间值：ISO 字符串或 Unix 时间戳。",
                    ),
                    "start": S.scalar_union("string", "number", description="diff 的起始时间。"),
                    "end": S.scalar_union("string", "number", description="diff 的结束时间。"),
                    "duration": S.string("加减时长，例如 '1d'、'2h30m'、'P1DT2H'。"),
                    "timezone": S.string("源时区或解释时区，IANA 名称，例如 'Asia/Shanghai'。"),
                    "target_timezone": S.string("convert_timezone 的目标 IANA 时区。"),
                    "output_format": S.string(
                        "输出形态；strftime 时需同时提供 strftime_format。",
                        enum=("iso", "date", "datetime", "timestamp", "strftime"),
                    ),
                    "strftime_format": S.string(
                        "output_format=strftime 时使用的受限 strftime 格式。"
                    ),
                },
                required=("action",),
            ),
        ),
        ToolDefinition(
            name="math",
            description=(
                "对安全的符号表达式进行求值、化简、求解、求导或积分。"
                "需要精确数值或代数结果时使用；简单四则运算也可直接调用，避免手算误差。"
            ),
            parameters=S.object(
                {
                    "action": S.string(
                        "数学操作类型。",
                        enum=(
                            "evaluate",
                            "simplify",
                            "solve",
                            "differentiate",
                            "integrate",
                        ),
                    ),
                    "expression": S.string("表达式，例如 '2*x + 3' 或 'sin(x)**2'。"),
                    "equation": S.string("单方程，例如 'x**2 - 4 = 0'。"),
                    "equations": S.array(S.string(), description="方程组字符串列表。"),
                    "variable": S.string("主变量名，例如 'x'。"),
                    "symbols": S.array(S.string(), description="需要声明的符号名列表。"),
                    "variables": S.open_object('代入求值的变量映射，例如 {"x": 2, "y": 3}。'),
                    "order": S.integer("求导或积分阶数。", minimum=1, maximum=10),
                    "lower": S.scalar_union("string", "number", description="定积分下限。"),
                    "upper": S.scalar_union("string", "number", description="定积分上限。"),
                },
                required=("action",),
            ),
        ),
    )


def knowledge_search_tool() -> ToolDefinition:
    return knowledge_search_tool_definition()


def schedule_tool() -> ToolDefinition:
    return schedule_tool_definition()


def script_tool() -> ToolDefinition:
    return ToolDefinition(
        name="script",
        description=(
            "仅在已配置的 Parrot 沙盒中运行短 Python 或 POSIX shell 脚本。"
            "无网络访问。"
            "仅在内置 time/math 等工具无法完成处理时使用；不要用它访问外部系统。"
        ),
        parameters=S.object(
            {
                "language": S.string("脚本语言。", enum=("python", "shell")),
                "code": S.string("要执行的完整短脚本正文；应自包含且无网络依赖。"),
                "timeout_seconds": S.integer("执行超时秒数；省略时使用运行时默认值。", minimum=1),
                "network_access": S.boolean("必须为 false 或省略；沙盒禁止联网。"),
                "input_payload": S.open_object("可选输入对象，供脚本读取的结构化参数。"),
            },
            required=("language", "code"),
        ),
    )
