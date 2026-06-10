"""Schemas for admin management APIs."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    category: str = "通用"
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


class ScriptVersionOut(BaseModel):
    id: int
    asset_id: int
    task_id: Optional[int] = None
    version: int
    script: str
    summary: str
    parameters: Dict[str, Any]
    expected_objects: List[Any]
    validation_status: str
    validation_error: str
    created_by: str
    created_at: str


class ScriptAssetOut(BaseModel):
    id: int
    workspace_id: int
    task_id: Optional[int] = None
    current_version_id: Optional[int] = None
    current_version: Optional[int] = None
    name: str
    description: str
    modeling_mode: str
    project_id: str
    source: str
    favorite: bool
    status: str
    tags: List[str]
    metadata: Dict[str, Any]
    summary: str = ""
    script_preview: str = ""
    created_at: str
    updated_at: str


class ScriptAssetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    favorite: Optional[bool] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class ScriptRollbackRequest(BaseModel):
    version_id: int


class ScriptReuseTemplateRequest(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    category: str = "复用脚本"
    workspace_id: Optional[int] = None


class ModelAssetCreate(BaseModel):
    workspace_id: int
    script_asset_id: Optional[int] = None
    task_id: Optional[int] = None
    project_id: str = ""
    name: str = Field(..., min_length=1, max_length=128)
    file_name: str = ""
    file_type: str = ""
    storage_uri: str = ""
    preview_uri: str = ""
    checksum: str = ""
    size_bytes: int = 0
    status: str = "active"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ModelAssetUpdate(BaseModel):
    script_asset_id: Optional[int] = None
    task_id: Optional[int] = None
    project_id: Optional[str] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    file_name: Optional[str] = None
    file_type: Optional[str] = None
    storage_uri: Optional[str] = None
    preview_uri: Optional[str] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ModelAssetOut(BaseModel):
    id: int
    workspace_id: int
    script_asset_id: Optional[int] = None
    task_id: Optional[int] = None
    project_id: str
    name: str
    file_name: str
    file_type: str
    storage_uri: str
    preview_uri: str
    checksum: str
    size_bytes: int
    status: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


class UsageSummary(BaseModel):
    task_count: int
    succeeded_count: int
    failed_count: int
    report_count: int
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0


class UsageDailyItem(BaseModel):
    day: str
    task_count: int
    succeeded_count: int
    failed_count: int
    report_count: int
    total_tokens: int = 0
    estimated_cost: float = 0


class UsageByModelItem(BaseModel):
    provider: str
    model: str
    request_count: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: float


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
    quota: Optional[Dict[str, Any]] = None


class BillingPlanOut(BaseModel):
    name: str
    monthly_price_cents: int
    limits: Dict[str, Optional[int]]


class BillingSummaryOut(BaseModel):
    workspaces: List[Dict[str, Any]]


class PaymentCheckoutRequest(BaseModel):
    workspace_id: int
    plan: str


class PaymentCheckoutResponse(BaseModel):
    ok: bool
    provider: str
    checkout_url: Optional[str] = None
    message: str


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
