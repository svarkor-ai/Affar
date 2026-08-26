"""Auth wire schemas (C6). One Pydantic model set for the auth aggregate.

C23 rule: routers return schema objects, never raw ORM objects. No money fields
on the auth wire, so no Decimal constraints are needed here.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """POST /api/auth/login body."""

    username: str
    password: str


class UserOut(BaseModel):
    """Public user representation (never exposes password_hash)."""

    id: int
    username: str
    role: str


class TokenResponse(BaseModel):
    """Successful login: signed JWT plus the authenticated user."""

    access_token: str
    user: UserOut
