from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RunRequesterReference(BaseModel):
    actor_type: str
    actor_id: str
    display_name: str


class RunRequesterSummary(RunRequesterReference):
    run_count: int
    active_run_count: int
    latest_run_at: datetime


class RunView(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    agent_name: str
    actor_type: str
    requester: RunRequesterReference
    entry_type: str
    input_type: str
    input_summary: str
    status: str
    runtime_execution_id: str | None = None
    created_at: datetime
    updated_at: datetime


class RunEventView(BaseModel):
    type: str
    event_id: str
    request_id: str
    occurred_at: datetime
    sequence: int
    data: dict[str, object]


class RunDiagnosticTraceView(BaseModel):
    id: str
    type: str
    sequence: int
    occurred_at: datetime
    data: dict[str, object]


class ConversationSummaryView(BaseModel):
    conversation_id: str
    agent_id: str
    agent_name: str
    message_count: int
    active_run_count: int
    latest_message_at: datetime


class ConversationMessageView(BaseModel):
    id: str
    interaction_id: str
    role: str
    content: str
    run_status: str
    created_at: datetime


class RunTaskView(BaseModel):
    id: str
    title: str
    objective: str
    kind: str
    depends_on: list[str]
    status: str
    child_interaction_id: str | None = None
    result_summary: str | None = None


class RunTaskBoardView(BaseModel):
    id: str | None = None
    status: str
    tasks: list[RunTaskView]
