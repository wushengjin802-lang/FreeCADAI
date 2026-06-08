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
from server.app.models.entities import AdminSession, AdminUser, ApiKey, Workspace


_admin_actor = ContextVar("admin_actor", default="admin")
_admin_principal = ContextVar("admin_principal", default={"id": None, "username": "admin", "role": "owner", "legacy": True})


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


def authenticate_plugin(db: Session = Depends(get_db), authorization: str = Header(default="")):
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
    api_key.last_used_at = datetime.utcnow()
    workspace = db.execute(select(Workspace).where(Workspace.id == api_key.workspace_id)).scalar_one_or_none()
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=403, detail="Workspace is not active.")
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
    if not settings.admin_token or not hmac.compare_digest(token, settings.admin_token):
        session = db.execute(
            select(AdminSession).where(
                AdminSession.token_hash == hash_api_key(token),
                AdminSession.status == "active",
                AdminSession.expires_at > datetime.utcnow(),
            )
        ).scalar_one_or_none()
        if session is None:
            raise HTTPException(status_code=403, detail="Invalid admin token.")
        user = db.get(AdminUser, session.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=403, detail="Admin user is not active.")
        principal = {"id": user.id, "username": user.username, "role": user.role, "legacy": False}
        _admin_actor.set(user.username)
        _admin_principal.set(principal)
        return principal
    principal = {"id": None, "username": "legacy-admin-token", "role": "owner", "legacy": True}
    _admin_actor.set("legacy-admin-token")
    _admin_principal.set(principal)
    return principal
