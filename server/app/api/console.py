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
    Notification,
    ScriptAsset,
    ScriptVersion,
    Template,
    User,
    UserSession,
    UsageRecord,
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
    ConsoleNotificationOut,
    ConsoleUsageMemberItem,
    ConsoleUsageProjectItem,
    ConsoleUserOut,
    ConsoleWorkspaceOut,
    ConsoleWorkspaceUpdate,
)
from server.app.schemas.admin import (
    ModelAssetCreate,
    ModelAssetOut,
    ModelAssetUpdate,
    ScriptAssetOut,
    ScriptAssetUpdate,
    ScriptReuseTemplateRequest,
    ScriptRollbackRequest,
    ScriptVersionOut,
    TemplateCreate,
    TemplateImportRequest,
    TemplateOut,
    TemplateUpdate,
    AuditLogOut,
    BillingPlanOut,
    BillingSummaryOut,
    PaymentCheckoutRequest,
    PaymentCheckoutResponse,
    UsageByModelItem,
    UsageDailyItem,
    UsageSummary,
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
from server.app.services.assets import copy_script_asset, current_script_version, touch_asset
from server.app.services.billing import quota_summary
from server.app.services.billing import assert_workspace_quota
from server.app.services.billing import billing_plans
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
    return ScriptAssetOut(
        id=row.id,
        workspace_id=row.workspace_id,
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


def _notification_out(row: Notification):
    return ConsoleNotificationOut(
        id=row.id,
        workspace_id=row.workspace_id,
        user_id=row.user_id,
        title=row.title,
        body=row.body,
        level=row.level,
        status=row.status,
        metadata=row.metadata_json,
        read_at=row.read_at.isoformat(timespec="seconds") if row.read_at else None,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _audit_out(row: AuditLog):
    return AuditLogOut(
        id=row.id,
        actor=row.actor,
        action=row.action,
        target_type=row.target_type,
        target_id=row.target_id,
        workspace_id=row.workspace_id,
        metadata=row.metadata_json,
        created_at=row.created_at.isoformat(timespec="seconds"),
    )


def _asset_created_by_user_id(db: Session, asset: ScriptAsset | ModelAsset):
    task_id = getattr(asset, "task_id", None)
    if not task_id:
        return None
    task = db.get(GenerationTask, task_id)
    return task.created_by_user_id if task else None


def _can_manage_asset(db: Session, user_id: int, member: WorkspaceMember, asset: ScriptAsset | ModelAsset):
    return member.role in CONSOLE_WRITE_ROLES or _asset_created_by_user_id(db, asset) == user_id


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


def _sync_quota_notifications(db: Session, workspace: Workspace):
    summary = quota_summary(db, workspace)
    for warning in summary.get("warnings", []):
        exists = db.execute(
            select(Notification).where(
                Notification.workspace_id == workspace.id,
                Notification.user_id.is_(None),
                Notification.title == "套餐用量提醒",
                Notification.body == warning,
                Notification.status == "unread",
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                Notification(
                    workspace_id=workspace.id,
                    title="套餐用量提醒",
                    body=warning,
                    level="warning",
                    status="unread",
                    metadata_json={"source": "quota", "plan": workspace.plan},
                    created_at=datetime.utcnow(),
                )
            )
    return summary


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


def _usage_scope(member: WorkspaceMember, user_id: int):
    return None if member.role in CONSOLE_WRITE_ROLES else user_id


@router.get("/usage", response_model=UsageSummary)
def console_usage_summary(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    _workspace, member = require_workspace_member(db, user["id"], workspace_id)
    user_scope = _usage_scope(member, user["id"])
    task_stmt = select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace_id)
    succeeded_stmt = select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace_id, GenerationTask.status == "succeeded")
    failed_stmt = select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace_id, GenerationTask.status == "failed")
    usage_stmt = select(
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    ).where(UsageRecord.workspace_id == workspace_id)
    task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
    if user_scope is not None:
        task_stmt = task_stmt.where(GenerationTask.created_by_user_id == user_scope)
        succeeded_stmt = succeeded_stmt.where(GenerationTask.created_by_user_id == user_scope)
        failed_stmt = failed_stmt.where(GenerationTask.created_by_user_id == user_scope)
        task_ids = task_ids.where(GenerationTask.created_by_user_id == user_scope)
    usage_stmt = usage_stmt.where(UsageRecord.task_id.in_(task_ids))
    report_stmt = select(func.count()).select_from(ExecutionReport).where(ExecutionReport.task_id.in_(task_ids))
    usage = db.execute(usage_stmt).one()
    return UsageSummary(
        task_count=int(db.scalar(task_stmt) or 0),
        succeeded_count=int(db.scalar(succeeded_stmt) or 0),
        failed_count=int(db.scalar(failed_stmt) or 0),
        report_count=int(db.scalar(report_stmt) or 0),
        input_tokens=int(usage[0] or 0),
        output_tokens=int(usage[1] or 0),
        total_tokens=int(usage[2] or 0),
        estimated_cost=float(usage[3] or 0),
    )


@router.get("/usage/daily", response_model=list[UsageDailyItem])
def console_usage_daily(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    days: int = Query(default=14, ge=1, le=90),
):
    _workspace, member = require_workspace_member(db, user["id"], workspace_id)
    user_scope = _usage_scope(member, user["id"])
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
    task_stmt = select(GenerationTask).where(
        GenerationTask.workspace_id == workspace_id,
        GenerationTask.created_at >= datetime.combine(start_day, datetime.min.time()),
    )
    if user_scope is not None:
        task_stmt = task_stmt.where(GenerationTask.created_by_user_id == user_scope)
    task_rows = db.execute(task_stmt).scalars().all()
    task_ids = [task.id for task in task_rows]
    for task in task_rows:
        key = task.created_at.date().isoformat()
        if key in buckets:
            buckets[key]["task_count"] += 1
            if task.status == "succeeded":
                buckets[key]["succeeded_count"] += 1
            if task.status == "failed":
                buckets[key]["failed_count"] += 1
    if task_ids:
        report_rows = db.execute(
            select(ExecutionReport).where(
                ExecutionReport.task_id.in_(task_ids),
                ExecutionReport.created_at >= datetime.combine(start_day, datetime.min.time()),
            )
        ).scalars().all()
        for report in report_rows:
            key = report.created_at.date().isoformat()
            if key in buckets:
                buckets[key]["report_count"] += 1
        usage_rows = db.execute(
            select(UsageRecord).where(
                UsageRecord.task_id.in_(task_ids),
                UsageRecord.created_at >= datetime.combine(start_day, datetime.min.time()),
            )
        ).scalars().all()
        for usage in usage_rows:
            key = usage.created_at.date().isoformat()
            if key in buckets:
                buckets[key]["total_tokens"] += int(usage.total_tokens or 0)
                buckets[key]["estimated_cost"] += float(usage.estimated_cost or 0)
    return [UsageDailyItem(day=day, **values) for day, values in buckets.items()]


@router.get("/usage/by-model", response_model=list[UsageByModelItem])
def console_usage_by_model(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    _workspace, member = require_workspace_member(db, user["id"], workspace_id)
    task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
    if member.role not in CONSOLE_WRITE_ROLES:
        task_ids = task_ids.where(GenerationTask.created_by_user_id == user["id"])
    stmt = select(
        UsageRecord.provider,
        UsageRecord.model,
        func.count(UsageRecord.id),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    ).where(UsageRecord.workspace_id == workspace_id, UsageRecord.task_id.in_(task_ids)).group_by(UsageRecord.provider, UsageRecord.model)
    rows = db.execute(stmt).all()
    return [
        UsageByModelItem(
            provider=row[0] or "openai-compatible",
            model=row[1] or "",
            request_count=int(row[2] or 0),
            input_tokens=int(row[3] or 0),
            output_tokens=int(row[4] or 0),
            total_tokens=int(row[5] or 0),
            estimated_cost=float(row[6] or 0),
        )
        for row in rows
    ]


@router.get("/usage/by-member", response_model=list[ConsoleUsageMemberItem])
def console_usage_by_member(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    _workspace, member = require_workspace_member(db, user["id"], workspace_id)
    if member.role not in CONSOLE_WRITE_ROLES:
        user_ids = [user["id"]]
    else:
        user_ids = [
            row.user_id
            for row in db.execute(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id, WorkspaceMember.status == "active")).scalars().all()
        ]
    result = []
    for user_id in user_ids:
        row_user = db.get(User, user_id)
        task_ids = select(GenerationTask.id).where(GenerationTask.workspace_id == workspace_id, GenerationTask.created_by_user_id == user_id)
        task_count = db.scalar(select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace_id, GenerationTask.created_by_user_id == user_id)) or 0
        usage = db.execute(
            select(
                func.coalesce(func.sum(UsageRecord.input_tokens), 0),
                func.coalesce(func.sum(UsageRecord.output_tokens), 0),
                func.coalesce(func.sum(UsageRecord.total_tokens), 0),
                func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
            ).where(UsageRecord.workspace_id == workspace_id, UsageRecord.task_id.in_(task_ids))
        ).one()
        result.append(
            ConsoleUsageMemberItem(
                user_id=user_id,
                email=row_user.email if row_user else "",
                display_name=row_user.display_name if row_user else "",
                task_count=int(task_count),
                input_tokens=int(usage[0] or 0),
                output_tokens=int(usage[1] or 0),
                total_tokens=int(usage[2] or 0),
                estimated_cost=float(usage[3] or 0),
            )
        )
    return result


@router.get("/usage/by-project", response_model=list[ConsoleUsageProjectItem])
def console_usage_by_project(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    _workspace, member = require_workspace_member(db, user["id"], workspace_id)
    task_stmt = select(
        GenerationTask.project_id,
        func.count(GenerationTask.id),
        func.coalesce(func.sum(UsageRecord.input_tokens), 0),
        func.coalesce(func.sum(UsageRecord.output_tokens), 0),
        func.coalesce(func.sum(UsageRecord.total_tokens), 0),
        func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
    ).outerjoin(UsageRecord, UsageRecord.task_id == GenerationTask.id).where(GenerationTask.workspace_id == workspace_id)
    if member.role not in CONSOLE_WRITE_ROLES:
        task_stmt = task_stmt.where(GenerationTask.created_by_user_id == user["id"])
    rows = db.execute(task_stmt.group_by(GenerationTask.project_id).order_by(desc(func.count(GenerationTask.id)))).all()
    return [
        ConsoleUsageProjectItem(
            project_id=row[0] or "未归档项目",
            task_count=int(row[1] or 0),
            input_tokens=int(row[2] or 0),
            output_tokens=int(row[3] or 0),
            total_tokens=int(row[4] or 0),
            estimated_cost=float(row[5] or 0),
        )
        for row in rows
    ]


@router.get("/billing/plans", response_model=list[BillingPlanOut])
def console_billing_plans(db: Session = Depends(get_db), user=Depends(authenticate_user)):
    return billing_plans()


@router.get("/billing/summary", response_model=BillingSummaryOut)
def console_billing_summary(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace, _member = require_workspace_member(db, user["id"], workspace_id)
    summary = _sync_quota_notifications(db, workspace)
    db.commit()
    return BillingSummaryOut(workspaces=[summary])


@router.post("/billing/checkout", response_model=PaymentCheckoutResponse)
def console_payment_checkout(payload: PaymentCheckoutRequest, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace, _member = require_workspace_member(db, user["id"], payload.workspace_id, CONSOLE_WRITE_ROLES)
    if payload.plan not in {item["name"] for item in billing_plans()}:
        raise HTTPException(status_code=400, detail="Unknown billing plan.")
    _audit(
        db,
        "console.billing.checkout.requested",
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


@router.get("/audit-logs", response_model=list[AuditLogOut])
def console_audit_logs(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    limit: int = Query(default=80, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    action: str = "",
):
    require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    stmt = select(AuditLog).where(AuditLog.workspace_id == workspace_id).order_by(desc(AuditLog.id)).offset(offset).limit(limit)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    rows = db.execute(stmt).scalars().all()
    return [_audit_out(row) for row in rows]


@router.get("/notifications", response_model=list[ConsoleNotificationOut])
def list_notifications(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    unread_only: bool = False,
):
    require_workspace_member(db, user["id"], workspace_id)
    stmt = select(Notification).where(
        Notification.workspace_id == workspace_id,
        or_(Notification.user_id.is_(None), Notification.user_id == user["id"]),
    )
    if unread_only:
        stmt = stmt.where(Notification.status == "unread")
    rows = db.execute(stmt.order_by(desc(Notification.id)).limit(100)).scalars().all()
    return [_notification_out(row) for row in rows]


@router.post("/notifications/{notification_id}/read", response_model=ConsoleNotificationOut)
def read_notification(notification_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(Notification, notification_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Notification not found.")
    require_workspace_member(db, user["id"], item.workspace_id)
    if item.user_id not in {None, user["id"]}:
        raise HTTPException(status_code=403, detail="Notification is not visible to current user.")
    item.status = "read"
    item.read_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _notification_out(item)


@router.post("/notifications/read-all")
def read_all_notifications(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id)
    rows = db.execute(
        select(Notification).where(
            Notification.workspace_id == workspace_id,
            Notification.status == "unread",
            or_(Notification.user_id.is_(None), Notification.user_id == user["id"]),
        )
    ).scalars().all()
    now = datetime.utcnow()
    for item in rows:
        item.status = "read"
        item.read_at = now
    db.commit()
    return {"ok": True, "count": len(rows)}


@router.get("/templates", response_model=list[TemplateOut])
def list_templates(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    include_disabled: bool = False,
    q: str = "",
):
    require_workspace_member(db, user["id"], workspace_id)
    stmt = select(Template).where(or_(Template.workspace_id.is_(None), Template.workspace_id == workspace_id))
    if not include_disabled:
        stmt = stmt.where(Template.enabled.is_(True))
    if q:
        like = "%{}%".format(q.strip())
        stmt = stmt.where(
            or_(
                Template.name.ilike(like),
                Template.category.ilike(like),
                Template.prompt.ilike(like),
            )
        )
    rows = db.execute(stmt.order_by(Template.category, Template.name)).scalars().all()
    return [_template_out(row) for row in rows]


@router.get("/templates/export", response_model=list[TemplateOut])
def export_templates(workspace_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], workspace_id)
    rows = db.execute(
        select(Template)
        .where(or_(Template.workspace_id.is_(None), Template.workspace_id == workspace_id))
        .order_by(Template.category, Template.name)
    ).scalars().all()
    _audit(db, "console.template.export", "template", "workspace", workspace_id, {"count": len(rows)})
    db.commit()
    return [_template_out(row) for row in rows]


@router.post("/templates/import", response_model=list[TemplateOut])
def import_templates(payload: TemplateImportRequest, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    workspace_ids = {item.workspace_id for item in payload.templates}
    if len(workspace_ids) != 1 or None in workspace_ids:
        raise HTTPException(status_code=422, detail="Console imports must target one enterprise workspace.")
    workspace_id = int(next(iter(workspace_ids)))
    workspace, _member = require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    imported: list[TemplateOut] = []
    for template in payload.templates:
        existing = db.execute(
            select(Template).where(
                Template.name == template.name,
                Template.category == template.category,
                Template.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if existing is None:
            assert_workspace_quota(db, workspace, "templates")
            existing = Template(
                workspace_id=workspace_id,
                name=template.name,
                category=template.category,
                prompt=template.prompt,
                enabled=template.enabled,
            )
            db.add(existing)
            db.flush()
        else:
            existing.prompt = template.prompt
            existing.enabled = template.enabled
        _audit(db, "console.template.import", "template", existing.id, workspace_id, {"name": template.name, "category": template.category})
        imported.append(_template_out(existing))
    db.commit()
    return imported


@router.post("/templates", response_model=TemplateOut)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    if payload.workspace_id is None:
        raise HTTPException(status_code=422, detail="Console templates must belong to a workspace.")
    workspace, _member = require_workspace_member(db, user["id"], payload.workspace_id, CONSOLE_WRITE_ROLES)
    assert_workspace_quota(db, workspace, "templates")
    item = Template(
        workspace_id=workspace.id,
        name=payload.name.strip(),
        category=payload.category.strip() or "General",
        prompt=payload.prompt,
        enabled=payload.enabled,
    )
    db.add(item)
    db.flush()
    _audit(db, "console.template.create", "template", item.id, workspace.id, {"name": item.name, "category": item.category})
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.put("/templates/{template_id}", response_model=TemplateOut)
def update_template(template_id: int, payload: TemplateUpdate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    if item.workspace_id is None:
        raise HTTPException(status_code=403, detail="System templates are read-only in console.")
    require_workspace_member(db, user["id"], item.workspace_id, CONSOLE_WRITE_ROLES)
    for field in ("name", "category", "prompt", "enabled"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value.strip() if isinstance(value, str) else value)
    _audit(db, "console.template.update", "template", item.id, item.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.delete("/templates/{template_id}")
def delete_template(template_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(Template, template_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Template not found.")
    if item.workspace_id is None:
        raise HTTPException(status_code=403, detail="System templates are read-only in console.")
    workspace_id = item.workspace_id
    name = item.name
    require_workspace_member(db, user["id"], workspace_id, CONSOLE_WRITE_ROLES)
    db.delete(item)
    _audit(db, "console.template.delete", "template", template_id, workspace_id, {"name": name})
    db.commit()
    return {"ok": True}


@router.get("/script-assets", response_model=list[ScriptAssetOut])
def list_script_assets(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    q: str = "",
    favorite: bool | None = None,
    status: str = "",
):
    require_workspace_member(db, user["id"], workspace_id)
    stmt = select(ScriptAsset).where(ScriptAsset.workspace_id == workspace_id)
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
def list_script_versions(asset_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    require_workspace_member(db, user["id"], asset.workspace_id)
    rows = db.execute(
        select(ScriptVersion).where(ScriptVersion.asset_id == asset_id).order_by(desc(ScriptVersion.version))
    ).scalars().all()
    return [_script_version_out(row) for row in rows]


@router.put("/script-assets/{asset_id}", response_model=ScriptAssetOut)
def update_script_asset(asset_id: int, payload: ScriptAssetUpdate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    _workspace, member = require_workspace_member(db, user["id"], asset.workspace_id)
    if not _can_manage_asset(db, user["id"], member, asset):
        raise HTTPException(status_code=403, detail="Only workspace admins or the creator can update this asset.")
    for field in ("name", "description", "favorite", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(asset, field, value)
    if payload.tags is not None:
        asset.tags_json = payload.tags
    if payload.metadata is not None:
        asset.metadata_json = payload.metadata
    touch_asset(asset)
    _audit(db, "console.script_asset.update", "script_asset", asset.id, asset.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/favorite", response_model=ScriptAssetOut)
def favorite_script_asset(asset_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    require_workspace_member(db, user["id"], asset.workspace_id, CONSOLE_TASK_ROLES)
    asset.favorite = not asset.favorite
    touch_asset(asset)
    _audit(db, "console.script_asset.favorite", "script_asset", asset.id, asset.workspace_id, {"favorite": asset.favorite})
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/copy", response_model=ScriptAssetOut)
def copy_console_script_asset(asset_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    require_workspace_member(db, user["id"], asset.workspace_id, CONSOLE_TASK_ROLES)
    copied = copy_script_asset(db, asset, "user:{}".format(user["id"]))
    _audit(db, "console.script_asset.copy", "script_asset", copied.id, copied.workspace_id, {"source_asset_id": asset.id})
    db.commit()
    db.refresh(copied)
    return _script_asset_out(db, copied)


@router.post("/script-assets/{asset_id}/rollback", response_model=ScriptAssetOut)
def rollback_script_asset(asset_id: int, payload: ScriptRollbackRequest, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    asset = db.get(ScriptAsset, asset_id)
    version = db.get(ScriptVersion, payload.version_id)
    if asset is None or version is None or version.asset_id != asset_id:
        raise HTTPException(status_code=404, detail="Script asset version not found.")
    _workspace, member = require_workspace_member(db, user["id"], asset.workspace_id)
    if not _can_manage_asset(db, user["id"], member, asset):
        raise HTTPException(status_code=403, detail="Only workspace admins or the creator can rollback this asset.")
    asset.current_version_id = version.id
    touch_asset(asset)
    _audit(db, "console.script_asset.rollback", "script_asset", asset.id, asset.workspace_id, {"version_id": version.id, "version": version.version})
    db.commit()
    db.refresh(asset)
    return _script_asset_out(db, asset)


@router.post("/script-assets/{asset_id}/reuse-template", response_model=TemplateOut)
def reuse_script_asset_as_template(
    asset_id: int,
    payload: ScriptReuseTemplateRequest,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
):
    asset = db.get(ScriptAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Script asset not found.")
    _workspace, member = require_workspace_member(db, user["id"], asset.workspace_id)
    if not _can_manage_asset(db, user["id"], member, asset):
        raise HTTPException(status_code=403, detail="Only workspace admins or the creator can reuse this asset as a template.")
    version = current_script_version(db, asset)
    if version is None:
        raise HTTPException(status_code=409, detail="Script asset has no version.")
    workspace_id = payload.workspace_id if payload.workspace_id is not None else asset.workspace_id
    workspace, _member = require_workspace_member(db, user["id"], workspace_id, CONSOLE_TASK_ROLES)
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
    _audit(db, "console.script_asset.reuse_template", "template", item.id, workspace_id, {"asset_id": asset.id, "version_id": version.id})
    db.commit()
    db.refresh(item)
    return _template_out(item)


@router.get("/model-assets", response_model=list[ModelAssetOut])
def list_model_assets(
    workspace_id: int,
    db: Session = Depends(get_db),
    user=Depends(authenticate_user),
    q: str = "",
    status: str = "",
):
    require_workspace_member(db, user["id"], workspace_id)
    stmt = select(ModelAsset).where(ModelAsset.workspace_id == workspace_id)
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
def create_model_asset(payload: ModelAssetCreate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    require_workspace_member(db, user["id"], payload.workspace_id, CONSOLE_WRITE_ROLES)
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
    _audit(db, "console.model_asset.create", "model_asset", item.id, item.workspace_id, {"name": item.name})
    db.commit()
    db.refresh(item)
    return _model_asset_out(item)


@router.put("/model-assets/{asset_id}", response_model=ModelAssetOut)
def update_model_asset(asset_id: int, payload: ModelAssetUpdate, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(ModelAsset, asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model asset not found.")
    _workspace, member = require_workspace_member(db, user["id"], item.workspace_id)
    if not _can_manage_asset(db, user["id"], member, item):
        raise HTTPException(status_code=403, detail="Only workspace admins or the creator can update this asset.")
    for field in ("script_asset_id", "task_id", "project_id", "name", "file_name", "file_type", "storage_uri", "preview_uri", "checksum", "size_bytes", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(item, field, value)
    if payload.metadata is not None:
        item.metadata_json = payload.metadata
    touch_asset(item)
    _audit(db, "console.model_asset.update", "model_asset", item.id, item.workspace_id, payload.model_dump(exclude_none=True))
    db.commit()
    db.refresh(item)
    return _model_asset_out(item)


@router.delete("/model-assets/{asset_id}")
def delete_model_asset(asset_id: int, db: Session = Depends(get_db), user=Depends(authenticate_user)):
    item = db.get(ModelAsset, asset_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Model asset not found.")
    require_workspace_member(db, user["id"], item.workspace_id, CONSOLE_WRITE_ROLES)
    workspace_id = item.workspace_id
    db.delete(item)
    _audit(db, "console.model_asset.delete", "model_asset", asset_id, workspace_id, {})
    db.commit()
    return {"ok": True}


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
