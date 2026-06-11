"""Enterprise/user console API for phase 16."""

import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from server.app.db.session import get_db
from server.app.models.entities import (
    ApiKey,
    AuditLog,
    ExecutionReport,
    GeneratedScript,
    GenerationTask,
    ModelAsset,
    ScriptAsset,
    Template,
    User,
    UserSession,
    Workspace,
    WorkspaceInvite,
    WorkspaceMember,
)
from server.app.schemas.console import (
    ConsoleAuthResponse,
    ConsoleApiKeyCreate,
    ConsoleApiKeyCreateResponse,
    ConsoleApiKeyOut,
    ConsoleApiKeyRotateResponse,
    ConsoleInviteCreate,
    ConsoleInviteOut,
    ConsoleLoginRequest,
    ConsoleMemberOut,
    ConsoleMemberUpdate,
    ConsolePasswordChange,
    ConsolePluginGuideOut,
    ConsoleRegisterRequest,
    ConsoleTaskActionResponse,
    ConsoleTaskCreate,
    ConsoleTaskDetail,
    ConsoleTaskListItem,
    ConsoleTaskSubmitResponse,
    ConsoleTemplateOut,
    ConsoleUserOut,
    ConsoleWorkspaceOut,
    ConsoleWorkspaceUpdate,
)
from server.app.services.auth import (
    authenticate_user,
    create_user_session,
    current_user_actor,
    hash_api_key,
    hash_password,
    require_workspace_member,
    verify_password,
)
from server.app.services.billing import quota_summary
from server.app.services.billing import assert_workspace_quota
from server.app.services.task_queue import enqueue_generation_task, load_generation_task_payload, retry_generation_task
from server.app.services.task_store import create_task


auth_router = APIRouter(prefix="/api/v1/console/auth", tags=["console-auth"])
router = APIRouter(prefix="/api/v1/console", tags=["console"], dependencies=[Depends(authenticate_user)])
public_router = APIRouter(prefix="/api/v1/console", tags=["console-public"])


CONSOLE_WRITE_ROLES = {"owner", "admin"}
CONSOLE_OWNER_ROLES = {"owner"}
CONSOLE_TASK_ROLES = {"owner", "admin", "member"}
MEMBER_ROLES = {"owner", "admin", "member", "viewer"}


def _normalize_email(email: str):
    value = (email or "").strip().lower()
    if "@" not in value or "." not in value.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Invalid email.")
    return value


def _user_out(row: User):
    return ConsoleUserOut(
        id=row.id,
        email=row.email,
        phone=row.phone,
        display_name=row.display_name,
        status=row.status,
        last_login_at=row.last_login_at.isoformat(timespec="seconds") if row.last_login_at else None,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _workspace_out(db: Session, workspace: Workspace, role: str):
    member_count = db.scalar(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.status == "active",
        )
    ) or 0
    api_key_count = db.scalar(select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == workspace.id)) or 0
    task_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace.id)) or 0
    script_count = db.scalar(select(func.count()).select_from(ScriptAsset).where(ScriptAsset.workspace_id == workspace.id)) or 0
    model_count = db.scalar(select(func.count()).select_from(ModelAsset).where(ModelAsset.workspace_id == workspace.id)) or 0
    return ConsoleWorkspaceOut(
        id=workspace.id,
        name=workspace.name,
        plan=workspace.plan,
        status=workspace.status,
        role=role,
        created_at=workspace.created_at.isoformat(timespec="seconds"),
        member_count=member_count,
        api_key_count=api_key_count,
        task_count=task_count,
        asset_count=script_count + model_count,
        quota=quota_summary(db, workspace),
    )


def _user_workspaces(db: Session, user_id: int):
    rows = db.execute(
        select(Workspace, WorkspaceMember)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.status == "active",
            Workspace.status == "active",
        )
        .order_by(Workspace.id)
    ).all()
    return [_workspace_out(db, workspace, member.role) for workspace, member in rows]


