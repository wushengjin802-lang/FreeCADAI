"""Local storage helpers for model assets."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException, UploadFile

from server.app.core.config import settings


def allowed_extensions() -> list[str]:
    return [item.strip().lower() for item in settings.model_asset_allowed_extensions.split(",") if item.strip()]


def max_upload_bytes() -> int:
    return settings.model_asset_max_upload_mb * 1024 * 1024


def storage_root() -> Path:
    root = Path(settings.model_asset_storage_dir)
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_filename(filename: str) -> str:
    value = Path(filename or "model.stl").name
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value or "model.stl"


def file_extension(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def assert_allowed_file(filename: str, size_bytes: int | None = None) -> str:
    ext = file_extension(filename)
    if ext not in allowed_extensions():
        raise HTTPException(status_code=422, detail="Unsupported model file type.")
    if size_bytes is not None and size_bytes > max_upload_bytes():
        raise HTTPException(status_code=413, detail="Model file is too large.")
    return ext


def _secret() -> bytes:
    seed = settings.plugin_api_key or settings.admin_password or settings.database_url
    return seed.encode("utf-8")


def sign_upload_token(workspace_id: int, file_name: str, size_bytes: int = 0) -> str:
    expires_at = datetime.utcnow() + timedelta(minutes=settings.model_asset_upload_token_minutes)
    payload = {
        "workspace_id": workspace_id,
        "file_name": safe_filename(file_name),
        "size_bytes": int(size_bytes or 0),
        "expires_at": expires_at.isoformat(timespec="seconds"),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    envelope = {"payload": payload, "signature": signature}
    return base64.urlsafe_b64encode(json.dumps(envelope, separators=(",", ":")).encode("utf-8")).decode("ascii")


def verify_upload_token(token: str, workspace_id: int, file_name: str) -> dict:
    try:
        envelope = json.loads(base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8"))
        payload = envelope["payload"]
        signature = envelope["signature"]
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid upload token.") from exc
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    expected = hmac.new(_secret(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid upload token.")
    if int(payload.get("workspace_id") or 0) != workspace_id:
        raise HTTPException(status_code=403, detail="Upload token workspace mismatch.")
    if safe_filename(payload.get("file_name", "")) != safe_filename(file_name):
        raise HTTPException(status_code=403, detail="Upload token file mismatch.")
    expires_at = datetime.fromisoformat(payload["expires_at"])
    if expires_at < datetime.utcnow():
        raise HTTPException(status_code=403, detail="Upload token has expired.")
    assert_allowed_file(file_name, int(payload.get("size_bytes") or 0) or None)
    return payload


def model_asset_path(workspace_id: int, asset_id: int, filename: str) -> Path:
    target_dir = storage_root() / str(workspace_id) / str(asset_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / safe_filename(filename)


def write_upload_file(file: UploadFile, target: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_upload_bytes():
                output.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Model file is too large.")
            hasher.update(chunk)
            output.write(chunk)
    return size, hasher.hexdigest()


def write_binary_stream(stream: BinaryIO, target: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    size = 0
    with target.open("wb") as output:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > max_upload_bytes():
                output.close()
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Model file is too large.")
            hasher.update(chunk)
            output.write(chunk)
    return size, hasher.hexdigest()


def storage_uri_for(workspace_id: int, asset_id: int, filename: str) -> str:
    return "local://model-assets/{}/{}/{}".format(workspace_id, asset_id, safe_filename(filename))


def resolve_storage_uri(uri: str) -> Path:
    prefix = "local://model-assets/"
    if not uri.startswith(prefix):
        raise HTTPException(status_code=404, detail="Model file is not stored locally.")
    relative = uri[len(prefix):]
    path = (storage_root() / relative).resolve()
    root = storage_root().resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=403, detail="Invalid model storage path.")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Model file not found.")
    return path


def delete_asset_files(workspace_id: int, asset_id: int):
    target = storage_root() / str(workspace_id) / str(asset_id)
    if target.exists():
        shutil.rmtree(target)
