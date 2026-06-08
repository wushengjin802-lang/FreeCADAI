"""Schemas for plugin-facing SaaS APIs."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    project_id: str = ""


class VerifyResponse(BaseModel):
    ok: bool
    workspace_id: int
    message: str
    workspace_name: str = ""
    workspace_plan: str = ""
    workspace_status: str = ""
    key_status: str = "active"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: str = ""
    modeling_mode: str = "3d_solid"
    project_id: str = ""


class RepairRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: str = ""
    failed_script: str = Field(..., min_length=1)
    error_text: str = Field(..., min_length=1)
    modeling_mode: str = "3d_solid"
    project_id: str = ""


class RegenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    context: str = ""
    parameters: str = Field(..., min_length=1)
    modeling_mode: str = "3d_solid"
    project_id: str = ""


class GenerationResponse(BaseModel):
    task_id: int
    script_id: int
    summary: str
    parameters: Dict[str, Any]
    script: str
    expected_objects: List[str]
    notes: List[str]


class ExecutionReportRequest(BaseModel):
    task_id: int
    script_id: Optional[int] = None
    status: str
    plugin_version: str = ""
    freecad_version: Any = None
    document_name: str = ""
    object_count: int = 0
    new_objects: List[str] = Field(default_factory=list)
    error_trace: str = ""


class ExecutionReportResponse(BaseModel):
    ok: bool
    report_id: int


class PluginTemplate(BaseModel):
    id: str
    name: str
    category: str = "common"
    prompt: str


class PluginTemplatesResponse(BaseModel):
    templates: List[PluginTemplate]


class PluginAccountLoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class PluginAccountLoginResponse(BaseModel):
    token: str
    expires_at: str
    user: Dict[str, Any]


class PluginWorkspaceItem(BaseModel):
    id: int
    name: str
    plan: str
    status: str
    api_key_count: int = 0


class PluginWorkspacesResponse(BaseModel):
    workspaces: List[PluginWorkspaceItem]


class PluginBindWorkspaceRequest(BaseModel):
    workspace_id: int
    key_name: str = "FreeCAD Plugin Key"


class PluginBindWorkspaceResponse(BaseModel):
    api_key: str
    prefix: str
    workspace: PluginWorkspaceItem
