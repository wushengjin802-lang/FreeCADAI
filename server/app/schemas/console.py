"""Schemas for enterprise/user console APIs."""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ConsoleUserOut(BaseModel):
    id: int
    email: str
    phone: str = ""
    display_name: str
    status: str
    last_login_at: Optional[str] = None
    created_at: str


class ConsoleWorkspaceOut(BaseModel):
    id: int
    name: str
    plan: str
    status: str
    role: str
    created_at: str
    member_count: int = 0
    api_key_count: int = 0
    task_count: int = 0
    asset_count: int = 0
    quota: Optional[Dict[str, Any]] = None


class ConsoleLoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=1)


class ConsoleRegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=8)
    display_name: str = Field(..., min_length=1, max_length=128)
    workspace_name: Optional[str] = Field(default=None, max_length=128)


class ConsoleAuthResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: str
    user: ConsoleUserOut
    workspaces: list[ConsoleWorkspaceOut] = []


class ConsolePasswordChange(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8)


class ConsoleWorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)


class ConsoleMemberOut(BaseModel):
    id: int
    workspace_id: int
    user_id: int
    email: str
    display_name: str
    role: str
    status: str
    joined_at: Optional[str] = None
    created_at: str


class ConsoleInviteCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    role: str = "member"


class ConsoleInviteOut(BaseModel):
    id: int
    workspace_id: int
    email: str
    role: str
    status: str
    expires_at: str
    invite_token: Optional[str] = None
    created_at: str


class ConsoleMemberUpdate(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None


class ConsoleApiKeyCreate(BaseModel):
    workspace_id: int
    name: str = Field(default="FreeCAD Plugin Key", min_length=1, max_length=128)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=3650)
    scopes: list[str] = Field(default_factory=lambda: ["plugin"])


class ConsoleApiKeyOut(BaseModel):
    id: int
    workspace_id: int
    name: str
    prefix: str
    status: str
    scopes: list[str] = []
    created_by_user_id: Optional[int] = None
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_at: str


class ConsoleApiKeyCreateResponse(BaseModel):
    id: int
    api_key: str
    prefix: str
    item: ConsoleApiKeyOut


class ConsoleApiKeyRotateResponse(BaseModel):
    id: int
    api_key: str
    prefix: str
    item: ConsoleApiKeyOut


class ConsolePluginGuideOut(BaseModel):
    workspace_id: int
    workspace_name: str
    saas_base_url: str
    verify_path: str = "/api/v1/plugin/auth/verify"
    login_path: str = "/api/v1/plugin/account/login"
    bind_path: str = "/api/v1/plugin/account/bind-workspace"
