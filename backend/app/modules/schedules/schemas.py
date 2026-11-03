from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.iam.schemas import UserReference


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScheduleCreateRequest(_StrictModel):
    agent_id: str = Field(min_length=1, max_length=64)
    schedule_type: Literal["recurring", "once"]
    title: str = Field(min_length=1, max_length=191)
    input_text: str = Field(min_length=1, max_length=12000)
    cron_expr: str | None = Field(default=None, max_length=128)
    run_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def validate_timing(self) -> ScheduleCreateRequest:
        if self.schedule_type == "recurring" and not self.cron_expr:
            raise ValueError("cron_expr is required for recurring schedules")
        if self.schedule_type == "once" and self.run_at is None:
            raise ValueError("run_at is required for once schedules")
        return self


class ScheduleUpdateRequest(_StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=191)
    input_text: str | None = Field(default=None, min_length=1, max_length=12000)
    schedule_type: Literal["recurring", "once"] | None = None
    cron_expr: str | None = Field(default=None, max_length=128)
    run_at: datetime | None = None
    timezone: str | None = Field(default=None, max_length=64)


class ScheduleView(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    creator: UserReference | None = None
    title: str
    input_text: str
    schedule_type: str
    cron_expr: str | None
    run_at: datetime | None
    timezone: str
    status: str
    next_trigger_at: datetime | None
    last_triggered_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ScheduleExecutionView(BaseModel):
    id: str
    schedule_id: str
    scheduled_for: datetime
    trigger_type: str
    status: str
    interaction_id: str | None
    error_code: str | None
    created_at: datetime
