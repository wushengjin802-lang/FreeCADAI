"""Admin management API for phase 5+."""

import csv
import io
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from server.app.db.session import get_db
from server.app.models.entities import (
    AdminSession,
    AdminUser,
    AuditLog,
    ApiKey,
    ExecutionReport,
    GeneratedScript,
    GenerationTask,
    ModelAsset,
    ScriptAsset,
    ScriptVersion,
    Template,
    UsageRecord,
    Workspace,
)
from server.app.schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminPasswordChange,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    AuditLogOut,
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyOut,
    BillingPlanOut,
    BillingSummaryOut,
    ModelAssetCreate,
    ModelAssetOut,
    ModelAssetUpdate,
    PaymentCheckoutRequest,
    PaymentCheckoutResponse,
    ScriptAssetOut,
    ScriptAssetUpdate,
    ScriptReuseTemplateRequest,
    ScriptRollbackRequest,
    ScriptVersionOut,
    TaskDetail,
    TaskListItem,
    TemplateCreate,
    TemplateImportRequest,
    TemplateOut,
    TemplateUpdate,
    UsageByModelItem,
    UsageDailyItem,
    UsageSummary,
    WorkspaceCreate,
    WorkspaceOut,
    WorkspaceUpdate,
)
from server.app.services.auth import (
    authenticate_admin,
    create_admin_session,
    current_admin_actor,
    current_admin_principal,
    hash_api_key,
    hash_password,
    verify_password,
)
from server.app.services.assets import copy_script_asset, current_script_version, touch_asset
from server.app.services.billing import assert_workspace_quota, billing_plans, quota_summary
from server.app.services.default_templates import ensure_default_templates
from server.app.services.task_queue import load_generation_task_payload, retry_generation_task


auth_router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin-auth"])
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(authenticate_admin)])
billing_router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


def _admin_user_out(row: AdminUser):
    return AdminUserOut(
        id=row.id,
        username=row.username,
        role=row.role,
        status=row.status,
        last_login_at=row.last_login_at.isoformat(timespec="seconds") if row.last_login_at else None,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _template_out(row: Template):
    return TemplateOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        category=row.category,
        prompt=row.prompt,
        enabled=row.enabled,
    )


def _script_version_out(row: ScriptVersion):
    return ScriptVersionOut(
        id=row.id,
        asset_id=row.asset_id,
        task_id=row.task_id,
        version=row.version,
        script=row.script,
        summary=row.summary,
        parameters=row.parameters_json,
        expected_objects=row.expected_objects_json,
        validation_status=row.validation_status,
        validation_error=row.validation_error,
        created_by=row.created_by,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _script_asset_out(db: Session, row: ScriptAsset):
    version = current_script_version(db, row)
    workspace = db.get(Workspace, row.workspace_id)
    return ScriptAssetOut(
        id=row.id,
        workspace_id=row.workspace_id,
        workspace_name=workspace.name if workspace else "",
        task_id=row.task_id,
        current_version_id=row.current_version_id,
        current_version=version.version if version else None,
        name=row.name,
        description=row.description,
        modeling_mode=row.modeling_mode,
        project_id=row.project_id,
        source=row.source,
        favorite=row.favorite,
        status=row.status,
        tags=row.tags_json,
        metadata=row.metadata_json,
        summary=version.summary if version else "",
        script_preview=(version.script[:240] if version else ""),
        created_at=row.created_at.isoformat(timespec="seconds"),
        updated_at=row.updated_at.isoformat(timespec="seconds"),
    )


def _model_asset_out(row: ModelAsset):
    return ModelAssetOut(
        id=row.id,
        workspace_id=row.workspace_id,
        script_asset_id=row.script_asset_id,
        task_id=row.task_id,
        project_id=row.project_id,
        name=row.name,
        file_name=row.file_name,
        file_type=row.file_type,
        storage_uri=row.storage_uri,
        preview_uri=row.preview_uri,
        checksum=row.checksum,
        size_bytes=row.size_bytes,
        status=row.status,
        metadata=row.metadata_json,
        created_at=row.created_at.isoformat(timespec="seconds"),
        updated_at=row.updated_at.isoformat(timespec="seconds"),
    )


def _api_key_out(row: ApiKey):
    return ApiKeyOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        prefix=row.prefix,
        status=row.status,
        last_used_at=row.last_used_at.isoformat(timespec="seconds") if row.last_used_at else None,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _workspace_out(db: Session, row: Workspace):
    api_key_count = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == row.id)) or 0
    task_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == row.id)) or 0
    return WorkspaceOut(
        id=row.id,
        name=row.name,
        plan=row.plan,
        status=row.status,
        created_at=row.created_at.isoformat(timespec="seconds"),
        api_key_count=api_key_count,
        task_count=task_count,
        quota=quota_summary(db, row),
    )


