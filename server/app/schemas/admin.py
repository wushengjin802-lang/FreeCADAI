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
