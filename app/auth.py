"""Auth module — JWT helpers, password hashing, FastAPI role dependency (C4).

Near-verbatim reuse of bibliotek ``src/auth.py`` (I7 reuse rule); the only
deliberate differences from the reuse source are:

  * config imports come from ``app.config`` (affärssystemet) not ``src.config``
  * the ``ROLES`` tuple is declared here (closed set C-F) and matches the User
    model's ROLES in ``app/models/user.py`` exactly
  * a ``get_current_user`` dependency is added (verify-token only, NO role
    check) to back the public ``GET /api/auth/me`` endpoint (C6 requires "me"
    to be role-agnostic).

Functions:
    hash_password(password)      → bcrypt hash string
    check_password(password, h)  → bool
    create_access_token(id, role)→ signed JWT (expires ACCESS_TOKEN_EXPIRE_MINUTES)
    verify_token(token)          → dict(user_id, role) or None
    require_role(allowed)        → FastAPI dependency: 401 / 403 / payload
    get_current_user             → FastAPI dependency: 401 or payload (no role gate)
"""

from datetime import UTC, datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, JWT_ALGORITHM, SECRET_KEY

# C-F fixed point: the closed set of user roles. Same names the User model uses.
ROLES: tuple[str, ...] = ("admin", "sales", "finance", "procurement", "customer")

# ---------------------------------------------------------------------------
# Password hashing (bcrypt directly — avoids passlib 1.7 / bcrypt 5 compat)
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    """Return a ``$2b$...`` bcrypt hash of *password*."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    """Return True if *password* matches *hashed*."""
    return bcrypt.checkpw(
        password.encode("utf-8"), hashed.encode("utf-8")
    )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_access_token(user_id: int, role: str) -> str:
    """Create a signed JWT that expires after ACCESS_TOKEN_EXPIRE_MINUTES."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),       # subject = user id
        "role": role,
        "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        "iat": now,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """Decode and verify *token*; return {user_id, role} or None on failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return {
            "user_id": int(payload["sub"]),
            "role": payload["role"],
        }
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# FastAPI dependencies — role gate  +  verify-only (public "me")
# ---------------------------------------------------------------------------

_scheme = HTTPBearer(auto_error=False)


def require_role(allowed_roles: list[str]):
    """Return a FastAPI dependency rejecting requests whose JWT lacks one of
    *allowed_roles*.

    Usage::

        @router.get("/secret")
        def secret_view(current_user = require_role(["admin"])):
            ...

    Raises 401 when the token is missing/invalid/expired, 403 when the role is
    present but not in *allowed_roles*.
    """

    def _dep(credentials: HTTPAuthorizationCredentials = Depends(_scheme)) -> dict:
        """Inner dep — called by FastAPI for every protected route."""
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        user = verify_token(credentials.credentials)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _dep


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_scheme),
) -> dict:
    """FastAPI dependency verifying the Bearer JWT WITHOUT a role check.

    Used by the public ``GET /api/auth/me`` (C6: "verify_token only, no role
    requirement"). Raises 401 when the token is missing/invalid/expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = verify_token(credentials.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