def _member_out(db: Session, member: WorkspaceMember):
    user = db.get(User, member.user_id)
    return ConsoleMemberOut(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        email=user.email if user else "",
        display_name=user.display_name if user else "",
        role=member.role,
        status=member.status,
        joined_at=member.joined_at.isoformat(timespec="seconds") if member.joined_at else None,
        created_at=member.created_at.isoformat(timespec="seconds"),
    )


def _api_key_out(row: ApiKey):
    return ConsoleApiKeyOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        prefix=row.prefix,
        status=row.status,
        scopes=row.scopes_json or [],
        created_by_user_id=row.created_by_user_id,
        expires_at=row.expires_at.isoformat(timespec="seconds") if row.expires_at else None,
        last_used_at=row.last_used_at.isoformat(timespec="seconds") if row.last_used_at else None,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _task_out(row: GenerationTask):
    return ConsoleTaskListItem(
        id=row.id,
        workspace_id=row.workspace_id,
        created_by_user_id=row.created_by_user_id,
        project_id=row.project_id,
        source=row.source,
        action=row.action,
        modeling_mode=row.modeling_mode,
        prompt=row.prompt,
        model=row.model,
        status=row.status,
        error_message=row.error_message,
        latency_ms=row.latency_ms,
        created_at=row.created_at.isoformat(timespec="seconds"),
        updated_at=row.updated_at.isoformat(timespec="seconds"),
    )


def _template_out(row: Template):
    return ConsoleTemplateOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        category=row.category,
        prompt=row.prompt,
        enabled=row.enabled,
    )


def _audit(db: Session, action: str, target_type: str, target_id="", workspace_id=None, metadata=None):
    db.add(
        AuditLog(
            actor=current_user_actor(),
            action=action,
            target_type=target_type,
            target_id=str(target_id or ""),
            workspace_id=workspace_id,
            metadata_json=metadata or {},
        )
    )


@auth_router.post("/register", response_model=ConsoleAuthResponse)
def register(payload: ConsoleRegisterRequest, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    exists = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Email already exists.")
    now = datetime.utcnow()
    user = User(
        email=email,
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
        status="active",
        created_at=now,
        updated_at=now,
    )
    workspace_name = (payload.workspace_name or "").strip() or "{}的工作区".format(user.display_name)
    workspace = Workspace(name=workspace_name, plan="free", status="active", created_at=now)
    db.add(user)
    db.add(workspace)
    db.flush()
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        role="owner",
        status="active",
        joined_at=now,
        created_at=now,
    )
    db.add(member)
    db.add(
        AuditLog(
            actor="user:{}".format(user.id),
            action="console.user.register",
            target_type="user",
            target_id=str(user.id),
            workspace_id=workspace.id,
            metadata_json={"email": user.email, "workspace_id": workspace.id},
        )
    )
    db.commit()
    db.refresh(user)
    token, session = create_user_session(db, user)
    return ConsoleAuthResponse(
        token=token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user=_user_out(user),
        workspaces=_user_workspaces(db, user.id),
    )


@auth_router.post("/login", response_model=ConsoleAuthResponse)
def login(payload: ConsoleLoginRequest, db: Session = Depends(get_db)):
    email = _normalize_email(payload.email)
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None or user.status != "active" or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=403, detail="Invalid email or password.")
    token, session = create_user_session(db, user)
    db.add(
        AuditLog(
            actor="user:{}".format(user.id),
            action="console.user.login",
            target_type="user",
            target_id=str(user.id),
            metadata_json={"email": user.email},
        )
    )
    db.commit()
    return ConsoleAuthResponse(
        token=token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user=_user_out(user),
        workspaces=_user_workspaces(db, user.id),
    )


@router.get("/auth/me")
def me(db: Session = Depends(get_db), user=Depends(authenticate_user)):
    row = db.get(User, user["id"])
    if row is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return {"user": _user_out(row), "workspaces": _user_workspaces(db, row.id)}


