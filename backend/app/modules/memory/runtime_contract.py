from __future__ import annotations

from app.modules.agent_runtime.contracts import ToolDefinition
from app.modules.agent_runtime.tool_schema import JsonSchema as S

MEMORY_TYPES = frozenset(
    {
        "user_preference",
        "project_convention",
        "long_term_fact",
        "session_state",
        "conversation_summary",
    }
)
PINNED_MEMORY_TYPES = frozenset(
    {
        "user_preference",
        "project_convention",
        "conversation_summary",
    }
)


def memory_tool_definition() -> ToolDefinition:
    return ToolDefinition(
        name="memory",
        description=(
            "检索、读取、写入、替换、删除或确认/拒绝当前可见的运行时 Memory。"
            "需要跨轮次保留用户偏好、项目约定或长期事实时使用；"
            "不要用它存放一次性临时推理或最终答复正文。"
        ),
        parameters=S.object(
            {
                "action": S.string(
                    "操作类型。",
                    enum=(
                        "search",
                        "read",
                        "add",
                        "replace",
                        "delete",
                        "confirm",
                        "reject",
                    ),
                ),
                "query": S.string("search 时的检索关键词或短句。"),
                "memory_id": S.string(
                    "目标 Memory 记录 id；read/replace/delete/confirm/reject 时使用。"
                ),
                "item_id": S.string("统一条目 id；与 item_type 搭配定位来源。"),
                "item_type": S.string("条目类型。", enum=("memory", "message")),
                "sources": S.array(
                    S.string(enum=("memory", "message")),
                    description="search 时限定检索来源。",
                ),
                "target": S.string("写入作用域。", enum=("user", "agent", "conversation")),
                "key": S.string("同作用域下用于幂等更新的可选稳定键。"),
                "content": S.string("add/replace 时写入的可复用事实正文。"),
                "memory_type": S.string(
                    "Memory 分类。",
                    enum=tuple(sorted(MEMORY_TYPES)),
                ),
                "write_intent": S.string(
                    "写入动机。",
                    enum=("inferred", "explicit_user_request"),
                ),
                "expected_version": S.integer("replace/delete 的乐观锁版本。", minimum=1),
            },
            required=("action",),
        ),
    )
