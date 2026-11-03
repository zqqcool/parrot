from __future__ import annotations

import logging

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette import status

from app.core.agent_runtime import DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD
from app.core.agent_types import agent_type_policy
from app.core.clock import utc_now
from app.core.errors import AppError
from app.core.ids import new_id
from app.core.object_storage import ObjectStoragePort, ObjectUploadGrant
from app.infrastructure.db.session import DatabaseManager
from app.modules.agents.avatar_validation import (
    validate_agent_avatar,
    validate_agent_avatar_upload_metadata,
)
from app.modules.agents.models import AgentPublication
from app.modules.agents.ports import AgentAvatar, AgentPublicationPolicy
from app.modules.agents.repository import AgentPublicationRepository, AgentTypeRepository
from app.modules.agents.schemas import (
    AgentAdminView,
    AgentCreateRequest,
    AgentTypeView,
    AgentUpdateRequest,
    AgentView,
)
from app.modules.audit.service import append_audit
from app.modules.iam.permissions import AGENTS_PUBLISH, PLATFORM_TENANTS_MANAGE
from app.modules.iam.schemas import PrincipalContext

logger = logging.getLogger(__name__)


class AgentService:
    def __init__(
        self,
        session: AsyncSession,
        database: DatabaseManager,
        publication_policy: AgentPublicationPolicy | None = None,
        object_storage: ObjectStoragePort | None = None,
        max_avatar_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.session = session
        self.database = database
        self.publication_policy = publication_policy
        self.object_storage = object_storage
        self.max_avatar_bytes = max_avatar_bytes

    async def list_for_tenant(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        *,
        query: str | None = None,
    ) -> list[AgentAdminView]:
        await self._enter_tenant(principal, tenant_id, "agents.read")
        statement = select(AgentPublication).where(AgentPublication.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    AgentPublication.name.icontains(normalized, autoescape=True),
                    AgentPublication.slug.icontains(normalized, autoescape=True),
                    AgentPublication.description.icontains(normalized, autoescape=True),
                )
            )
        result = await self.session.execute(statement.order_by(AgentPublication.name))
        return [self.admin_view(item) for item in result.scalars()]

    async def list_types(self, principal: PrincipalContext) -> list[AgentTypeView]:
        if "agents.read" not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        types = await AgentTypeRepository(self.session).list_all()
        result: list[AgentTypeView] = []
        for item in types:
            policy = agent_type_policy(item.key)
            if policy is None:
                raise RuntimeError(f"Agent type policy is unavailable: {item.key}")
            result.append(
                AgentTypeView(
                    key=item.key,
                    name=item.name,
                    description=item.description,
                    is_default=item.is_default,
                    uses_knowledge=policy.uses_knowledge,
                    restricts_executable_skills=policy.restricts_executable_skills,
                )
            )
        return result

    async def create(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        payload: AgentCreateRequest,
    ) -> AgentAdminView:
        await self._enter_tenant(principal, tenant_id, "agents.manage")
        if payload.published:
            raise AppError(
                "AGENT_CONFIGURATION_REQUIRED",
                "Create the agent as a draft, configure a default LLM, then publish it",
                status.HTTP_409_CONFLICT,
            )
        existing = await self.session.execute(
            select(AgentPublication.id).where(AgentPublication.slug == payload.slug)
        )
        if existing.scalar_one_or_none():
            raise AppError("AGENT_CONFLICT", "Agent slug already exists", status.HTTP_409_CONFLICT)
        agent_type_key = await self._resolve_type_key(payload.agent_type_key)
        model = AgentPublication(
            id=new_id("agent"),
            tenant_id=tenant_id,
            runtime_agent_id=payload.runtime_agent_id,
            slug=payload.slug,
            name=payload.name,
            description=payload.description,
            system_prompt=payload.system_prompt,
            agent_type_key=agent_type_key,
            published=payload.published,
            allow_anonymous=payload.allow_anonymous,
            published_at=utc_now() if payload.published else None,
        )
        self.session.add(model)
        await self.session.flush()
        append_audit(
            self.session, principal, "agent.create", "agent", model.id, tenant_id=tenant_id
        )
        return self.admin_view(model)

    async def update(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        payload: AgentUpdateRequest,
    ) -> AgentAdminView:
        await self._enter_tenant(principal, tenant_id, "agents.manage")
        if payload.published is not None and AGENTS_PUBLISH not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        model = await self._get_tenant_agent(tenant_id, agent_id)
        values = payload.model_dump(exclude_none=True)
        if "agent_type_key" in values:
            await self._ensure_valid_type(values["agent_type_key"])
            if values["agent_type_key"] != model.agent_type_key:
                if self.publication_policy is None:
                    raise RuntimeError("Agent publication policy is not configured")
                await self.publication_policy.ensure_agent_type_change_allowed(
                    tenant_id, agent_id, values["agent_type_key"]
                )
        if payload.published is True and model.published is False:
            if self.publication_policy is None:
                raise RuntimeError("Agent publication policy is not configured")
            await self.publication_policy.ensure_publishable(tenant_id, agent_id)
            values["published_at"] = utc_now()
        if payload.published is False:
            values["published_at"] = None
        if values:
            await self.session.execute(
                update(AgentPublication).where(AgentPublication.id == agent_id).values(**values)
            )
            await self.session.refresh(model)
        append_audit(
            self.session,
            principal,
            "agent.update",
            "agent",
            model.id,
            audit_values_for_agent_update(values),
            tenant_id=tenant_id,
        )
        return self.admin_view(model)

    async def issue_avatar_upload(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        content_type: str,
        size_bytes: int,
    ) -> ObjectUploadGrant:
        await self._enter_tenant(principal, tenant_id, "agents.manage")
        await self._get_tenant_agent(tenant_id, agent_id)
        validate_agent_avatar_upload_metadata(content_type, size_bytes, self.max_avatar_bytes)
        staging_key = f"staging/agent-avatars/{tenant_id}/{agent_id}/{new_id('upload')}"
        return await self._object_storage().issue_upload_grant(
            staging_key, content_type, size_bytes
        )

    async def attach_avatar(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
        staging_key: str,
    ) -> AgentAdminView:
        await self._enter_tenant(principal, tenant_id, "agents.manage")
        model = await self._get_tenant_agent(tenant_id, agent_id)
        self._validate_staging_key(tenant_id, agent_id, staging_key)
        storage = self._object_storage()
        staged_object = await storage.read(staging_key)
        if staged_object is None:
            raise AppError(
                "AVATAR_UPLOAD_NOT_FOUND",
                "Avatar upload was not found or has expired",
                status.HTTP_404_NOT_FOUND,
            )
        avatar = validate_agent_avatar(
            staged_object.content, staged_object.content_type, self.max_avatar_bytes
        )
        key = f"avatars/{tenant_id}/{agent_id}/{new_id('avatar')}.{avatar.extension}"
        old_key = model.avatar_key
        try:
            await storage.write(key, avatar.content, avatar.content_type)
            model.avatar_key = key
            model.avatar_content_type = avatar.content_type
            await self.session.flush()
            append_audit(
                self.session,
                principal,
                "agent.avatar.attach",
                "agent",
                model.id,
                {"content_type": avatar.content_type, "size_bytes": len(avatar.content)},
                tenant_id=tenant_id,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            await storage.delete(key)
            raise
        await self._delete_staged_avatar(storage, staging_key)
        await self._delete_replaced_avatar(storage, old_key)
        return self.admin_view(model)

    async def get_avatar(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        agent_id: str,
    ) -> AgentAvatar:
        await self._enter_tenant(principal, tenant_id, "agents.read")
        return await self._load_avatar(await self._get_tenant_agent(tenant_id, agent_id))

    async def list_public(
        self,
        *,
        offset: int = 0,
        limit: int = 10,
        search: str | None = None,
    ) -> list[AgentView]:
        items = await AgentPublicationRepository(self.session).list_public(
            offset=offset,
            limit=limit,
            search=search,
        )
        return [self.view(item) for item in items]

    async def get_public(self, slug: str) -> AgentPublication:
        result = await self.session.execute(
            select(AgentPublication).where(
                AgentPublication.slug == slug,
                AgentPublication.status == "active",
                AgentPublication.published.is_(True),
                AgentPublication.allow_anonymous.is_(True),
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        return model

    async def get_public_avatar(self, slug: str) -> AgentAvatar:
        return await self._load_avatar(await self.get_public(slug))

    async def _get_tenant_agent(self, tenant_id: str, agent_id: str) -> AgentPublication:
        result = await self.session.execute(
            select(AgentPublication).where(
                AgentPublication.id == agent_id,
                AgentPublication.tenant_id == tenant_id,
            )
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        return model

    async def _ensure_valid_type(self, agent_type_key: str) -> None:
        if agent_type_policy(agent_type_key) is None or not await AgentTypeRepository(
            self.session
        ).exists(agent_type_key):
            raise AppError(
                "AGENT_TYPE_INVALID",
                "Agent type is not supported",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    async def _resolve_type_key(self, agent_type_key: str | None) -> str:
        if agent_type_key is not None:
            await self._ensure_valid_type(agent_type_key)
            return agent_type_key
        default_key = await AgentTypeRepository(self.session).default_key()
        if default_key is None:
            raise RuntimeError("Agent type catalog has no default type")
        if agent_type_policy(default_key) is None:
            raise RuntimeError(f"Agent type policy is unavailable: {default_key}")
        return default_key

    async def _load_avatar(self, model: AgentPublication) -> AgentAvatar:
        if not model.avatar_key or not model.avatar_content_type:
            raise AppError(
                "RESOURCE_NOT_FOUND", "Agent avatar not found", status.HTTP_404_NOT_FOUND
            )
        stored_object = await self._object_storage().read(model.avatar_key)
        if stored_object is None:
            logger.error("Agent avatar object is missing", extra={"agent_id": model.id})
            raise AppError(
                "RESOURCE_NOT_FOUND", "Agent avatar not found", status.HTTP_404_NOT_FOUND
            )
        return AgentAvatar(content=stored_object.content, content_type=model.avatar_content_type)

    def _object_storage(self) -> ObjectStoragePort:
        if self.object_storage is None:
            raise RuntimeError("Object storage is not configured")
        return self.object_storage

    async def _delete_replaced_avatar(self, storage: ObjectStoragePort, key: str | None) -> None:
        if not key:
            return
        try:
            await storage.delete(key)
        except Exception:
            logger.warning("Unable to delete replaced agent avatar", extra={"avatar_key": key})

    async def _delete_staged_avatar(self, storage: ObjectStoragePort, key: str) -> None:
        try:
            await storage.delete(key)
        except Exception:
            logger.warning("Unable to delete staged agent avatar", extra={"avatar_key": key})

    @staticmethod
    def _validate_staging_key(tenant_id: str, agent_id: str, staging_key: str) -> None:
        prefix = f"staging/agent-avatars/{tenant_id}/{agent_id}/upload_"
        if not staging_key.startswith(prefix) or "/" in staging_key[len(prefix) :]:
            raise AppError(
                "AVATAR_UPLOAD_INVALID",
                "Avatar upload does not belong to this agent",
                status.HTTP_422_UNPROCESSABLE_CONTENT,
            )

    async def _enter_tenant(
        self,
        principal: PrincipalContext,
        tenant_id: str,
        permission: str,
    ) -> None:
        if (
            principal.tenant_id != tenant_id
            and PLATFORM_TENANTS_MANAGE not in principal.permissions
        ):
            raise AppError("RESOURCE_NOT_FOUND", "Agent not found", status.HTTP_404_NOT_FOUND)
        if permission not in principal.permissions:
            raise AppError("FORBIDDEN", "Permission denied", status.HTTP_403_FORBIDDEN)
        await self.database.set_tenant(self.session, tenant_id)

    @staticmethod
    def view(item: AgentPublication) -> AgentView:
        return AgentView(
            id=item.id,
            tenant_id=item.tenant_id,
            runtime_agent_id=item.runtime_agent_id,
            slug=item.slug,
            name=item.name,
            description=item.description,
            status=item.status,
            agent_type_key=item.agent_type_key,
            published=item.published,
            allow_anonymous=item.allow_anonymous,
            avatar_present=bool(item.avatar_key and item.avatar_content_type),
        )

    @staticmethod
    def admin_view(item: AgentPublication) -> AgentAdminView:
        threshold = getattr(item, "capability_relevance_threshold", None)
        return AgentAdminView(
            **AgentService.view(item).model_dump(),
            system_prompt=item.system_prompt,
            capability_relevance_threshold=(
                DEFAULT_CAPABILITY_RELEVANCE_THRESHOLD if threshold is None else threshold
            ),
        )


def audit_values_for_agent_update(values: dict[str, object]) -> dict[str, object]:
    audit_values = {key: value for key, value in values.items() if key != "system_prompt"}
    if "system_prompt" in values:
        audit_values["system_prompt_configured"] = bool(values["system_prompt"])
    return audit_values