@router.put("/auth/password")
def change_password(payload: ConsolePasswordChange, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    row = db.get(User, user["id"])
    if row is None or not verify_password(payload.current_password, row.password_hash):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")
    row.password_hash = hash_password(payload.new_password)
    row.updated_at = datetime.utcnow()
    _audit(db, "console.user.password.change", "user", row.id, metadata={"email": row.email})
    db.commit()
    return {"ok": True}


@router.post("/auth/logout")
def logout(db: Session = Depends(get_db), authorization: str = Header(default="")):
    token = authorization.split(" ", 1)[1].strip() if authorization.lower().startswith("bearer ") else ""
    if token:
        session = db.execute(select(UserSession).where(UserSession.token_hash == hash_api_key(token))).scalar_one_or_none()
        if session is not None:
            session.status = "revoked"
            _audit(db, "console.user.logout", "user_session", session.id, metadata={"user_id": session.user_id})
            db.commit()
    return {"ok": True}


@router.get("/workspaces", response_model=list[ConsoleWorkspaceOut])
def list_workspaces(db: Session = Depends(get_db), user=Depends(authenticate_user)):
    return _user_workspaces(db, user["id"])


@router.get("/workspaces/{workspace_id}", response_model=ConsoleWorkspaceOut)
def workspace_detail(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace, member = require_workspace_member(db, user["id"], workspace_id)
    return _workspace_out(db, workspace, member.role)


@router.put("/workspaces/{workspace_id}", response_model=ConsoleWorkspaceOut)
def update_workspace(
    workspace_id: int,
    payload: ConsoleWorkspaceUpdate,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
):
    workspace, member = require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    if payload.name is not None:
        workspace.name = payload.name.strip()
    _audit(db, "console.workspace.update", "workspace", workspace.id, workspace.id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(workspace)
    return _workspace_out(db, workspace, member.role)


@router.get("/workspaces/{workspace_id}/members", response_model=list[ConsoleMemberOut])
def list_members(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id)
    rows = db.execute(
        select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id).order_by(WorkspaceMember.id)
    ).scalars().all()
    return [_member_out(db, row) for row in rows]


@router.post("/workspaces/{workspace_id}/invites", response_model=ConsoleInviteOut)
def create_invite(
    workspace_id: int,
    payload: ConsoleInviteCreate,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
):
    require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    email = _normalize_email(payload.email)
    if payload.role not in MEMBER_ROLES or payload.role == "owner":
        raise HTTPException(status_code=422, detail="Invalid role.")
    target_user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if target_user is not None:
        existing = db.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == target_user.id,
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = WorkspaceMember(
                workspace_id=workspace_id,
                user_id=target_user.id,
                role=payload.role,
                status="active",
                invited_by_user_id=user["id"],
                joined_at=datetime.utcnow(),
            )
            db.add(existing)
        else:
            existing.role = payload.role
            existing.status = "active"
            existing.joined_at = existing.joined_at or datetime.utcnow()
        _audit(db, "console.member.add", "workspace_member", target_user.id, workspace_id, {"email": email, "role": payload.role})
        db.commit()
        return ConsoleInviteOut(
            id=0,
            workspace_id=workspace_id,
            email=email,
            role=payload.role,
            status="accepted",
            expires_at=datetime.utcnow().isoformat(timespec="seconds"),
            invite_token=None,
            created_at=datetime.utcnow().isoformat(timespec="seconds"),
        )
    raw_token = "fcai_invite_" + secrets.token_urlsafe(28)
    now = datetime.utcnow()
    invite = WorkspaceInvite(
        workspace_id=workspace_id,
        email=email,
        role=payload.role,
        token_hash=hash_api_key(raw_token),
        status="pending",
        expires_at=now + timedelta(days=7),
        created_at=now,
    )
    db.add(invite)
    db.flush()
    _audit(db, "console.workspace.invite", "workspace_invite", invite.id, workspace_id, {"email": email, "role": payload.role})
    db.commit()
    db.refresh(invite)
    return ConsoleInviteOut(
        id=invite.id,
        workspace_id=invite.workspace_id,
        email=invite.email,
        role=invite.role,
        status=invite.status,
        expires_at=invite.expires_at.isoformat(timespec="seconds"),
        invite_token=raw_token,
        created_at=invite.created_at.isoformat(timespec="seconds"),
    )


@router.put("/workspaces/{workspace_id}/members/{member_id}", response_model=ConsoleMemberOut)
def update_member(
    workspace_id: int,
    member_id: int,
    payload: ConsoleMemberUpdate,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
):
    require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    item = db.get(WorkspaceMember, member_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Member not found.")
    if item.user_id == user["id"] and (payload.role is not None or payload.status == "disabled"):
        raise HTTPException(status_code=400, detail="Cannot demote or disable yourself.")
    if payload.role is not None:
        if payload.role not in MEMBER_ROLES:
            raise HTTPException(status_code=422, detail="Invalid role.")
        if item.role == "owner" and payload.role != "owner":
            owner_count = db.scalar(
                select(func.count()).select_from(WorkspaceMember).where(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.role == "owner",
                    WorkspaceMember.status == "active",
                )
            ) or 0
            if owner_count <= 1:
                raise HTTPException(status_code=400, detail="Workspace needs at least one owner.")
        item.role = payload.role
    if payload.status is not None:
        if payload.status not in {"active", "disabled"}:
            raise HTTPException(status_code=422, detail="Invalid status.")
        item.status = payload.status
    _audit(db, "console.member.update", "workspace_member", item.id, workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return _member_out(db, item)


@router.delete("/workspaces/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: int, member_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    item = db.get(WorkspaceMember, member_id)
    if item is None or item.workspace_id != workspace_id:
        raise HTTPException(status_code=404, detail="Member not found.")
    if item.user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Cannot remove yourself.")
    if item.role == "owner" and item.status == "active":
        owner_count = db.scalar(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.role == "owner",
                WorkspaceMember.status == "active",
            )
        ) or 0
        if owner_count <= 1:
            raise HTTPException(status_code=400, detail="Workspace needs at least one owner.")
    item.status = "disabled"
    _audit(db, "console.member.remove", "workspace_member", item.id, workspace_id, {"user_id": item.user_id})
    db.commit()
    return {"ok": True}


@router.get("/tasks", response_model=list[ConsoleTaskListItem])
def list_tasks(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str = "",
    action: str = "",
    modeling_mode: str = "",
    q: str = "",
    mine: bool = False,
):
    require_workspace_member(db, user["id"], workspace_id)
    stmt = select(GenerationTask).where(GenerationTask.workspace_id == workspace_id)
    if mine:
        stmt = stmt.where(GenerationTask.created_by_user_id == user["id"])
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
    rows = db.execute(stmt.order_by(desc(GenerationTask.id)).offset(offset).limit(limit)).scalars().all()
    return [_task_out(row) for row in rows]


@router.post("/tasks", response_model=ConsoleTaskSubmitResponse)
def submit_task(payload: ConsoleTaskCreate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace, _member = require_workspace_member(db, user["id"], payload.workspace_id, CONSOLE_TASK_ROLES)
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    context = payload.context or ""
    if payload.template_id is not None:
        template = db.get(Template, payload.template_id)
        if template is None or not template.enabled or (template.workspace_id not in {None, workspace.id}):
            raise HTTPException(status_code=404, detail="Template not found.")
        context = "{}\n\nTemplate: {}\n{}".format(context, template.name, template.prompt).strip()
    task = create_task(
        db,
        workspace,
        "generate",
        payload.prompt,
        context,
        payload.modeling_mode,
        payload.project_id,
        status="queued",
        source="console",
        created_by_user_id=user["id"],
    )
    queue_payload = {
        "action": "generate",
        "prompt": payload.prompt,
        "context": context,
        "modeling_mode": payload.modeling_mode,
        "project_id": payload.project_id,
        "created_by_user_id": user["id"],
        "source": "console",
    }
    enqueue_generation_task(task.id, queue_payload)
    _audit(db, "console.task.submit", "task", task.id, workspace.id, {"modeling_mode": payload.modeling_mode, "project_id": payload.project_id})
    db.commit()
    return ConsoleTaskSubmitResponse(task_id=task.id, status=task.status, message="Task has been queued.")


@router.get("/tasks/{task_id}", response_model=ConsoleTaskDetail)
def task_detail(task_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    require_workspace_member(db, user["id"], task.workspace_id)
    scripts = db.execute(select(GeneratedScript).where(GeneratedScript.task_id == task_id)).scalars().all()
    reports = db.execute(select(ExecutionReport).where(ExecutionReport.task_id == task_id)).scalars().all()
    return ConsoleTaskDetail(
        task=_task_out(task).model_dump() | {"context_snapshot": task.context_snapshot},
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
                "created_at": item.created_at.isoformat(timespec="seconds"),
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


@router.post("/tasks/{task_id}/cancel", response_model=ConsoleTaskActionResponse)
def cancel_task(task_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    require_workspace_member(db, user["id"], task.workspace_id, CONSOLE_TASK_ROLES)
    if task.status not in {"queued", "running"}:
        return ConsoleTaskActionResponse(ok=False, task_id=task.id, status=task.status, message="Task cannot be canceled in its current status.")
    task.status = "canceled"
    task.error_message = "User canceled task."
    _audit(db, "console.task.cancel", "task", task.id, task.workspace_id, {"status": task.status})
    db.commit()
    return ConsoleTaskActionResponse(ok=True, task_id=task.id, status=task.status, message="Task canceled.")


@router.post("/tasks/{task_id}/retry", response_model=ConsoleTaskActionResponse)
def retry_task(task_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    task = db.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found.")
    workspace, _member = require_workspace_member(db, user["id"], task.workspace_id, CONSOLE_TASK_ROLES)
    if task.status not in {"failed", "canceled"}:
        return ConsoleTaskActionResponse(ok=False, task_id=task.id, status=task.status, message="Only failed or canceled tasks can be retried.")
    if load_generation_task_payload(task.id) is None:
        raise HTTPException(status_code=409, detail="Queued task payload is missing.")
    assert_workspace_quota(db, workspace, "tasks")
    assert_workspace_quota(db, workspace, "concurrent")
    task.status = "queued"
    task.error_message = ""
    _audit(db, "console.task.retry", "task", task.id, task.workspace_id, {})
    db.commit()
    retry_generation_task(task.id)
    return ConsoleTaskActionResponse(ok=True, task_id=task.id, status=task.status, message="Task queued again.")


@router.get("/templates", response_model=list[ConsoleTemplateOut])
def list_templates(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id)
    rows = db.execute(
        select(Template)
        .where(
            Template.enabled.is_(True),
            or_(Template.workspace_id.is_(None), Template.workspace_id == workspace_id),
        )
        .order_by(Template.category, Template.name)
    ).scalars().all()
    return [_template_out(row) for row in rows]


@router.get("/api-keys", response_model=list[ConsoleApiKeyOut])
def list_api_keys(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id)
    rows = db.execute(
        select(ApiKey).where(ApiKey.workspace_id == workspace_id).order_by(ApiKey.id.desc())
    ).scalars().all()
    return [_api_key_out(row) for row in rows]


@router.post("/api-keys", response_model=ConsoleApiKeyCreateResponse)
def create_api_key(payload: ConsoleApiKeyCreate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace, _member = require_workspace_member(db, user["id"], payload.workspace_id, CONSOLE_WRITE_ROLES)
    scopes = payload.scopes or ["plugin"]
    if any(scope not in {"plugin"} for scope in scopes):
        raise HTTPException(status_code=422, detail="Invalid API key scope.")
    assert_workspace_quota(db, workspace, "api_keys")
    raw_key = "fcai_" + secrets.token_urlsafe(32)
    prefix = raw_key[:12]
    now = datetime.utcnow()
    item = ApiKey(
        workspace_id=workspace.id,
        name=payload.name.strip(),
        key_hash=hash_api_key(raw_key),
        prefix=prefix,
        status="active",
        created_by_user_id=user["id"],
        expires_at=now + timedelta(days=payload.expires_in_days) if payload.expires_in_days else None,
        scopes_json=scopes,
        created_at=now,
    )
    db.add(item)
    db.flush()
    _audit(db, "console.api_key.create", "api_key", item.id, workspace.id, {"name": item.name, "prefix": prefix, "scopes": scopes})
    db.commit()
    db.refresh(item)
    return ConsoleApiKeyCreateResponse(id=item.id, api_key=raw_key, prefix=prefix, item=_api_key_out(item))


@router.post("/api-keys/{key_id}/enable", response_model=ConsoleApiKeyOut)
def enable_api_key(key_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    require_workspace_member(db, user["id"], item.workspace_id, CONSOLE_WRITE_ROLES)
    item.status = "active"
    _audit(db, "console.api_key.enable", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return _api_key_out(item)


@router.post("/api-keys/{key_id}/disable", response_model=ConsoleApiKeyOut)
def disable_api_key(key_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    require_workspace_member(db, user["id"], item.workspace_id, CONSOLE_WRITE_ROLES)
    item.status = "disabled"
    _audit(db, "console.api_key.disable", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return _api_key_out(item)


@router.post("/api-keys/{key_id}/rotate", response_model=ConsoleApiKeyRotateResponse)
def rotate_api_key(key_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(ApiKey, key_id)
    if item is None:
        raise HTTPException(status_code=404, detail="API key not found.")
    require_workspace_member(db, user["id"], item.workspace_id, CONSOLE_WRITE_ROLES)
    raw_key = "fcai_" + secrets.token_urlsafe(32)
    item.key_hash = hash_api_key(raw_key)
    item.prefix = raw_key[:12]
    item.status = "active"
    _audit(db, "console.api_key.rotate", "api_key", item.id, item.workspace_id, {"prefix": item.prefix})
    db.commit()
    db.refresh(item)
    return ConsoleApiKeyRotateResponse(id=item.id, api_key=raw_key, prefix=item.prefix, item=_api_key_out(item))


@router.get("/plugin/connection-guide", response_model=ConsolePluginGuideOut)
def plugin_connection_guide(
    workspace_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
):
    workspace, _member = require_workspace_member(db, user["id"], workspace_id)
    base_url = str(request.base_url).rstrip("/")
    return ConsolePluginGuideOut(
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        saas_base_url=base_url,
    )


@public_router.post("/invites/{invite_token}/accept", response_model=ConsoleAuthResponse)
def accept_invite(invite_token: str, payload: ConsoleRegisterRequest, db: Session = Depends(get_db)):
    invite = db.execute(
        select(WorkspaceInvite).where(
            WorkspaceInvite.token_hash == hash_api_key(invite_token),
            WorkspaceInvite.status == "pending",
            WorkspaceInvite.expires_at > datetime.utcnow(),
        )
    ).scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found.")
    email = _normalize_email(payload.email)
    if email != invite.email:
        raise HTTPException(status_code=403, detail="Invite email does not match.")
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    now = datetime.utcnow()
    if user is None:
        user = User(
            email=email,
            display_name=payload.display_name.strip(),
            password_hash=hash_password(payload.password),
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
    else:
        if not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=403, detail="Invalid email or password.")
        user.display_name = user.display_name or payload.display_name.strip()
        user.updated_at = now
    member = db.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == invite.workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    ).scalar_one_or_none()
    if member is None:
        db.add(
            WorkspaceMember(
                workspace_id=invite.workspace_id,
                user_id=user.id,
                role=invite.role,
                status="active",
                joined_at=now,
                created_at=now,
            )
        )
    else:
        member.role = invite.role
        member.status = "active"
        member.joined_at = member.joined_at or now
    invite.status = "accepted"
    invite.accepted_at = now
    db.add(
        AuditLog(
            actor="user:{}".format(user.id),
            action="console.workspace.invite.accept",
            target_type="workspace_invite",
            target_id=str(invite.id),
            workspace_id=invite.workspace_id,
            metadata_json={"email": email, "role": invite.role},
        )
    )
    db.commit()
    db.refresh(user)
    token, session = create_user_session(db, user)
    return ConsoleAuthResponse(
        token=token,
        expires_at=session.expires_at.isoformat(timespec="seconds"),
        user=_user_out(user),
        workspaces=_user_workspaces(db, user.id),
    )
