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
    Template,
    Workspace,
)
from server.app.schemas.admin import (
    AdminLoginRequest,
    AdminLoginResponse,
    AdminUserCreate,
    AdminUserOut,
    AdminUserUpdate,
    AuditLogOut,
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyOut,
    TaskDetail,
    TaskListItem,
    TemplateCreate,
    TemplateImportRequest,
    TemplateOut,
    TemplateUpdate,
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
    hash_api_key,
    hash_password,
    verify_password,
)


auth_router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin-auth"])
router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(authenticate_admin)])


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
def list_admin_users(db: Session = Depends(get_db)):
    rows = db.execute(select(AdminUser).order_by(AdminUser.id)).scalars().all()
    return [_admin_user_out(row) for row in rows]


@router.post("/admin-users", response_model=AdminUserOut)
def create_admin_user(payload: AdminUserCreate, db: Session = Depends(get_db)):
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
def update_admin_user(user_id: int, payload: AdminUserUpdate, db: Session = Depends(get_db)):
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
    result = []
    for row in rows:
        api_key_count = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == row.id)) or 0
        task_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == row.id)) or 0
        result.append(
            WorkspaceOut(
                id=row.id,
                name=row.name,
                plan=row.plan,
                status=row.status,
                created_at=row.created_at.isoformat(timespec="seconds"),
                api_key_count=api_key_count,
                task_count=task_count,
            )
        )
    return result


@router.post("/workspaces", response_model=WorkspaceOut)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)):
    item = Workspace(name=payload.name, plan=payload.plan, status=payload.status)
    db.add(item)
    db.flush()
    _audit(db, "workspace.create", "workspace", item.id, item.id, {"name": item.name, "plan": item.plan, "status": item.status})
    db.commit()
    db.refresh(item)
    return WorkspaceOut(
        id=item.id,
        name=item.name,
        plan=item.plan,
        status=item.status,
        created_at=item.created_at.isoformat(timespec="seconds"),
        api_key_count=0,
        task_count=0,
    )


@router.put("/workspaces/{workspace_id}", response_model=WorkspaceOut)
def update_workspace(workspace_id: int, payload: WorkspaceUpdate, db: Session = Depends(get_db)):
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
    api_key_count = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == item.id)) or 0
    task_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == item.id)) or 0
    return WorkspaceOut(
        id=item.id,
        name=item.name,
        plan=item.plan,
        status=item.status,
        created_at=item.created_at.isoformat(timespec="seconds"),
        api_key_count=api_key_count,
        task_count=task_count,
    )


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
def import_templates(payload: TemplateImportRequest, db: Session = Depends(get_db)):
    imported: list[TemplateOut] = []
    for template in payload.templates:
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


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
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
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db)):
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
def delete_template(template_id: int, db: Session = Depends(get_db)):
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
def create_api_key(payload: ApiKeyCreate, db: Session = Depends(get_db)):
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None:
        workspace = Workspace(id=payload.workspace_id, name="Workspace {}".format(payload.workspace_id))
        db.add(workspace)
        db.commit()
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
def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    item.status = "revoked"
    _audit(db, "api_key.revoke", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return _api_key_out(item)


@router.post("/api-keys/{key_id}/enable", response_model=ApiKeyOut)
def enable_api_key(key_id: int, db: Session = Depends(get_db)):
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
    if workspace_id is not None:
        task_stmt = task_stmt.where(GenerationTask.workspace_id == workspace_id)
        succeeded_stmt = succeeded_stmt.where(GenerationTask.workspace_id == workspace_id)
        failed_stmt = failed_stmt.where(GenerationTask.workspace_id == workspace_id)
        task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
        report_stmt = report_stmt.where(ExecutionReport.task_id.in_(task_ids))
    task_count = db.scalar(task_stmt) or 0
    succeeded_count = db.scalar(succeeded_stmt) or 0
    failed_count = db.scalar(failed_stmt) or 0
    report_count = db.scalar(report_stmt) or 0
    return UsageSummary(
        task_count=task_count,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        report_count=report_count,
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
    return [
        UsageDailyItem(day=day, **values)
        for day, values in buckets.items()
    ]


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
