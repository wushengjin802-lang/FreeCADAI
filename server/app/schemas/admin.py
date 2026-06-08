"""Schemas for admin management APIs."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = "common"
    prompt: str = Field(..., min_length=1)
    enabled: bool = True
    workspace_id: Optional[int] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    prompt: Optional[str] = None
    enabled: Optional[bool] = None


class TemplateOut(BaseModel):
    id: int
    workspace_id: Optional[int] = None
    name: str
    category: str
    prompt: str
    enabled: bool


class ApiKeyCreate(BaseModel):
    workspace_id: int = 1
    name: str = "Plugin Key"


class ApiKeyCreateResponse(BaseModel):
    id: int
    api_key: str
    prefix: str


class ApiKeyOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    prefix: str
    status: str
    last_used_at: Optional[str] = None
    created_at: str


class TemplateImportRequest(BaseModel):
    templates: List[TemplateCreate]


class TaskListItem(BaseModel):
    id: int
    workspace_id: int
    project_id: str
    action: str
    modeling_mode: str
    prompt: str
    model: str
    status: str
    latency_ms: int
    created_at: str


class TaskDetail(BaseModel):
    task: Dict[str, Any]
    scripts: List[Dict[str, Any]]
    reports: List[Dict[str, Any]]


class UsageSummary(BaseModel):
    task_count: int
    succeeded_count: int
    failed_count: int
    report_count: int


class UsageDailyItem(BaseModel):
    day: str
    task_count: int
    succeeded_count: int
    failed_count: int
    report_count: int


class WorkspaceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    plan: str = "free"
    status: str = "active"


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    status: Optional[str] = None


class WorkspaceOut(BaseModel):
    id: int
    name: str
    plan: str
    status: str
    created_at: str
    api_key_count: int = 0
    task_count: int = 0


class AuditLogOut(BaseModel):
    id: int
    actor: str
    action: str
    target_type: str
    target_id: str
    workspace_id: Optional[int] = None
    metadata: Dict[str, Any]
    created_at: str


class AdminLoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1)


class AdminLoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: Dict[str, Any]


class AdminUserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=8)
    role: str = "operator"
    status: str = "active"


class AdminUserUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = Field(default=None, min_length=8)


class AdminPasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class AdminUserOut(BaseModel):
    id: int
    username: str
    role: str
    status: str
    last_login_at: Optional[str] = None
    created_at: str
