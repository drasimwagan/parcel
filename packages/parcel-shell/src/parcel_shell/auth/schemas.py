from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12)


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime


class RoleSummary(BaseModel):
    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    user: UserSummary
    roles: list[RoleSummary]
    permissions: list[str]
