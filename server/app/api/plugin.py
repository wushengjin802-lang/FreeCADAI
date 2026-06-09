"""Plugin-facing API endpoints."""

import secrets
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from freecad_ai.templates import TEMPLATES

from server.app.db.session import get_db
from server.app.models.entities import AdminUser, ApiKey, AuditLog, Template, Workspace
from server.app.models.entities import GeneratedScript, GenerationTask
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
from server.app.services.auth import authenticate_admin, authenticate_plugin, create_admin_session, hash_api_key, verify_password
from server.app.services.billing import assert_workspace_quota, record_usage
from server.app.services.llm_orchestrator import generate_script, regenerate_script, repair_script
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
    user = db.execute(select(AdminUser).where(AdminUser.username == payload.username)).scalar_one_or_none()
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Invalid username or password.")
    raw_token, session = create_admin_session(db, user)
    db.add(
        AuditLog(
            actor=user.username,
            action="plugin.account.login",
            target_type="admin_user",
            target_id=str(user.id),
            metadata_json={"source": "freecad_plugin"},
        )
    )
    db.commit()
    return PluginAccountLoginResponse(
        token=raw_token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user={"id": user.id, "username": user.username, "role": user.role, "status": user.status},
    )


@router.get("/account/workspaces", response_model=PluginWorkspacesResponse)
def plugin_account_workspaces(
    db: Session = Depends(get_db),
    admin=Depends(authenticate_admin),
):
    if admin.get("role") not in {"owner", "operator", "viewer"}:
        raise HTTPException(status_code=403, detail="Permission denied.")
    rows = db.execute(select(Workspace).order_by(Workspace.id)).scalars().all()
    return PluginWorkspacesResponse(workspaces=[_workspace_item(db, row) for row in rows])


@router.post("/account/bind-workspace", response_model=PluginBindWorkspaceResponse)
def plugin_account_bind_workspace(
    payload: PluginBindWorkspaceRequest,
    db: Session = Depends(get_db),
    authorization: str = Header(default=""),
):
    admin = authenticate_admin(db=db, authorization=authorization)
    if admin.get("role") not in {"owner", "operator"}:
        raise HTTPException(status_code=403, detail="Permission denied.")
    workspace = db.get(Workspace, payload.workspace_id)
    if workspace is None or workspace.status != "active":
        raise HTTPException(status_code=404, detail="Workspace is not active.")
    assert_workspace_quota(db, workspace, "api_keys")
    raw_key = "fcai_" + secrets.token_urlsafe(32)
    prefix = raw_key[:12]
    item = ApiKey(
        workspace_id=workspace.id,
        name=payload.key_name,
        key_hash=hash_api_key(raw_key),
        prefix=prefix,
        status="active",
    )
    db.add(item)
    db.add(
        AuditLog(
            actor=admin.get("username", "admin"),
            action="plugin.workspace.bind",
            target_type="workspace",
            target_id=str(workspace.id),
            workspace_id=workspace.id,
            metadata_json={"key_name": payload.key_name, "prefix": prefix},
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
                category="builtin",
                prompt=item["prompt"],
            )
            for index, item in enumerate(TEMPLATES, start=1)
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


def _submit_generation(db: Session, workspace: Workspace, action: str, request, extra=None):
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


def _run_generation(db, workspace, action, request, callback):
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
    return _submit_generation(db, workspace, "generate", request)


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
    )


@router.post("/regenerate/submit", response_model=GenerationSubmitResponse)
def submit_regenerate(
    request: RegenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _submit_generation(db, workspace, "regenerate", request, {"parameters": request.parameters})


@router.get("/tasks/{task_id}", response_model=GenerationTaskStatusResponse)
def task_status(
    task_id: int,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    task = _require_workspace_task(db, workspace, task_id)
    return _status_payload(db, task)


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
    )


@router.post("/execution-reports", response_model=ExecutionReportResponse)
def execution_report(
    request: ExecutionReportRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    item = save_execution_report(db, request)
    return ExecutionReportResponse(ok=True, report_id=item.id)
