"""Admin management API for phase 5+."""

import csv
import io
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from server.app.db.session import get_db
from server.app.models.entities import ApiKey, ExecutionReport, GeneratedScript, GenerationTask, Template, Workspace
from server.app.schemas.admin import (
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
)
from server.app.services.auth import authenticate_admin, hash_api_key


router = APIRouter(prefix="/api/v1/admin", tags=["admin"], dependencies=[Depends(authenticate_admin)])


@router.get("/tasks", response_model=list[TaskListItem])
def list_tasks(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str = "",
    action: str = "",
    modeling_mode: str = "",
    q: str = "",
):
    stmt = select(GenerationTask)
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
):
    rows = list_tasks(
        db=db,
        limit=limit,
        offset=0,
        status=status,
        action=action,
        modeling_mode=modeling_mode,
        q=q,
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
def list_templates(db: Session = Depends(get_db), include_disabled: bool = False):
    stmt = select(Template).order_by(Template.category, Template.name)
    if not include_disabled:
        stmt = stmt.where(Template.enabled.is_(True))
    rows = db.execute(stmt).scalars().all()
    return [TemplateOut(id=row.id, name=row.name, category=row.category, prompt=row.prompt, enabled=row.enabled) for row in rows]


@router.get("/templates/export", response_model=list[TemplateOut])
def export_templates(db: Session = Depends(get_db)):
    return list_templates(db=db, include_disabled=True)


@router.post("/templates/import", response_model=list[TemplateOut])
def import_templates(payload: TemplateImportRequest, db: Session = Depends(get_db)):
    imported: list[TemplateOut] = []
    for template in payload.templates:
        existing = db.execute(
            select(Template).where(Template.name == template.name, Template.category == template.category)
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
    db.commit()
    rows = db.execute(select(Template).order_by(Template.category, Template.name)).scalars().all()
    for row in rows:
        imported.append(TemplateOut(id=row.id, name=row.name, category=row.category, prompt=row.prompt, enabled=row.enabled))
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
    db.commit()
    db.refresh(item)
    return TemplateOut(id=item.id, name=item.name, category=item.category, prompt=item.prompt, enabled=item.enabled)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db)):
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    for field in ("name", "category", "prompt", "enabled"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    db.commit()
    db.refresh(item)
    return TemplateOut(id=item.id, name=item.name, category=item.category, prompt=item.prompt, enabled=item.enabled)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db)):
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    db.delete(item)
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
    db.commit()
    db.refresh(item)
    return ApiKeyCreateResponse(id=item.id, api_key=raw_key, prefix=prefix)


@router.get("/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db)):
    rows = db.execute(select(ApiKey).order_by(desc(ApiKey.id))).scalars().all()
    return [
        ApiKeyOut(
            id=row.id,
            workspace_id=row.workspace_id,
            name=row.name,
            prefix=row.prefix,
            status=row.status,
            last_used_at=row.last_used_at.isoformat(timespec="seconds") if row.last_used_at else None,
            created_at=row.created_at.isoformat(timespec="seconds"),
        )
        for row in rows
    ]


@router.post("/api-keys/{key_id}/revoke", response_model=ApiKeyOut)
def revoke_api_key(key_id: int, db: Session = Depends(get_db)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    item.status = "revoked"
    db.commit()
    db.refresh(item)
    return ApiKeyOut(
        id=item.id,
        workspace_id=item.workspace_id,
        name=item.name,
        prefix=item.prefix,
        status=item.status,
        last_used_at=item.last_used_at.isoformat(timespec="seconds") if item.last_used_at else None,
        created_at=item.created_at.isoformat(timespec="seconds"),
    )


@router.post("/api-keys/{key_id}/enable", response_model=ApiKeyOut)
def enable_api_key(key_id: int, db: Session = Depends(get_db)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    item.status = "active"
    db.commit()
    db.refresh(item)
    return ApiKeyOut(
        id=item.id,
        workspace_id=item.workspace_id,
        name=item.name,
        prefix=item.prefix,
        status=item.status,
        last_used_at=item.last_used_at.isoformat(timespec="seconds") if item.last_used_at else None,
        created_at=item.created_at.isoformat(timespec="seconds"),
    )


@router.get("/usage", response_model=UsageSummary)
def usage_summary(db: Session = Depends(get_db)):
    task_count = db.scalar(select(func.count()).select_from(GenerationTask)) or 0
    succeeded_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.status == "succeeded")) or 0
    failed_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.status == "failed")) or 0
    report_count = db.scalar(select(func.count()).select_from(ExecutionReport)) or 0
    return UsageSummary(
        task_count=task_count,
        succeeded_count=succeeded_count,
        failed_count=failed_count,
        report_count=report_count,
    )


@router.get("/usage/daily", response_model=list[UsageDailyItem])
def usage_daily(db: Session = Depends(get_db), days: int = Query(default=14, ge=1, le=90)):
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
    task_rows = db.execute(select(GenerationTask).where(GenerationTask.created_at >= datetime.combine(start_day, datetime.min.time()))).scalars().all()
    for task in task_rows:
        key = task.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["task_count"] += 1
            if task.status == "succeeded":
                buckets[key]["succeeded_count"] += 1
            if task.status == "failed":
                buckets[key]["failed_count"] += 1
    report_rows = db.execute(select(ExecutionReport).where(ExecutionReport.created_at >= datetime.combine(start_day, datetime.min.time()))).scalars().all()
    for report in report_rows:
        key = report.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["report_count"] += 1
    return [
        UsageDailyItem(day=day, **values)
        for day, values in buckets.items()
    ]
