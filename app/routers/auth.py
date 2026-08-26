"""Auth router (C6).

    POST /api/auth/login   LoginRequest{username,password} -> TokenResponse
    GET  /api/auth/me      Bearer <jwt> -> UserOut   (verify_token only, no role)

Reused from bibliotek's auth router; adapted to the affärssystemet schema split
(LoginRequest/UserOut/TokenResponse live in app.schemas.auth) and to the "me"
endpoint contract (Bearer JWT, no role requirement).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import check_password, create_access_token, get_current_user
from app.database import get_session
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    body: LoginRequest,
    db: Session = Depends(get_session),
) -> TokenResponse:
    """Authenticate *username*/*password* against the User table.

    Returns a signed JWT (create_access_token) plus the UserOut. 401 on unknown
    username or wrong password; the caller can never distinguish which.
    """
    user = db.query(User).filter(User.username == body.username).first()
    if user is None or not check_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ogiltiga användaruppgifter",
        )
    token = create_access_token(user.id, user.role)
    return TokenResponse(
        access_token=token,
        user=UserOut(id=user.id, username=user.username, role=user.role),
    )


@router.get("/me", response_model=UserOut)
def me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> UserOut:
    """Return the authenticated user's public profile (verify only, no role)."""
    user = db.query(User).filter(User.id == current_user["user_id"]).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(id=user.id, username=user.username, role=user.role)
