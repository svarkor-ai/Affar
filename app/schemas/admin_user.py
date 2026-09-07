"""Admin-user wire schemas (MC 1120.1).

One Pydantic model set for the user-admin aggregate (C9/C23 style). Routers
return schema objects, never raw ORM objects, and NEVER expose password_hash.

The role field is validated against the closed ROLES set (C-F) — no dynamic
roles in this scope.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.auth import ROLES


class AdminUserCreate(BaseModel):
    """POST /api/admin/users body."""

    username: str = Field(min_length=1, max_length=50)
    role: str
    email: Optional[str] = Field(default=None, max_length=255)
    password: str = Field(min_length=6, max_length=128)

    @field_validator("role")
    @classmethod
    def _role_in_closed_set(cls, v: str) -> str:
        if v not in ROLES:
            raise ValueError(f"rollen '{v}' finns inte i {list(ROLES)}")
        return v


class AdminUserUpdate(BaseModel):
    """PATCH /api/admin/users/{id} body — every field optional.

    Password reset is deliberately out of scope (brief: not unless trivial).
    """

    role: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("role")
    @classmethod
    def _role_in_closed_set(cls, v):
        if v is None:
            return v
        if v not in ROLES:
            raise ValueError(f"rollen '{v}' finns inte i {list(ROLES)}")
        return v


class AdminUserOut(BaseModel):
    """Admin representation on the wire — extends UserOut with email/is_active.

    Never includes password_hash.
    """

    id: int
    username: str
    role: str
    email: Optional[str] = None
    is_active: bool = True
    created_at: datetime
