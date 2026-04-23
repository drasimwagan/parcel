from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from parcel_shell.auth.schemas import RoleSummary, UserSummary


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12)
    role_ids: list[uuid.UUID] = Field(default_factory=list)


class UpdateUserRequest(BaseModel):
    email: EmailStr | None = None
    is_active: bool | None = None


class UserDetailResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    roles: list[RoleSummary]


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int
    offset: int
    limit: int


class CreateRoleRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None


class UpdateRoleRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None


class RoleDetailResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_builtin: bool
    permissions: list[str]


class PermissionResponse(BaseModel):
    name: str
    description: str
    module: str


class AssignRoleRequest(BaseModel):
    role_id: uuid.UUID


class AssignPermissionRequest(BaseModel):
    permission_name: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
