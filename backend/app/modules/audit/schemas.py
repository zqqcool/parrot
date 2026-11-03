from __future__ import annotations

from pydantic import BaseModel

from app.modules.iam.schemas import UserReference


class AuditView(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    actor_type: str
    actor: UserReference | None = None
    request_id: str
    created_at: str
