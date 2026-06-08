"""Plugin API key authentication."""

import hashlib
import hmac
from datetime import datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from server.app.core.config import settings
from server.app.db.session import get_db
from server.app.models.entities import ApiKey, Workspace


def hash_api_key(api_key):
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def _extract_bearer(authorization):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    return authorization.split(" ", 1)[1].strip()


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
