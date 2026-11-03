from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import and_, delete, desc, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_id
from app.modules.iam.models import User
from app.modules.knowledge.models import (
    AgentKnowledgeSpaceBinding,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentVersion,
    KnowledgeSpace,
    KnowledgeSpaceGroupGrant,
    KnowledgeSpaceUserGrant,
)
from app.modules.tenancy.models import Group, GroupMember, TenantMembership


class KnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_spaces(
        self, tenant_id: str, *, query: str | None = None
    ) -> list[KnowledgeSpace]:
        statement = select(KnowledgeSpace).where(KnowledgeSpace.tenant_id == tenant_id)
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    KnowledgeSpace.name.icontains(normalized, autoescape=True),
                    KnowledgeSpace.classification.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.scalars(
            statement.order_by(KnowledgeSpace.created_at.desc(), KnowledgeSpace.id.desc())
        )
        return list(rows)

    async def get_space(self, tenant_id: str, space_id: str) -> KnowledgeSpace | None:
        return await self.session.scalar(
            select(KnowledgeSpace).where(
                KnowledgeSpace.tenant_id == tenant_id, KnowledgeSpace.id == space_id
            )
        )

    async def published_version_ids(self, tenant_id: str, space_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(KnowledgeDocumentVersion.id)
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocument.space_id == space_id,
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
            .order_by(KnowledgeDocumentVersion.id)
        )
        return tuple(rows)

    async def user_has_access(self, tenant_id: str, space_id: str, user_id: str) -> bool:
        direct = await self.session.scalar(
            select(KnowledgeSpaceUserGrant.id)
            .join(
                TenantMembership,
                (TenantMembership.tenant_id == KnowledgeSpaceUserGrant.tenant_id)
                & (TenantMembership.user_id == KnowledgeSpaceUserGrant.user_id),
            )
            .where(
                KnowledgeSpaceUserGrant.tenant_id == tenant_id,
                KnowledgeSpaceUserGrant.space_id == space_id,
                KnowledgeSpaceUserGrant.user_id == user_id,
                TenantMembership.status == "active",
            )
        )
        if direct is not None:
            return True
        grouped = await self.session.scalar(
            select(KnowledgeSpaceGroupGrant.id)
            .join(
                Group,
                (Group.tenant_id == KnowledgeSpaceGroupGrant.tenant_id)
                & (Group.id == KnowledgeSpaceGroupGrant.group_id),
            )
            .join(
                GroupMember,
                (GroupMember.tenant_id == Group.tenant_id) & (GroupMember.group_id == Group.id),
            )
            .join(
                TenantMembership,
                (TenantMembership.tenant_id == GroupMember.tenant_id)
                & (TenantMembership.id == GroupMember.membership_id),
            )
            .where(
                KnowledgeSpaceGroupGrant.tenant_id == tenant_id,
                KnowledgeSpaceGroupGrant.space_id == space_id,
                TenantMembership.user_id == user_id,
                TenantMembership.status == "active",
                Group.status == "active",
            )
        )
        return grouped is not None

    async def grants(
        self, tenant_id: str, space_id: str
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        users = await self.session.scalars(
            select(KnowledgeSpaceUserGrant.user_id)
            .where(
                KnowledgeSpaceUserGrant.tenant_id == tenant_id,
                KnowledgeSpaceUserGrant.space_id == space_id,
            )
            .order_by(KnowledgeSpaceUserGrant.user_id)
        )
        groups = await self.session.scalars(
            select(KnowledgeSpaceGroupGrant.group_id)
            .where(
                KnowledgeSpaceGroupGrant.tenant_id == tenant_id,
                KnowledgeSpaceGroupGrant.space_id == space_id,
            )
            .order_by(KnowledgeSpaceGroupGrant.group_id)
        )
        return tuple(users), tuple(groups)

    async def replace_grants(
        self, tenant_id: str, space_id: str, user_ids: Iterable[str], group_ids: Iterable[str]
    ) -> None:
        await self.session.execute(
            delete(KnowledgeSpaceUserGrant).where(
                KnowledgeSpaceUserGrant.tenant_id == tenant_id,
                KnowledgeSpaceUserGrant.space_id == space_id,
            )
        )
        await self.session.execute(
            delete(KnowledgeSpaceGroupGrant).where(
                KnowledgeSpaceGroupGrant.tenant_id == tenant_id,
                KnowledgeSpaceGroupGrant.space_id == space_id,
            )
        )
        self.session.add_all(
            KnowledgeSpaceUserGrant(
                id=new_id("knowledge_user_grant"),
                tenant_id=tenant_id,
                space_id=space_id,
                user_id=user_id,
            )
            for user_id in sorted(set(user_ids))
        )
        self.session.add_all(
            KnowledgeSpaceGroupGrant(
                id=new_id("knowledge_group_grant"),
                tenant_id=tenant_id,
                space_id=space_id,
                group_id=group_id,
            )
            for group_id in sorted(set(group_ids))
        )

    async def active_members_exist(self, tenant_id: str, user_ids: tuple[str, ...]) -> bool:
        if not user_ids:
            return True
        rows = await self.session.scalars(
            select(TenantMembership.user_id).where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.status == "active",
                TenantMembership.user_id.in_(set(user_ids)),
            )
        )
        return set(rows) == set(user_ids)

    async def active_groups_exist(self, tenant_id: str, group_ids: tuple[str, ...]) -> bool:
        if not group_ids:
            return True
        rows = await self.session.scalars(
            select(Group.id).where(
                Group.tenant_id == tenant_id, Group.status == "active", Group.id.in_(set(group_ids))
            )
        )
        return set(rows) == set(group_ids)

    async def list_documents(
        self, tenant_id: str, space_id: str, *, query: str | None = None
    ) -> list[tuple[KnowledgeDocument, int, int, str, str]]:
        statement = (
            select(
                KnowledgeDocument,
                KnowledgeDocumentVersion.version,
                func.count(KnowledgeChunk.id),
                User.id,
                User.display_name,
            )
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeDocument.tenant_id)
                & (KnowledgeDocumentVersion.document_id == KnowledgeDocument.id),
            )
            .outerjoin(
                KnowledgeChunk,
                (KnowledgeChunk.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeChunk.document_version_id == KnowledgeDocumentVersion.id),
            )
            .join(User, User.id == KnowledgeDocumentVersion.created_by_user_id)
            .where(
                KnowledgeDocument.tenant_id == tenant_id,
                KnowledgeDocument.space_id == space_id,
                or_(
                    and_(
                        KnowledgeDocument.status.in_(("active", "archived")),
                        KnowledgeDocumentVersion.status == "published",
                    ),
                    and_(
                        KnowledgeDocument.status.in_(("processing", "failed")),
                        KnowledgeDocumentVersion.status.in_(("processing", "failed")),
                    ),
                ),
            )
            .group_by(KnowledgeDocument.id, KnowledgeDocumentVersion.id, User.id)
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id)
        )
        normalized = query.strip() if query else ""
        if normalized:
            statement = statement.where(
                or_(
                    KnowledgeDocument.title.icontains(normalized, autoescape=True),
                    KnowledgeDocument.source_uri.icontains(normalized, autoescape=True),
                )
            )
        rows = await self.session.execute(statement)
        return [
            (document, version, int(chunk_count), changed_by_user_id, changed_by_display_name)
            for (
                document,
                version,
                chunk_count,
                changed_by_user_id,
                changed_by_display_name,
            ) in rows.tuples()
        ]

    async def available_document_exists(
        self, tenant_id: str, space_id: str, title_key: str
    ) -> bool:
        return (
            await self.session.scalar(
                select(KnowledgeDocument.id).where(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.space_id == space_id,
                    KnowledgeDocument.title_key == title_key,
                    KnowledgeDocument.status.in_(("active", "processing")),
                )
            )
        ) is not None

    async def document_versions(
        self, tenant_id: str, document_id: str
    ) -> tuple[KnowledgeDocument, tuple[KnowledgeDocumentVersion, ...]] | None:
        document = await self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id
            )
        )
        if document is None:
            return None
        versions = await self.session.scalars(
            select(KnowledgeDocumentVersion)
            .where(
                KnowledgeDocumentVersion.tenant_id == tenant_id,
                KnowledgeDocumentVersion.document_id == document_id,
            )
            .order_by(KnowledgeDocumentVersion.version.desc())
        )
        return document, tuple(versions)

    async def document_chunks(
        self, tenant_id: str, version_id: str, *, page: int, page_size: int
    ) -> tuple[tuple[KnowledgeChunk, ...], int]:
        conditions = (
            KnowledgeChunk.tenant_id == tenant_id,
            KnowledgeChunk.document_version_id == version_id,
        )
        total = await self.session.scalar(
            select(func.count()).select_from(KnowledgeChunk).where(*conditions)
        )
        chunks = await self.session.scalars(
            select(KnowledgeChunk)
            .where(*conditions)
            .order_by(KnowledgeChunk.ordinal, KnowledgeChunk.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return tuple(chunks), int(total or 0)

    async def document(self, tenant_id: str, document_id: str) -> KnowledgeDocument | None:
        return await self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.tenant_id == tenant_id, KnowledgeDocument.id == document_id
            )
        )

    async def search(
        self, tenant_id: str, space_id: str, query: str, limit: int
    ) -> list[tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion, float]]:
        terms = func.websearch_to_tsquery("simple", query)
        rank = func.ts_rank_cd(KnowledgeChunk.search_vector, terms)
        rows = await self.session.execute(
            select(
                KnowledgeChunk,
                KnowledgeDocument,
                KnowledgeDocumentVersion,
                rank.label("score"),
            )
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeChunk.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.space_id == space_id,
                KnowledgeChunk.search_vector.op("@@")(terms),
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
            .order_by(desc(rank), KnowledgeChunk.id)
            .limit(limit)
        )
        return list(rows.tuples())

    async def citation(
        self, tenant_id: str, chunk_id: str
    ) -> tuple[KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion] | None:
        row = await self.session.execute(
            select(KnowledgeChunk, KnowledgeDocument, KnowledgeDocumentVersion)
            .join(
                KnowledgeDocumentVersion,
                (KnowledgeDocumentVersion.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeDocumentVersion.id == KnowledgeChunk.document_version_id),
            )
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.tenant_id == KnowledgeDocumentVersion.tenant_id)
                & (KnowledgeDocument.id == KnowledgeDocumentVersion.document_id),
            )
            .join(
                KnowledgeSpace,
                (KnowledgeSpace.tenant_id == KnowledgeChunk.tenant_id)
                & (KnowledgeSpace.id == KnowledgeChunk.space_id),
            )
            .where(
                KnowledgeChunk.tenant_id == tenant_id,
                KnowledgeChunk.id == chunk_id,
                KnowledgeSpace.status == "active",
                KnowledgeDocument.status == "active",
                KnowledgeDocumentVersion.status == "published",
            )
        )
        return row.tuples().one_or_none()

    async def replace_agent_spaces(
        self, tenant_id: str, agent_id: str, space_ids: tuple[str, ...]
    ) -> None:
        await self.session.execute(
            delete(AgentKnowledgeSpaceBinding).where(
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.agent_id == agent_id,
            )
        )
        self.session.add_all(
            AgentKnowledgeSpaceBinding(
                id=new_id("agent_knowledge"),
                tenant_id=tenant_id,
                agent_id=agent_id,
                space_id=space_id,
            )
            for space_id in sorted(set(space_ids))
        )

    async def add_agent_space(self, tenant_id: str, agent_id: str, space_id: str) -> bool:
        statement = (
            insert(AgentKnowledgeSpaceBinding)
            .values(
                id=new_id("agent_knowledge"),
                tenant_id=tenant_id,
                agent_id=agent_id,
                space_id=space_id,
            )
            .on_conflict_do_nothing(constraint="uq_agent_knowledge_space")
            .returning(AgentKnowledgeSpaceBinding.id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def remove_agent_space(self, tenant_id: str, agent_id: str, space_id: str) -> bool:
        statement = (
            delete(AgentKnowledgeSpaceBinding)
            .where(
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.agent_id == agent_id,
                AgentKnowledgeSpaceBinding.space_id == space_id,
            )
            .returning(AgentKnowledgeSpaceBinding.id)
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none() is not None

    async def agent_space_ids(self, tenant_id: str, agent_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(AgentKnowledgeSpaceBinding.space_id)
            .where(
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.agent_id == agent_id,
            )
            .order_by(AgentKnowledgeSpaceBinding.space_id)
        )
        return tuple(rows)

    async def space_agent_ids(self, tenant_id: str, space_id: str) -> tuple[str, ...]:
        rows = await self.session.scalars(
            select(AgentKnowledgeSpaceBinding.agent_id)
            .where(
                AgentKnowledgeSpaceBinding.tenant_id == tenant_id,
                AgentKnowledgeSpaceBinding.space_id == space_id,
            )
            .order_by(AgentKnowledgeSpaceBinding.agent_id)
        )
        return tuple(rows)