def _audit(db: Session, action: str, target_type: str, target_id="", workspace_id=None, metadata=None):
    db.add(
        AuditLog(
            actor=current_admin_actor(),
            action=action,
            target_type=target_type,
            target_id=str(target_id or ""),
            workspace_id=workspace_id,
            metadata_json=metadata or {},
        )
    )


def _require_role(
    db: Session,
    allowed_roles: set[str],
    action: str,
    target_type: str = "admin_api",
    authorization: str = "",
):
    principal = authenticate_admin(db=db, authorization=authorization) if authorization else current_admin_principal()
    role = principal.get("role", "")
    if role not in allowed_roles:
        db.add(
            AuditLog(
                actor=current_admin_actor(),
                action="permission.denied",
                target_type=target_type,
                target_id=action,
                metadata_json={"required": sorted(allowed_roles), "actual": role},
            )
        )
        db.commit()
        raise HTTPException(status_code=403, detail="Permission denied.")
    return principal


@auth_router.post("/login", response_model=AdminLoginResponse)
def login(payload: AdminLoginRequest, db: Session = Depends(get_db)):
    user = db.execute(select(AdminUser).where(AdminUser.username == payload.username)).scalar_one_or_none()
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Invalid username or password.")
    raw_token, session = create_admin_session(db, user)
    db.add(
        AuditLog(
            actor=user.username,
            action="admin.login",
            target_type="admin_user",
            target_id=str(user.id),
            metadata_json={"username": user.username},
        )
    )
    db.commit()
    return AdminLoginResponse(
        token=raw_token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user={"id": user.id, "username": user.username, "role": user.role, "status": user.status},
    )


@router.get("/auth/me")
def me(admin=Depends(authenticate_admin)):
    return admin


@router.put("/auth/password")
def change_own_password(payload: AdminPasswordChange, db: Session = Depends(get_db), authorization: str = Header(default="")):
    principal = _require_role(db, {"owner", "operator", "viewer"}, "admin.password.change", authorization=authorization)
    user = db.get(AdminUser, principal["id"])
    if user is None or not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    user.password_hash = hash_password(payload.new_password)
    _audit(db, "admin.password.change", "admin_user", user.id, metadata={"username": user.username})
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def logout(db: Session = Depends(get_db), authorization: str = Header(default="")):
    # FastAPI already authenticated the request through the router dependency.
    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else ""
    if token:
        session = db.execute(select(AdminSession).where(AdminSession.token_hash == hash_api_key(token))).scalar_one_or_none()
        if session is not None:
            session.status = "revoked"
            _audit(db, "admin.logout", "admin_session", session.id, metadata={"user_id": session.user_id})
            db.commit()
    return {"ok": True}


