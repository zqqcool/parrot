from __future__ import annotations

from sqlalchemy import (
    Boolean,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)


class TenantMembership(Base, TimestampMixin):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        UniqueConstraint("tenant_id", "id", name="uq_membership_tenant_id"),
        Index("ix_membership_tenant_status", "tenant_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")


class Group(Base, TimestampMixin):
    __tablename__ = "groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_group_tenant_name"),
        UniqueConstraint("tenant_id", "id", name="uq_group_tenant_id"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(String(512), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["groups.tenant_id", "groups.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    membership_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class GroupRole(Base):
    __tablename__ = "group_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "group_id"],
            ["groups.tenant_id", "groups.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class MembershipRole(Base):
    __tablename__ = "membership_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "membership_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "role_id"],
            ["roles.tenant_id", "roles.id"],
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    membership_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(64), primary_key=True)
