from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TenantAccess(BaseModel):
    id: str
    slug: str
    name: str


class PrincipalContext(BaseModel):
    tenant_id: str | None
    subject_type: str = "user"
    subject_id: str
    username: str
    display_name: str
    avatar_present: bool = False
    permissions: tuple[str, ...]
    tenants: tuple[TenantAccess, ...]
    must_change_password: bool
    request_id: str


class SessionData(BaseModel):
    principal: PrincipalContext
    csrf_token: str
    expires_at: datetime
    password_min_length: int
    default_schedule_timezone: str


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)


class CurrentUserProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=150)


class TenantSwitchRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)


class UserReference(BaseModel):
    id: str
    display_name: str
    avatar_present: bool


class UserView(UserReference):
    username: str
    email: str | None
    status: str
    must_change_password: bool


class UserAvatarUploadRequest(BaseModel):
    content_type: str = Field(min_length=1, max_length=128)
    size_bytes: int = Field(ge=1)


class UserAvatarUploadGrantView(BaseModel):
    object_key: str
    upload_key: str
    upload_token: str
    expires_at: datetime


class UserAvatarAttachRequest(BaseModel):
    object_key: str = Field(min_length=1, max_length=256)


class UserCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    display_name: str = Field(min_length=1, max_length=150)
    temporary_password: str = Field(min_length=10, max_length=256)


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class PasswordResetRequest(BaseModel):
    temporary_password: str = Field(min_length=10, max_length=256)


class RoleView(BaseModel):
    id: str
    key: str
    name: str
    description: str
    status: str
    is_system: bool
    permissions: tuple[str, ...] = ()


class RoleCreateRequest(BaseModel):
    key: str = Field(pattern="^[a-z][a-z0-9_.-]{2,127}$")
    name: str = Field(min_length=1, max_length=150)
    description: str = Field(default="", max_length=512)
    permissions: tuple[str, ...] = ()


class PermissionView(BaseModel):
    key: str
    description: str