@router.get("/admin-users", response_model=list[AdminUserOut])
def list_admin_users(db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner"}, "admin_users.list", "admin_user", authorization)
    rows = db.execute(select(AdminUser).order_by(AdminUser.id)).scalars().all()
    return [_admin_user_out(row) for row in rows]


@router.post("/admin-users", response_model=AdminUserOut)
def create_admin_user(payload: AdminUserCreate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner"}, "admin_users.create", "admin_user", authorization)
    exists = db.execute(select(AdminUser).where(AdminUser.username == payload.username)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Admin username already exists.")
    item = AdminUser(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        status=payload.status,
    )
    db.add(item)
    db.flush()
    _audit(db, "admin_user.create", "admin_user", item.id, metadata={"username": item.username, "role": item.role})
    db.commit()
    db.refresh(item)
    return _admin_user_out(item)


@router.put("/admin-users/{user_id}", response_model=AdminUserOut)
def update_admin_user(user_id: int, payload: AdminUserUpdate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner"}, "admin_users.update", "admin_user", authorization)
    item = db.get(AdminUser, user_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Admin user not found.")
    changed = payload.model_dump(exclude_none=True)
    if payload.role is not None:
        item.role = payload.role
    if payload.status is not None:
        item.status = payload.status
    if payload.password is not None:
        item.password_hash = hash_password(payload.password)
        changed["password"] = "updated"
    _audit(db, "admin_user.update", "admin_user", item.id, metadata={"username": item.username, **changed})
    db.commit()
    db.refresh(item)
    return _admin_user_out(item)


@router.get("/workspaces", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_db)):
    rows = db.execute(select(Workspace).order_by(Workspace.id)).scalars().all()
    return [_workspace_out(db, row) for row in rows]


@router.post("/workspaces", response_model=WorkspaceOut)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "workspaces.create", "workspace", authorization)
    item = Workspace(name=payload.name, plan=payload.plan, status=payload.status)
    db.add(item)
    db.flush()
    _audit(db, "workspace.create", "workspace", item.id, item.id, {"name": item.name, "plan": item.plan, "status": item.status})
    db.commit()
    db.refresh(item)
    return _workspace_out(db, item)


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: int, payload: WorkspaceUpdate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "workspaces.update", "workspace", authorization)
    item = db.get(Workspace, workspace_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    changed = {}
    for field in ("name", "plan", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
            changed[field] = value
    _audit(db, "workspace.update", "workspace", item.id, item.id, changed)
    db.commit()
    db.refresh(item)
    return _workspace_out(db, item)


@router.get("/tasks", response_model=list[TaskListItem])
def list_tasks(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str = "",
    action: str = "",
    modeling_mode: str = "",
    q: str = "",
    workspace_id: int | None = None,
):
    stmt = select(GenerationTask)
    if workspace_id is not None:
        stmt = stmt.where(GenerationTask.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(GenerationTask.status == status)
    if action:
        stmt = stmt.where(GenerationTask.action == action)
    if modeling_mode:
        stmt = stmt.where(GenerationTask.modeling_mode == modeling_mode)
    if q:
        like = "%{}%".format(q.strip())
        stmt = stmt.where(
            or_(
                GenerationTask.prompt.ilike(like),
                GenerationTask.project_id.ilike(like),
                GenerationTask.model.ilike(like),
                GenerationTask.error_message.ilike(like),
            )
        )
    stmt = stmt.order_by(desc(GenerationTask.id)).offset(offset).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        TaskListItem(
            id=row.id,
            workspace_id=row.workspace_id,
            project_id=row.project_id,
            action=row.action,
            modeling_mode=row.modeling_mode,
            prompt=row.prompt,
            model=row.model,
            status=row.status,
            latency_ms=row.latency_ms,
            created_at=row.created_at.isoformat(timespec="seconds"),
        )
        for row in rows
    ]


@router.get("/tasks/export")
def export_tasks(
    db: Session = Depends(get_db),
    limit: int = Query(default=1000, ge=1, le=5000),
    status: str = "",
    action: str = "",
    modeling_mode: str = "",
    q: str = "",
    workspace_id: int | None = None,
):
    rows = list_tasks(
        db=db,
        limit=limit,
        offset=0,
        status=status,
        action=action,
        modeling_mode=modeling_mode,
        q=q,
        workspace_id=workspace_id,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "workspace_id", "project_id", "action", "mode", "model", "status", "latency_ms", "created_at", "prompt"])
    for row in rows:
        writer.writerow(
            [
                row.id,
                row.workspace_id,
                row.project_id,
                row.action,
                row.modeling_mode,
                row.model,
                row.status,
                row.latency_ms,
                row.created_at,
                row.prompt,
            ]
        )
    return Response(
        content="\ufeff" + buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="freecadai_tasks.csv"'},
    )


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def task_detail(task_id: int, db: Session = Depends(get_db)):
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    scripts = db.execute(select(GeneratedScript).where(GeneratedScript.task_id == task_id)).scalars().all()
    reports = db.execute(select(ExecutionReport).where(ExecutionReport.task_id == task_id)).scalars().all()
    return TaskDetail(
        task={
            "id": task.id,
            "workspace_id": task.workspace_id,
            "project_id": task.project_id,
            "action": task.action,
            "modeling_mode": task.modeling_mode,
            "prompt": task.prompt,
            "context_snapshot": task.context_snapshot,
            "model": task.model,
            "status": task.status,
            "error_message": task.error_message,
            "latency_ms": task.latency_ms,
            "created_at": task.created_at.isoformat(timespec="seconds"),
        },
        scripts=[
            {
                "id": item.id,
                "asset_id": item.asset_id,
                "version_id": item.version_id,
                "summary": item.summary,
                "parameters": item.parameters_json,
                "expected_objects": item.expected_objects_json,
                "validation_status": item.validation_status,
                "validation_error": item.validation_error,
                "script": item.script,
            }
            for item in scripts
        ],
        reports=[
            {
                "id": item.id,
                "status": item.status,
                "plugin_version": item.plugin_version,
                "freecad_version": item.freecad_version,
                "document_name": item.document_name,
                "object_count": item.object_count,
                "new_objects": item.new_objects_json,
                "error_trace": item.error_trace,
                "created_at": item.created_at.isoformat(timespec="seconds"),
            }
            for item in reports
        ],
    )


@router.post("/tasks/{task_id}/cancel")
def cancel_admin_task(task_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "tasks.cancel", "task", authorization)
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    if task.status not in {"queued", "running"}:
        return {"ok": False, "task_id": task.id, "status": task.status, "message": "当前任务状态不可取消。"}
    task.status = "canceled"
    task.error_message = "管理员已取消任务。"
    _audit(db, "task.cancel", "task", task.id, task.workspace_id, {"status": task.status})
    db.commit()
    return {"ok": True, "task_id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/retry")
def retry_admin_task(task_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "tasks.retry", "task", authorization)
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    workspace = db.get(Workspace, task.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if task.status not in {"failed", "canceled"}:
        return {"ok": False, "task_id": task.id, "status": task.status, "message": "只有失败或已取消任务可以重试。"}
    if load_generation_task_payload(task.id) is None:
        raise HTTPException(status_code=409, detail="任务请求内容已不存在，无法重试。")
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    task.status = "queued"
    task.error_message = ""
    _audit(db, "task.retry", "task", task.id, task.workspace_id, {})
    db.commit()
    retry_generation_task(task.id)
    return {"ok": True, "task_id": task.id, "status": task.status}


@router.get("/script-assets", response_model=list[ScriptAssetOut])
def list_script_assets(
    db: Session = Depends(get_db),
    workspace_id: int | None = None,
    q: str = "",
    favorite: bool | None = None,
    status: str = "",
):
    stmt = select(ScriptAsset)
    if workspace_id is not None:
        stmt = stmt.where(ScriptAsset.workspace_id == workspace_id)
    if favorite is not None:
        stmt = stmt.where(ScriptAsset.favorite.is_(favorite))
    if status:
        stmt = stmt.where(ScriptAsset.status == status)
    if q:
        like = "%{}%".format(q.strip())
        stmt = stmt.where(
            or_(
                ScriptAsset.name.ilike(like),
                ScriptAsset.description.ilike(like),
                ScriptAsset.project_id.ilike(like),
            )
        )
    rows = db.execute(stmt.order_by(desc(ScriptAsset.updated_at), desc(ScriptAsset.id)).limit(200)).scalars().all()
    return [_script_asset_out(db, row) for row in rows]


@router.get("/script-assets/{asset_id}/versions", response_model=list[ScriptVersionOut])
def list_script_versions(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    rows = db.execute(
        select(ScriptVersion).where(ScriptVersion.asset_id == asset_id).order_by(desc(ScriptVersion.version))
    ).scalars().all()
    return [_script_version_out(row) for row in rows]


@router.put("/script-assets/{asset_id}", response_model=ScriptAssetOut)
def update_script_asset(asset_id: int, payload: ScriptAssetUpdate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "script_assets.update", "script_asset", authorization)
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    for field in ("name", "description", "favorite", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(asset, field, value)
    if payload.tags is not None:
        asset.tags_json = payload.tags
    if payload.metadata is not None:
        asset.metadata_json = payload.metadata
    touch_asset(asset)
    _audit(db, "script_asset.update", "script_asset", asset.id, asset.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/favorite", response_model=ScriptAssetOut)
def favorite_script_asset(asset_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "script_assets.favorite", "script_asset", authorization)
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    asset.favorite = not asset.favorite
    touch_asset(asset)
    _audit(db, "script_asset.favorite", "script_asset", asset.id, asset.workspace_id, {"favorite": asset.favorite})
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/copy", response_model=ScriptAssetOut)
def copy_admin_script_asset(asset_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    principal = _require_role(db, {"owner", "operator"}, "script_assets.copy", "script_asset", authorization)
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    copied = copy_script_asset(db, asset, principal.get("username", "admin"))
    _audit(db, "script_asset.copy", "script_asset", copied.id, copied.workspace_id, {"source_asset_id": asset.id})
    db.commit()
    db.refresh(copied)
    return _script_asset_out(db, copied)


@router.post("/script-assets/{asset_id}/rollback", response_model=ScriptAssetOut)
def rollback_script_asset(
    asset_id: int,
    payload: ScriptRollbackRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    _require_role(db, {"owner", "operator"}, "script_assets.rollback", "script_asset", authorization)
    asset = db.get(ScriptAsset, asset_id)
    version = db.get(ScriptVersion, payload.version_id)
    if asset is None or version is None or version.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Script asset version not found.")
    asset.current_version_id = version.id
    touch_asset(asset)
    _audit(db, "script_asset.rollback", "script_asset", asset.id, asset.workspace_id, {"version_id": version.id, "version": version.version})
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/reuse-template", response_model=TemplateOut)
def reuse_script_asset_as_template(
    asset_id: int,
    payload: ScriptReuseTemplateRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    _require_role(db, {"owner", "operator"}, "script_assets.reuse_template", "script_asset", authorization)
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    version = current_script_version(db, asset)
    if version is None:
        raise HTTPException(status_code=409, detail="Script asset has no version.")
    workspace_id = payload.workspace_id if payload.workspace_id is not None else asset.workspace_id
    workspace = db.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    assert_workspace_quota(db, workspace, "templates")
    item = Template(
        workspace_id=workspace_id,
        name=(payload.name or asset.name)[:128],
        category=payload.category,
        prompt=version.script,
        enabled=True,
    )
    db.add(item)
    db.flush()
    _audit(db, "script_asset.reuse_template", "template", item.id, workspace_id, {"asset_id": asset.id, "version_id": version.id})
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.get("/model-assets", response_model=list[ModelAssetOut])
def list_model_assets(db: Session = Depends(get_db), workspace_id: int | None = None, q: str = "", status: str = ""):
    stmt = select(ModelAsset)
    if workspace_id is not None:
        stmt = stmt.where(ModelAsset.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(ModelAsset.status == status)
    if q:
        like = "%{}%".format(q.strip())
        stmt = stmt.where(
            or_(
                ModelAsset.name.ilike(like),
                ModelAsset.file_name.ilike(like),
                ModelAsset.project_id.ilike(like),
            )
        )
    rows = db.execute(stmt.order_by(desc(ModelAsset.updated_at), desc(ModelAsset.id)).limit(200)).scalars().all()
    return [_model_asset_out(row) for row in rows]


@router.post("/model-assets", response_model=ModelAssetOut)
def create_model_asset(payload: ModelAssetCreate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "model_assets.create", "model_asset", authorization)
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    item = ModelAsset(
        workspace_id=payload.workspace_id,
        script_asset_id=payload.script_asset_id,
        task_id=payload.task_id,
        project_id=payload.project_id,
        name=payload.name,
        file_name=payload.file_name,
        file_type=payload.file_type,
        storage_uri=payload.storage_uri,
        preview_uri=payload.preview_uri,
        checksum=payload.checksum,
        size_bytes=payload.size_bytes,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(item)
    db.flush()
    _audit(db, "model_asset.create", "model_asset", item.id, item.workspace_id, {"name": item.name})
    db.commit()
    db.refresh(item)
    return _model_asset_out(item)


@router.put("/model-assets/{asset_id}", response_model=ModelAssetOut)
def update_model_asset(asset_id: int, payload: ModelAssetUpdate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "model_assets.update", "model_asset", authorization)
    item = db.get(ModelAsset, asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model asset not found.")
    for field in ("script_asset_id", "task_id", "project_id", "name", "file_name", "file_type", "storage_uri", "preview_uri", "checksum", "size_bytes", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    if payload.metadata is not None:
        item.metadata_json = payload.metadata
    touch_asset(item)
    _audit(db, "model_asset.update", "model_asset", item.id, item.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return _model_asset_out(item)


@router.delete("/model-assets/{asset_id}")
def delete_model_asset(asset_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "model_assets.delete", "model_asset", authorization)
    item = db.get(ModelAsset, asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model asset not found.")
    workspace_id = item.workspace_id
    db.delete(item)
    _audit(db, "model_asset.delete", "model_asset", asset_id, workspace_id, {})
    db.commit()
    return {"ok": True}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db), include_disabled: bool = False, workspace_id: int | None = None):
    stmt = select(Template).order_by(Template.category, Template.name)
    if workspace_id is not None:
        stmt = stmt.where(Template.workspace_id == workspace_id)
    if not include_disabled:
        stmt = stmt.where(Template.enabled.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [_template_out(row) for row in rows]


@router.get("/templates/export", response_model=list[TemplateOut])
def export_templates(db: Session = Depends(get_db), workspace_id: int | None = None):
    return list_templates(db=db, include_disabled=True, workspace_id=workspace_id)


@router.post("/templates/import", response_model=list[TemplateOut])
def import_templates(payload: TemplateImportRequest, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "templates.import", "template", authorization)
    imported: list[TemplateOut] = []
    for template in payload.templates:
        if template.workspace_id is not None:
            workspace = db.get(Workspace, template.workspace_id)
            if workspace is None:
                raise HTTPException(status_code=404, detail="Workspace not found.")
            existing_for_limit = db.execute(
                select(Template).where(
                    Template.name == template.name,
                    Template.category == template.category,
                    Template.workspace_id == template.workspace_id,
                )
            ).scalar_one_or_none()
            if existing_for_limit is None:
                assert_workspace_quota(db, workspace, "templates")
        existing = db.execute(
            select(Template).where(
                Template.name == template.name,
                Template.category == template.category,
                Template.workspace_id == template.workspace_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Template(
                workspace_id=template.workspace_id,
                name=template.name,
                category=template.category,
                prompt=template.prompt,
                enabled=template.enabled,
            )
            db.add(existing)
        else:
            existing.workspace_id = template.workspace_id
            existing.prompt = template.prompt
            existing.enabled = template.enabled
        _audit(db, "template.import", "template", template.name, template.workspace_id, {"category": template.category})
    db.commit()
    rows = db.execute(select(Template).order_by(Template.category, Template.name)).scalars().all()
    for row in rows:
        imported.append(_template_out(row))
    return imported


@router.post("/templates/seed-defaults", response_model=list[TemplateOut])
def seed_default_templates(db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "templates.seed_defaults", "template", authorization)
    ensure_default_templates(db)
    _audit(db, "template.seed_defaults", "template", "builtin", None, {"source": "freecad_plugin"})
    db.commit()
    rows = db.execute(select(Template).order_by(Template.category, Template.name)).scalars().all()
    return [_template_out(row) for row in rows]


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "templates.create", "template", authorization)
    if payload.workspace_id is not None:
        workspace = db.get(Workspace, payload.workspace_id)
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found.")
        assert_workspace_quota(db, workspace, "templates")
    item = Template(
        workspace_id=payload.workspace_id,
        name=payload.name,
        category=payload.category,
        prompt=payload.prompt,
        enabled=payload.enabled,
    )
    db.add(item)
    db.flush()
    _audit(db, "template.create", "template", item.id, item.workspace_id, {"name": item.name, "category": item.category})
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "templates.update", "template", authorization)
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    for field in ("name", "category", "prompt", "enabled"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    _audit(db, "template.update", "template", item.id, item.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "templates.delete", "template", authorization)
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    workspace_id = item.workspace_id
    name = item.name
    db.delete(item)
    _audit(db, "template.delete", "template", template_id, workspace_id, {"name": name})
    db.commit()
    return {"ok": True}


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "api_keys.create", "api_key", authorization)
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None:
        workspace = Workspace(id=payload.workspace_id, name="Workspace {}".format(payload.workspace_id))
        db.add(workspace)
        db.commit()
        db.refresh(workspace)
    assert_workspace_quota(db, workspace, "api_keys")
    raw_key = "fcai_" + secrets.token_urlsafe(32)
    prefix = raw_key[:12]
    item = ApiKey(
        workspace_id=payload.workspace_id,
        name=payload.name,
        key_hash=hash_api_key(raw_key),
        prefix=prefix,
    )
    db.add(item)
    db.flush()
    _audit(db, "api_key.create", "api_key", item.id, item.workspace_id, {"name": item.name, "prefix": prefix})
    db.commit()
    db.refresh(item)
    return ApiKeyCreateResponse(id=item.id, api_key=raw_key, prefix=prefix)


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), workspace_id: int | None = None):
    stmt = select(ApiKey).order_by(desc(ApiKey.id))
    if workspace_id is not None:
        stmt = stmt.where(ApiKey.workspace_id == workspace_id)
    rows = db.execute(stmt).scalars().all()
    return [_api_key_out(row) for row in rows]


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(key_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "api_keys.revoke", "api_key", authorization)
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    item.status = "revoked"
    _audit(db, "api_key.revoke", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return _api_key_out(item)


@router.post("/api-keys/{key_id}/enable", response_model=ApiKeyOut)
def enable_api_key(key_id: int, db: Session = Depends(get_db), authorization: str = Header(default="")):
    _require_role(db, {"owner", "operator"}, "api_keys.enable", "api_key", authorization)
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    item.status = "active"
    _audit(db, "api_key.enable", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return _api_key_out(item)


@router.get("/usage", response_model=UsageSummary)
def usage_summary(db: Session = Depends(get_db), workspace_id: int | None = None):
    task_stmt = select(func.count()).select_from(GenerationTask)
    succeeded_stmt = select(func.count()).select_from(GenerationTask).where(GenerationTask.status == "succeeded")
    failed_stmt = select(func.count()).select_from(GenerationTask).where(GenerationTask.status == "failed")
    report_stmt = select(func.count()).select_from(ExecutionReport)
    usage_stmt = select(
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    )
    if workspace_id is not None:
        task_stmt = task_stmt.where(GenerationTask.workspace_id == workspace_id)
        succeeded_stmt = succeeded_stmt.where(GenerationTask.workspace_id == workspace_id)
        failed_stmt = failed_stmt.where(GenerationTask.workspace_id == workspace_id)
        task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
        report_stmt = report_stmt.where(ExecutionReport.task_id.in_(task_ids))
        usage_stmt = usage_stmt.where(UsageRecord.workspace_id == workspace_id)
    task_count = db.scalar(task_stmt) or 0
    succeeded_count = db.scalar(succeeded_stmt) or 0
    failed_count = db.scalar(failed_stmt) or 0
    report_count = db.scalar(report_stmt) or 0
    usage = db.execute(usage_stmt).one()
    return UsageSummary(
        task_count=task_count,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        report_count=report_count,
        input_tokens=int(usage[0] or 0),
        output_tokens=int(usage[1] or 0),
        total_tokens=int(usage[2] or 0),
        estimated_cost=float(usage[3] or 0),
    )


@router.get("/usage/daily", response_model=list[UsageDailyItem])
def usage_daily(db: Session = Depends(get_db), days: int = Query(default=14, ge=1, le=90), workspace_id: int | None = None):
    start_day = (datetime.utcnow() - timedelta(days=days - 1)).date()
    buckets = {
        (start_day + timedelta(days=index)).isoformat(): {
            "task_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "report_count": 0,
            "total_tokens": 0,
            "estimated_cost": 0,
        }
        for index in range(days)
    }
    task_stmt = select(GenerationTask).where(GenerationTask.created_at >= datetime.combine(start_day, datetime.min.time()))
    if workspace_id is not None:
        task_stmt = task_stmt.where(GenerationTask.workspace_id == workspace_id)
    task_rows = db.execute(task_stmt).scalars().all()
    for task in task_rows:
        key = task.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["task_count"] += 1
            if task.status == "succeeded":
                buckets[key]["succeeded_count"] += 1
            if task.status == "failed":
                buckets[key]["failed_count"] += 1
    report_stmt = select(ExecutionReport).where(ExecutionReport.created_at >= datetime.combine(start_day, datetime.min.time()))
    if workspace_id is not None:
        task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
        report_stmt = report_stmt.where(ExecutionReport.task_id.in_(task_ids))
    report_rows = db.execute(report_stmt).scalars().all()
    for report in report_rows:
        key = report.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["report_count"] += 1
    usage_stmt = select(UsageRecord).where(UsageRecord.created_at >= datetime.combine(start_day, datetime.min.time()))
    if workspace_id is not None:
        usage_stmt = usage_stmt.where(UsageRecord.workspace_id == workspace_id)
    usage_rows = db.execute(usage_stmt).scalars().all()
    for usage in usage_rows:
        key = usage.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["total_tokens"] += int(usage.total_tokens or 0)
            buckets[key]["estimated_cost"] += float(usage.estimated_cost or 0)
    return [
        UsageDailyItem(day=day, **values)
        for day, values in buckets.items()
    ]


@router.get("/usage/by-model", response_model=list[UsageByModelItem])
def usage_by_model(db: Session = Depends(get_db), workspace_id: int | None = None):
    def normalize_provider(provider: str, model: str) -> str:
        provider_text = (provider or "").lower()
        model_text = (model or "").lower()
        if "deepseek" in provider_text or "deepseek" in model_text:
            return "deepseek"
        if provider_text in {"openai", "openai-compatible"} and model_text.startswith("gpt-"):
            return "openai"
        return provider or "openai-compatible"

    stmt = select(
        UsageRecord.provider,
        UsageRecord.model,
        func.count(UsageRecord.id),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    ).group_by(UsageRecord.provider, UsageRecord.model)
    if workspace_id is not None:
        stmt = stmt.where(UsageRecord.workspace_id == workspace_id)
    rows = db.execute(stmt).all()
    grouped = {}
    for row in rows:
        provider = normalize_provider(row[0], row[1])
        key = (provider, row[1])
        item = grouped.setdefault(
            key,
            {
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "estimated_cost": 0.0,
            },
        )
        item["request_count"] += int(row[2] or 0)
        item["input_tokens"] += int(row[3] or 0)
        item["output_tokens"] += int(row[4] or 0)
        item["total_tokens"] += int(row[5] or 0)
        item["estimated_cost"] += float(row[6] or 0)
    return [
        UsageByModelItem(
            provider=provider,
            model=model,
            request_count=item["request_count"],
            input_tokens=item["input_tokens"],
            output_tokens=item["output_tokens"],
            total_tokens=item["total_tokens"],
            estimated_cost=item["estimated_cost"],
        )
        for (provider, model), item in sorted(grouped.items())
    ]


@router.get("/billing/plans", response_model=list[BillingPlanOut])
def list_billing_plans():
    return billing_plans()


@router.get("/billing/summary", response_model=BillingSummaryOut)
def billing_summary(db: Session = Depends(get_db), workspace_id: int | None = None):
    stmt = select(Workspace).order_by(Workspace.id)
    if workspace_id is not None:
        stmt = stmt.where(Workspace.id == workspace_id)
    rows = db.execute(stmt).scalars().all()
    return BillingSummaryOut(workspaces=[quota_summary(db, row) for row in rows])


@router.post("/billing/checkout", response_model=PaymentCheckoutResponse)
def create_payment_checkout(
    payload: PaymentCheckoutRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    _require_role(db, {"owner", "operator"}, "billing.checkout", "billing", authorization)
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    if payload.plan not in {item["name"] for item in billing_plans()}:
        raise HTTPException(status_code=400, detail="Unknown billing plan.")
    _audit(
        db,
        "billing.checkout.requested",
        "workspace",
        workspace.id,
        workspace.id,
        {"current_plan": workspace.plan, "target_plan": payload.plan, "provider": "placeholder"},
    )
    db.commit()
    return PaymentCheckoutResponse(
        ok=True,
        provider="placeholder",
        checkout_url=None,
        message="支付接口已预留；接入支付服务后将在这里返回 checkout_url。",
    )


@router.post("/billing/webhook")
def billing_webhook(payload: dict, db: Session = Depends(get_db)):
    db.add(
        AuditLog(
            actor="payment_webhook",
            action="billing.webhook.received",
            target_type="billing",
            target_id=str(payload.get("event_id", "")),
            workspace_id=payload.get("workspace_id"),
            metadata_json=payload,
        )
    )
    db.commit()
    return {"ok": True, "message": "Billing webhook placeholder accepted."}


@billing_router.post("/webhook")
def public_billing_webhook(payload: dict, db: Session = Depends(get_db)):
    db.add(
        AuditLog(
            actor="payment_webhook",
            action="billing.webhook.received",
            target_type="billing",
            target_id=str(payload.get("event_id", "")),
            workspace_id=payload.get("workspace_id"),
            metadata_json=payload,
        )
    )
    db.commit()
    return {"ok": True, "message": "Billing webhook placeholder accepted."}


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    db: Session = Depends(get_db),
    limit: int = Query(default=80, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    workspace_id: int | None = None,
    action: str = "",
):
    stmt = select(AuditLog).order_by(desc(AuditLog.id)).offset(offset).limit(limit)
    if workspace_id is not None:
        stmt = stmt.where(AuditLog.workspace_id == workspace_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.execute(stmt).scalars().all()
    return [
        AuditLogOut(
            id=row.id,
            actor=row.actor,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            workspace_id=row.workspace_id,
            metadata=row.metadata_json,
            created_at=row.created_at.isoformat(timespec="seconds"),
        )
        for row in rows
    ]
