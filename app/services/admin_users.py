"""Admin-user service (MC 1120.1) — CRUD layer behind /api/admin/users.

Thin and consistent with the catalog/customer/supplier service style: each
function takes a Session and returns an ORM User (the router projects it onto
AdminUserOut). Only the [admin] role may reach these — enforced at the router
via require_role. Never returns a User's password_hash.
"""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import User


def get_user_or_404(db: Session, user_id: int) -> User:
    """Return the user with *user_id* or raise 404."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


def list_users(db: Session) -> list[User]:
    """Return all users ordered by username (stable admin list ordering)."""
    return db.query(User).order_by(User.username).all()


def create_user(db: Session, username: str, role: str, password: str, email: str | None) -> User:
    """Persist and return a new User, hashing *password* with the repo's hash_password."""
    user = User(
        username=username,
        password_hash=hash_password(password),  # never store the plaintext
        role=role,
        email=email,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user(
    db: Session,
    user_id: int,
    role: str | None = None,
    email: str | None = None,
    is_active: bool | None = None,
) -> User:
    """Apply the non-None AdminUserUpdate fields to the user with *user_id*."""
    user = get_user_or_404(db, user_id)
    if role is not None:
        user.role = role
    if email is not None:
        user.email = email
    if is_active is not None:
        user.is_active = is_active
    db.commit()
    db.refresh(user)
    return user
