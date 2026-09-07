"""Admin-users router (MC 1120.1) — HTTP surface for user-admin + roles.

    GET   /api/admin/users         -> list[AdminUserOut]   [admin]
    POST  /api/admin/users         AdminUserCreate -> AdminUserOut  [admin]
    GET   /api/admin/users/{id}    -> AdminUserOut        [admin]
    PATCH /api/admin/users/{id}    AdminUserUpdate -> AdminUserOut  [admin]

All routes are role-gated to [admin] (the only role allowed to manage
users). Returns schema objects (C23), never raw ORM, and never exposes
password_hash. Role values are validated against the closed ROLES set (C-F).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_session
from app.schemas.admin_user import AdminUserCreate, AdminUserOut, AdminUserUpdate

from app.services import admin_users as admin_users_service

router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])

ADMIN_ROLES = ["admin"]


@router.get("", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ADMIN_ROLES)),
) -> list[AdminUserOut]:
    return [
        AdminUserOut(**user_to_dict(u)) for u in admin_users_service.list_users(db)
    ]


@router.post("", response_model=AdminUserOut, status_code=200)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ADMIN_ROLES)),
) -> AdminUserOut:
    user = admin_users_service.create_user(
        db,
        username=body.username,
        role=body.role,
        password=body.password,
        email=body.email,
    )
    return AdminUserOut(**user_to_dict(user))


@router.get("/{user_id}", response_model=AdminUserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ADMIN_ROLES)),
) -> AdminUserOut:
    user = admin_users_service.get_user_or_404(db, user_id)
    return AdminUserOut(**user_to_dict(user))


@router.patch("/{user_id}", response_model=AdminUserOut)
def update_user(
    user_id: int,
    body: AdminUserUpdate,
    db: Session = Depends(get_session),
    _auth=Depends(require_role(ADMIN_ROLES)),
) -> AdminUserOut:
    user = admin_users_service.update_user(
        db,
        user_id=user_id,
        role=body.role,
        email=body.email,
        is_active=body.is_active,
    )
    return AdminUserOut(**user_to_dict(user))


def user_to_dict(u) -> dict:
    """Project an ORM User onto AdminUserOut (C23 — no bare ORM, no password_hash)."""
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "email": u.email,
        "is_active": u.is_active,
        "created_at": u.created_at,
    }
