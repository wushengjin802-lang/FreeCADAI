"""Plugin-facing API endpoints."""

import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from server.app.db.session import get_db
from server.app.models.entities import AdminSession, AdminUser, ApiKey, AuditLog, Template, User, UserSession, Workspace, WorkspaceMember
from server.app.models.entities import GeneratedScript, GenerationTask, ModelAsset, ScriptAsset
from server.app.schemas.plugin import (
    ExecutionReportRequest,
    ExecutionReportResponse,
    GenerateRequest,
    GenerationSubmitResponse,
    GenerationResponse,
    GenerationTaskStatusResponse,
    PluginAccountLoginRequest,
    PluginAccountLoginResponse,
    PluginBindWorkspaceRequest,
    PluginBindWorkspaceResponse,
    PluginTemplate,
    PluginTemplatesResponse,
    PluginWorkspaceItem,
    PluginWorkspacesResponse,
    RegenerateRequest,
    RepairRequest,
    TaskActionResponse,
    VerifyRequest,
    VerifyResponse,
)
from server.app.services.auth import authenticate_admin, authenticate_plugin, create_admin_session, create_user_session, current_plugin_api_key_user_id, hash_api_key, verify_password
from server.app.services.billing import assert_workspace_quota, record_usage
from server.app.services.default_templates import builtin_template_rows
from server.app.services.llm_orchestrator import generate_script, regenerate_script, repair_script
from server.app.services.assets import touch_asset
from server.app.services.model_storage import assert_allowed_file, model_asset_path, storage_uri_for, write_upload_file
from server.app.services.task_queue import enqueue_generation_task, load_generation_task_payload, retry_generation_task
from server.app.services.task_store import create_task, mark_task_failed, mark_task_success, save_execution_report


router = APIRouter(prefix="/api/v1/plugin", tags=["plugin"])


def _workspace_item(db: Session, workspace: Workspace):
    api_key_count = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == workspace.id)) or 0
    return PluginWorkspaceItem(
        id=workspace.id,
        name=workspace.name,
        plan=workspace.plan,
        status=workspace.status,
        api_key_count=api_key_count,
    )


def _extract_bearer(authorization: str):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    return authorization.split(" ", 1)[1].strip()


