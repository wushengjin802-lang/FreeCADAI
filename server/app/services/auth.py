"""Plugin API key authentication."""

import hashlib
import hmac
import secrets
from contextvars import ContextVar
from datetime import datetime, timedelta

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.core.config import settings
from server.app.db.session import get_db
from server.app.models.entities import AdminSession, AdminUser, ApiKey, User, UserSession, Workspace, WorkspaceMember


_admin_actor = ContextVar("admin_actor", default="admin")
_admin_principal = ContextVar("admin_principal", default={"id": None, "username": "admin", "role": "viewer"})
_user_actor = ContextVar("user_actor", default="user:anonymous")
_user_principal = ContextVar("user_principal", default={"id": None, "email": "", "display_name": "", "status": "anonymous"})
_plugin_api_key_user_id = ContextVar("plugin_api_key_user_id", default=None)


def hash_api_key(api_key):
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000)
    return "pbkdf2_sha256${}${}".format(salt, digest.hex())


def verify_password(password, password_hash):
    try:
        method, salt, expected = password_hash.split("$", 2)
    except ValueError:
        return False
    if method != "pbkdf2_sha256":
        return False
    actual = hash_password(password, salt).split("$", 2)[2]
    return hmac.compare_digest(actual, expected)


def _extract_bearer(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    return authorization.split(" ", 1)[1].strip()


def current_admin_actor():
    return _admin_actor.get()


def current_admin_principal():
    return _admin_principal.get()


def current_user_actor():
    return _user_actor.get()


def current_user_principal():
    return _user_principal.get()


def current_plugin_api_key_user_id():
    return _plugin_api_key_user_id.get()


def _fallback_workspace_user_id(db: Session, workspace_id: int):
    member = db.execute(
        select(WorkspaceMember)
        .where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.status == "active",
            WorkspaceMember.role.in_(("owner", "admin")),
        )
        .order_by(WorkspaceMember.role.desc(), WorkspaceMember.id.asc())
    ).scalar_one_or_none()
    if member is not None:
        return member.user_id
    member = db.execute(
        select(WorkspaceMember)
        .where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.status == "active")
        .order_by(WorkspaceMember.id.asc())
    ).scalar_one_or_none()
    return member.user_id if member is not None else None


def authenticate_plugin(db: Session = Depends(get_db), authorization: str = Header(default="")):
    _plugin_api_key_user_id.set(None)
    token = _extract_bearer(authorization)
    if settings.plugin_api_key and hmac.compare_digest(token, settings.plugin_api_key):
        workspace = db.execute(select(Workspace).where(Workspace.id == 1)).scalar_one_or_none()
        if workspace is None:
            workspace = Workspace(id=1, name="Default Workspace")
            db.add(workspace)
            db.commit()
        return workspace

    key_hash = hash_api_key(token)
    api_key = db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.status == "active")
    ).scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=403, detail="Invalid plugin API key.")
    if api_key.expires_at is not None and api_key.expires_at <= datetime.utcnow():
        api_key.status = "expired"
        db.commit()
        raise HTTPException(status_code=403, detail="Plugin API key has expired.")
    api_key.last_used_at = datetime.utcnow()
    workspace = db.execute(select(Workspace).where(Workspace.id == api_key.workspace_id)).scalar_one_or_none()
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=403, detail="Workspace is not active.")
    if api_key.created_by_user_id is None:
        api_key.created_by_user_id = _fallback_workspace_user_id(db, workspace.id)
    _plugin_api_key_user_id.set(api_key.created_by_user_id)
    db.commit()
    return workspace


def create_admin_session(db: Session, user: AdminUser):
    raw_token = "fcai_admin_" + secrets.token_urlsafe(36)
    item = AdminSession(
        user_id=user.id,
        token_hash=hash_api_key(raw_token),
        expires_at=datetime.utcnow() + timedelta(hours=settings.admin_session_hours),
    )
    user.last_login_at = datetime.utcnow()
    db.add(item)
    db.commit()
    db.refresh(item)
    return raw_token, item


def create_user_session(db: Session, user: User):
    raw_token = "fcai_user_" + secrets.token_urlsafe(36)
    item = UserSession(
        user_id=user.id,
        token_hash=hash_api_key(raw_token),
        expires_at=datetime.utcnow() + timedelta(hours=settings.user_session_hours),
    )
    user.last_login_at = datetime.utcnow()
    user.updated_at = datetime.utcnow()
    db.add(item)
    db.commit()
    db.refresh(item)
    return raw_token, item


def ensure_default_admin(db: Session):
    exists = db.scalar(select(AdminUser.id).limit(1))
    if exists or not settings.admin_username or not settings.admin_password:
        return None
    item = AdminUser(
        username=settings.admin_username,
        password_hash=hash_password(settings.admin_password),
        role="owner",
        status="active",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def authenticate_admin(db: Session = Depends(get_db), authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    session = db.execute(
        select(AdminSession).where(
            AdminSession.token_hash == hash_api_key(token),
            AdminSession.status == "active",
            AdminSession.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=403, detail="Invalid admin session.")
    user = db.get(AdminUser, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=403, detail="Admin user is not active.")
    principal = {"id": user.id, "username": user.username, "role": user.role}
    _admin_actor.set(user.username)
    _admin_principal.set(principal)
    return principal


def authenticate_user(db: Session = Depends(get_db), authorization: str = Header(default="")):
    token = _extract_bearer(authorization)
    session = db.execute(
        select(UserSession).where(
            UserSession.token_hash == hash_api_key(token),
            UserSession.status == "active",
            UserSession.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=403, detail="Invalid user session.")
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=403, detail="User is not active.")
    principal = {"id": user.id, "email": user.email, "display_name": user.display_name, "status": user.status}
    _user_actor.set("user:{}".format(user.id))
    _user_principal.set(principal)
    return principal


def require_workspace_member(
    db: Session,
    user_id: int,
    workspace_id: int,
    allowed_roles: set[str] | None = None,
):
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == "active",
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if allowed_roles is not None and member.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Permission denied.")
    workspace = db.get(Workspace, workspace_id)
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace, member
