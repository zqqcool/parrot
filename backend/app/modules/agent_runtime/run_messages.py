from __future__ import annotations

from app.modules.agent_runtime.contracts import ChatMessage
from app.modules.agent_runtime.execution_helpers import taskboard_context
from app.modules.agent_runtime.prompt_composer import initial_messages
from app.modules.agent_runtime.resume_snapshot import restore_resume_snapshot
from app.modules.agent_runtime.subagent_continuation import (
    append_loop_continuation,
    is_loop_taskboard,
)
from app.modules.agent_runtime.taskboard import completed_task_board
from app.modules.interactions.history import ConversationHistoryMessage, ConversationTurn
from app.modules.interactions.runtime import RuntimeRequest


def messages_for_run(
    request: RuntimeRequest,
    user_text: str,
    memory_context: str,
    history: tuple[ConversationTurn, ...],
    resume_transcript: tuple[ConversationHistoryMessage, ...] = (),
    *,
    agent_system_prompt: str,
    is_knowledge_agent: bool,
    has_completed_board: bool,
) -> list[ChatMessage]:
    messages = initial_messages(
        user_text,
        memory_context,
        history,
        taskboard_context(request.task_board),
        request.resume_assistant_message,
        resume_transcript=resume_transcript,
        agent_system_prompt=agent_system_prompt,
        is_knowledge_agent=is_knowledge_agent,
    )
    if not has_completed_board or not request.resume_messages:
        return messages
    try:
        resumed = restore_resume_snapshot(request.resume_messages)
    except ValueError:
        return messages
    if not resumed:
        return messages
    board = completed_task_board(request.task_board)
    if board is not None and is_loop_taskboard(board):
        append_loop_continuation(resumed, board)
        return resumed
    resumed.append(ChatMessage(role="user", content=taskboard_context(request.task_board)))
    return resumed