def _plugin_account_principal(db: Session, authorization: str):
    token_hash = hash_api_key(_extract_bearer(authorization))
    user_session = db.execute(
        select(UserSession).where(
            UserSession.token_hash == token_hash,
            UserSession.status == "active",
            UserSession.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if user_session is not None:
        user = db.get(User, user_session.user_id)
        if user is None or user.status != "active":
            raise HTTPException(status_code=403, detail="User is not active.")
        return {"kind": "user", "id": user.id, "username": user.email, "role": "user", "display_name": user.display_name}

    admin_session = db.execute(
        select(AdminSession).where(
            AdminSession.token_hash == token_hash,
            AdminSession.status == "active",
            AdminSession.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if admin_session is None:
        raise HTTPException(status_code=403, detail="Invalid account session.")
    admin = db.get(AdminUser, admin_session.user_id)
    if admin is None or admin.status != "active":
        raise HTTPException(status_code=403, detail="Admin user is not active.")
    return {"kind": "admin", "id": admin.id, "username": admin.username, "role": admin.role}


@router.get("/health")
def health():
    return {"ok": True, "service": "FreeCADAI SaaS"}


@router.post("/auth/verify", response_model=VerifyResponse)
def verify_plugin(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return VerifyResponse(
        ok=True,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_plan=workspace.plan,
        workspace_status=workspace.status,
        key_status="active",
        message="Plugin API Key is valid.",
    )


@router.post("/account/login", response_model=PluginAccountLoginResponse)
def plugin_account_login(payload: PluginAccountLoginRequest, db: Session = Depends(get_db)):
    email = payload.username.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is not None:
        if user.status != "active" or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=403, detail="Invalid username or password.")
        raw_token, session = create_user_session(db, user)
        db.add(
            AuditLog(
                actor="user:{}".format(user.id),
                action="plugin.account.login",
                target_type="user",
                target_id=str(user.id),
                metadata_json={"source": "freecad_plugin", "email": user.email},
            )
        )
        db.commit()
        return PluginAccountLoginResponse(
            token=raw_token,
            expires_at=session.expires_at.isoformat(timespec="seconds"),
            user={"id": user.id, "username": user.email, "display_name": user.display_name, "role": "user", "status": user.status, "kind": "user"},
        )

    admin_user = db.execute(select(AdminUser).where(AdminUser.username == payload.username)).scalar_one_or_none()
    if admin_user is None or admin_user.status != "active" or not verify_password(payload.password, admin_user.password_hash):
        raise HTTPException(status_code=403, detail="Invalid username or password.")
    raw_token, session = create_admin_session(db, admin_user)
    db.add(
        AuditLog(
            actor=admin_user.username,
            action="plugin.account.login",
            target_type="admin_user",
            target_id=str(admin_user.id),
            metadata_json={"source": "freecad_plugin", "compat": True},
        )
    )
    db.commit()
    return PluginAccountLoginResponse(
        token=raw_token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user={"id": admin_user.id, "username": admin_user.username, "role": admin_user.role, "status": admin_user.status, "kind": "admin"},
    )


@router.get("/account/workspaces", response_model=PluginWorkspacesResponse)
def plugin_account_workspaces(
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    principal = _plugin_account_principal(db, authorization)
    if principal["kind"] == "user":
        rows = db.execute(
            select(Workspace)
            .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
            .where(
                WorkspaceMember.user_id == principal["id"],
                WorkspaceMember.status == "active",
                Workspace.status == "active",
            )
            .order_by(Workspace.id)
        ).scalars().all()
        return PluginWorkspacesResponse(workspaces=[_workspace_item(db, row) for row in rows])

    if principal.get("role") not in {"owner", "operator", "viewer"}:
        raise HTTPException(status_code=403, detail="Permission denied.")
    rows = db.execute(select(Workspace).order_by(Workspace.id)).scalars().all()
    return PluginWorkspacesResponse(workspaces=[_workspace_item(db, row) for row in rows])


@router.post("/account/bind-workspace", response_model=PluginBindWorkspaceResponse)
def plugin_account_bind_workspace(
    payload: PluginBindWorkspaceRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    principal = _plugin_account_principal(db, authorization)
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=404, detail="Workspace is not active.")
    actor = principal.get("username", "account")
    created_by_user_id = None
    if principal["kind"] == "user":
        membership = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == principal["id"],
                WorkspaceMember.status == "active",
            )
        ).scalar_one_or_none()
        if membership is None or membership.role not in {"owner", "admin"}:
            raise HTTPException(status_code=403, detail="Permission denied.")
        actor = "user:{}".format(principal["id"])
        created_by_user_id = principal["id"]
    elif principal.get("role") not in {"owner", "operator"}:
        raise HTTPException(status_code=403, detail="Permission denied.")

    assert_workspace_quota(db, workspace, "api_keys")
    raw_key = "fcai_" + secrets.token_urlsafe(32)
    prefix = raw_key[:12]
    item = ApiKey(
        workspace_id=workspace.id,
        name=payload.key_name,
        key_hash=hash_api_key(raw_key),
        prefix=prefix,
        status="active",
        created_by_user_id=created_by_user_id,
        scopes_json=["plugin"],
    )
    db.add(item)
    db.add(
        AuditLog(
            actor=actor,
            action="plugin.workspace.bind",
            target_type="workspace",
            target_id=str(workspace.id),
            workspace_id=workspace.id,
            metadata_json={"key_name": payload.key_name, "prefix": prefix, "account_kind": principal["kind"]},
        )
    )
    db.commit()
    return PluginBindWorkspaceResponse(api_key=raw_key, prefix=prefix, workspace=_workspace_item(db, workspace))


@router.get("/templates", response_model=PluginTemplatesResponse)
def plugin_templates(
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    rows = db.execute(
        select(Template)
        .where(
            Template.enabled.is_(True),
            or_(Template.workspace_id.is_(None), Template.workspace_id == workspace.id),
        )
        .order_by(Template.category, Template.name)
    ).scalars().all()
    if rows:
        return PluginTemplatesResponse(
            templates=[
                PluginTemplate(id=str(row.id), name=row.name, category=row.category, prompt=row.prompt)
                for row in rows
            ]
        )
    return PluginTemplatesResponse(
        templates=[
            PluginTemplate(
                id="builtin-{}".format(index),
                name=item["name"],
                category=item["category"],
                prompt=item["prompt"],
            )
            for index, item in enumerate(builtin_template_rows(), start=1)
        ]
    )


def _status_payload(db: Session, task: GenerationTask):
    script = db.execute(select(GeneratedScript).where(GeneratedScript.task_id == task.id)).scalars().first()
    return GenerationTaskStatusResponse(
        task_id=task.id,
        status=task.status,
        action=task.action,
        error_message=task.error_message,
        latency_ms=task.latency_ms,
        script_id=script.id if script else None,
        summary=script.summary if script else "",
        parameters=script.parameters_json if script else {},
        script=script.script if script else "",
        expected_objects=script.expected_objects_json if script else [],
        notes=[],
    )


def _require_workspace_task(db: Session, workspace: Workspace, task_id: int):
    task = db.get(GenerationTask, task_id)
    if task is None or task.workspace_id != workspace.id:
        raise HTTPException(status_code=404, detail="Task not found.")
    return task


def _account_token_user_id(db: Session, workspace: Workspace, account_token: str):
    token = (account_token or "").strip()
    if not token:
        return None
    session = db.execute(
        select(UserSession).where(
            UserSession.token_hash == hash_api_key(token),
            UserSession.status == "active",
            UserSession.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if session is None:
        return None
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        return None
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == "active",
        )
    ).scalar_one_or_none()
    return user.id if member is not None else None


def _request_created_by_user_id(db: Session, workspace: Workspace, request):
    account_user_id = _account_token_user_id(db, workspace, getattr(request, "account_token", ""))
    return account_user_id if account_user_id is not None else current_plugin_api_key_user_id()


def _submit_generation(db: Session, workspace: Workspace, action: str, request, extra=None, created_by_user_id=None):
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    task = create_task(
        db,
        workspace,
        action,
        request.prompt,
        request.context,
        request.modeling_mode,
        request.project_id,
        status="queued",
        created_by_user_id=created_by_user_id,
    )
    payload = {
        "action": action,
        "prompt": request.prompt,
        "context": request.context,
        "modeling_mode": request.modeling_mode,
        "project_id": request.project_id,
    }
    if extra:
        payload.update(extra)
    enqueue_generation_task(task.id, payload)
    return GenerationSubmitResponse(task_id=task.id, status=task.status, message="任务已进入队列。")


def _run_generation(db, workspace, action, request, callback, created_by_user_id=None):
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    task = create_task(
        db,
        workspace,
        action,
        request.prompt,
        request.context,
        request.modeling_mode,
        request.project_id,
        created_by_user_id=created_by_user_id,
    )
    started = time.time()
    try:
        payload = callback()
        latency_ms = int((time.time() - started) * 1000)
        script = mark_task_success(db, task, payload, latency_ms)
        record_usage(db, workspace, task, payload.get("_usage"))
        payload["task_id"] = task.id
        payload["script_id"] = script.id
        return GenerationResponse(**payload)
    except Exception as exc:
        latency_ms = int((time.time() - started) * 1000)
        mark_task_failed(db, task, exc, latency_ms)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate/submit", response_model=GenerationSubmitResponse)
def submit_generate(
    request: GenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _submit_generation(db, workspace, "generate", request, created_by_user_id=_request_created_by_user_id(db, workspace, request))


@router.post("/repair/submit", response_model=GenerationSubmitResponse)
def submit_repair(
    request: RepairRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _submit_generation(
        db,
        workspace,
        "repair",
        request,
        {"failed_script": request.failed_script, "error_text": request.error_text},
        created_by_user_id=_request_created_by_user_id(db, workspace, request),
    )


@router.post("/regenerate/submit", response_model=GenerationSubmitResponse)
def submit_regenerate(
    request: RegenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _submit_generation(db, workspace, "regenerate", request, {"parameters": request.parameters}, created_by_user_id=_request_created_by_user_id(db, workspace, request))


@router.get("/tasks/{task_id}", response_model=GenerationTaskStatusResponse)
def task_status(
    task_id: int,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    task = _require_workspace_task(db, workspace, task_id)
    return _status_payload(db, task)


@router.post("/model-assets/upload")
def upload_model_asset_from_plugin(
    task_id: int | None = Form(None),
    script_asset_id: int | None = Form(None),
    project_id: str = Form(""),
    name: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    ext = assert_allowed_file(file.filename or "")
    task = None
    if task_id:
        task = _require_workspace_task(db, workspace, task_id)
    if script_asset_id:
        script_asset = db.get(ScriptAsset, script_asset_id)
        if script_asset is None or script_asset.workspace_id != workspace.id:
            raise HTTPException(status_code=404, detail="Script asset not found.")
    item = ModelAsset(
        workspace_id=workspace.id,
        script_asset_id=script_asset_id,
        task_id=task_id,
        project_id=project_id or (task.project_id if task else ""),
        name=(name or file.filename or "Plugin model asset")[:128],
        file_name=file.filename or "model{}".format(ext),
        file_type=ext.lstrip(".").upper(),
        storage_uri="",
        preview_uri="",
        checksum="",
        size_bytes=0,
        status="active",
        metadata_json={"uploaded_by": "plugin", "source": "plugin"},
    )
    db.add(item)
    db.flush()
    target = model_asset_path(workspace.id, item.id, item.file_name)
    size_bytes, checksum = write_upload_file(file, target)
    item.size_bytes = size_bytes
    item.checksum = checksum
    item.storage_uri = storage_uri_for(workspace.id, item.id, item.file_name)
    item.preview_uri = "/api/v1/console/model-assets/{}/preview".format(item.id) if ext == ".stl" else ""
    touch_asset(item)
    db.add(
        AuditLog(
            actor="plugin",
            action="plugin.model_asset.upload",
            target_type="model_asset",
            target_id=str(item.id),
            workspace_id=workspace.id,
            metadata_json={"file_name": item.file_name, "size_bytes": size_bytes, "task_id": task_id, "script_asset_id": script_asset_id},
        )
    )
    db.commit()
    db.refresh(item)
    return {
        "ok": True,
        "asset_id": item.id,
        "workspace_id": item.workspace_id,
        "task_id": item.task_id,
        "script_asset_id": item.script_asset_id,
        "file_name": item.file_name,
        "file_type": item.file_type,
        "storage_uri": item.storage_uri,
        "preview_uri": item.preview_uri,
        "checksum": item.checksum,
        "size_bytes": item.size_bytes,
    }


@router.post("/tasks/{task_id}/cancel", response_model=TaskActionResponse)
def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    task = _require_workspace_task(db, workspace, task_id)
    if task.status not in {"queued", "running"}:
        return TaskActionResponse(ok=False, task_id=task.id, status=task.status, message="当前任务状态不可取消。")
    task.status = "canceled"
    task.error_message = "用户已取消任务。"
    db.commit()
    return TaskActionResponse(ok=True, task_id=task.id, status=task.status, message="任务已取消。")


@router.post("/tasks/{task_id}/retry", response_model=TaskActionResponse)
def retry_task(
    task_id: int,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    task = _require_workspace_task(db, workspace, task_id)
    if task.status not in {"failed", "canceled"}:
        return TaskActionResponse(ok=False, task_id=task.id, status=task.status, message="只有失败或已取消任务可以重试。")
    if load_generation_task_payload(task.id) is None:
        raise HTTPException(status_code=409, detail="任务请求内容已不存在，无法重试。")
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    task.status = "queued"
    task.error_message = ""
    db.commit()
    retry_generation_task(task.id)
    return TaskActionResponse(ok=True, task_id=task.id, status=task.status, message="任务已重新入队。")


@router.post("/generate", response_model=GenerationResponse)
def generate(
    request: GenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "generate",
        request,
        lambda: generate_script(request.prompt, request.context, request.modeling_mode),
        created_by_user_id=_request_created_by_user_id(db, workspace, request),
    )


@router.post("/repair", response_model=GenerationResponse)
def repair(
    request: RepairRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "repair",
        request,
        lambda: repair_script(
            request.prompt,
            request.context,
            request.failed_script,
            request.error_text,
            request.modeling_mode,
        ),
        created_by_user_id=_request_created_by_user_id(db, workspace, request),
    )


@router.post("/regenerate", response_model=GenerationResponse)
def regenerate(
    request: RegenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "regenerate",
        request,
        lambda: regenerate_script(
            request.prompt,
            request.context,
            request.parameters,
            request.modeling_mode,
        ),
        created_by_user_id=_request_created_by_user_id(db, workspace, request),
    )


@router.post("/execution-reports", response_model=ExecutionReportResponse)
def execution_report(
    request: ExecutionReportRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    item = save_execution_report(db, request)
    return ExecutionReportResponse(ok=True, report_id=item.id)
