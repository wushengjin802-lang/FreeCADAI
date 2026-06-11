import type {
  AdminPrincipal,
  AdminUser,
  ApiKey,
  ApiKeyCreateResponse,
  AuditLog,
  BillingPlan,
  BillingSummary,
  ConsoleApiKeyCreateResponse,
  ConsoleAuthResponse,
  ConsoleInvite,
  ConsoleMeResponse,
  ConsoleMember,
  ConsoleNotification,
  ConsolePluginGuide,
  ConsoleTaskActionResponse,
  ConsoleTaskDetail,
  ConsoleTaskListItem,
  ConsoleTaskSubmitResponse,
  ConsoleUsageMemberItem,
  ConsoleUsageProjectItem,
  ConsoleWorkspace,
  Health,
  LoginResponse,
  ModelAsset,
  ScriptAsset,
  ScriptVersion,
  TaskDetail,
  TaskListItem,
  Template,
  UsageByModelItem,
  UsageDailyItem,
  UsageSummary,
  Workspace
} from "./types";

type QueryValue = string | number | boolean | null | undefined;

function currentApiPrefix() {
  if (process.env.NEXT_PUBLIC_API_PREFIX) return process.env.NEXT_PUBLIC_API_PREFIX;
  if (typeof window !== "undefined" && window.location.pathname.startsWith("/freecadai")) {
    return "/freecadai";
  }
  return "";
}

function appPath(path: string) {
  return `${currentApiPrefix()}${path}`;
}

function toQuery(params: Record<string, QueryValue>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function parseError(response: Response) {
  const text = await response.text();
  try {
    const data = JSON.parse(text) as { detail?: unknown };
    return typeof data.detail === "string" ? data.detail : text;
  } catch {
    return text || response.statusText;
  }
}

export async function apiFetch<T>(path: string, token: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(appPath(path), {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...(init.headers || {})
    }
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json() as Promise<T>;
}

export async function login(username: string, password: string) {
  const response = await fetch(appPath("/api/v1/admin/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json() as Promise<LoginResponse>;
}

export async function consoleLogin(email: string, password: string) {
  const response = await fetch(appPath("/api/v1/console/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password })
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json() as Promise<ConsoleAuthResponse>;
}

export async function consoleRegister(body: { email: string; password: string; display_name: string; workspace_name?: string }) {
  const response = await fetch(appPath("/api/v1/console/auth/register"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json() as Promise<ConsoleAuthResponse>;
}

export async function consoleAcceptInvite(inviteToken: string, body: { email: string; password: string; display_name: string; workspace_name?: string }) {
  const response = await fetch(appPath(`/api/v1/console/invites/${inviteToken}/accept`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json() as Promise<ConsoleAuthResponse>;
}

export const consoleApi = {
  me: (token: string) => apiFetch<ConsoleMeResponse>("/api/v1/console/auth/me", token),
  logout: (token: string) => apiFetch<{ ok: boolean }>("/api/v1/console/auth/logout", token, { method: "POST" }),
  changePassword: (token: string, body: { current_password: string; new_password: string }) =>
    apiFetch<{ ok: boolean }>("/api/v1/console/auth/password", token, { method: "PUT", body: JSON.stringify(body) }),
  workspaces: (token: string) => apiFetch<ConsoleWorkspace[]>("/api/v1/console/workspaces", token),
  workspace: (token: string, workspaceId: number) => apiFetch<ConsoleWorkspace>(`/api/v1/console/workspaces/${workspaceId}`, token),
  updateWorkspace: (token: string, workspaceId: number, body: { name?: string }) =>
    apiFetch<ConsoleWorkspace>(`/api/v1/console/workspaces/${workspaceId}`, token, { method: "PUT", body: JSON.stringify(body) }),
  members: (token: string, workspaceId: number) =>
    apiFetch<ConsoleMember[]>(`/api/v1/console/workspaces/${workspaceId}/members`, token),
  inviteMember: (token: string, workspaceId: number, body: { email: string; role: string }) =>
    apiFetch<ConsoleInvite>(`/api/v1/console/workspaces/${workspaceId}/invites`, token, { method: "POST", body: JSON.stringify(body) }),
  updateMember: (token: string, workspaceId: number, memberId: number, body: Partial<{ role: string; status: string }>) =>
    apiFetch<ConsoleMember>(`/api/v1/console/workspaces/${workspaceId}/members/${memberId}`, token, { method: "PUT", body: JSON.stringify(body) }),
  removeMember: (token: string, workspaceId: number, memberId: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/console/workspaces/${workspaceId}/members/${memberId}`, token, { method: "DELETE" }),
  apiKeys: (token: string, workspaceId: number) =>
    apiFetch<ApiKey[]>(`/api/v1/console/api-keys${toQuery({ workspace_id: workspaceId })}`, token),
  createApiKey: (token: string, body: { workspace_id: number; name: string; expires_in_days?: number | null; scopes?: string[] }) =>
    apiFetch<ConsoleApiKeyCreateResponse>("/api/v1/console/api-keys", token, { method: "POST", body: JSON.stringify(body) }),
  enableApiKey: (token: string, id: number) =>
    apiFetch<ApiKey>(`/api/v1/console/api-keys/${id}/enable`, token, { method: "POST" }),
  disableApiKey: (token: string, id: number) =>
    apiFetch<ApiKey>(`/api/v1/console/api-keys/${id}/disable`, token, { method: "POST" }),
  rotateApiKey: (token: string, id: number) =>
    apiFetch<ConsoleApiKeyCreateResponse>(`/api/v1/console/api-keys/${id}/rotate`, token, { method: "POST" }),
  pluginGuide: (token: string, workspaceId: number) =>
    apiFetch<ConsolePluginGuide>(`/api/v1/console/plugin/connection-guide${toQuery({ workspace_id: workspaceId })}`, token),
  tasks: (
    token: string,
    params: { workspace_id: number; limit?: number; offset?: number; q?: string; status?: string; action?: string; modeling_mode?: string; mine?: boolean }
  ) => apiFetch<ConsoleTaskListItem[]>(`/api/v1/console/tasks${toQuery({ limit: 50, offset: 0, ...params })}`, token),
  createTask: (token: string, body: { workspace_id: number; prompt: string; context?: string; modeling_mode?: string; project_id?: string; template_id?: number | null }) =>
    apiFetch<ConsoleTaskSubmitResponse>("/api/v1/console/tasks", token, { method: "POST", body: JSON.stringify(body) }),
  taskDetail: (token: string, id: number) => apiFetch<ConsoleTaskDetail>(`/api/v1/console/tasks/${id}`, token),
  cancelTask: (token: string, id: number) =>
    apiFetch<ConsoleTaskActionResponse>(`/api/v1/console/tasks/${id}/cancel`, token, { method: "POST" }),
  retryTask: (token: string, id: number) =>
    apiFetch<ConsoleTaskActionResponse>(`/api/v1/console/tasks/${id}/retry`, token, { method: "POST" }),
  templates: (token: string, workspaceId: number) =>
    apiFetch<Template[]>(`/api/v1/console/templates${toQuery({ workspace_id: workspaceId })}`, token),
  templateCenter: (token: string, params: { workspace_id: number; include_disabled?: boolean; q?: string }) =>
    apiFetch<Template[]>(`/api/v1/console/templates${toQuery(params)}`, token),
  createTemplate: (token: string, body: Omit<Template, "id">) =>
    apiFetch<Template>("/api/v1/console/templates", token, { method: "POST", body: JSON.stringify(body) }),
  updateTemplate: (token: string, id: number, body: Partial<Omit<Template, "id" | "workspace_id">>) =>
    apiFetch<Template>(`/api/v1/console/templates/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  deleteTemplate: (token: string, id: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/console/templates/${id}`, token, { method: "DELETE" }),
  importTemplates: (token: string, templates: Array<Omit<Template, "id">>) =>
    apiFetch<Template[]>("/api/v1/console/templates/import", token, { method: "POST", body: JSON.stringify({ templates }) }),
  exportTemplates: (token: string, workspaceId: number) =>
    apiFetch<Template[]>(`/api/v1/console/templates/export${toQuery({ workspace_id: workspaceId })}`, token),
  scriptAssets: (token: string, params: { workspace_id: number; q?: string; favorite?: boolean | null; status?: string }) =>
    apiFetch<ScriptAsset[]>(`/api/v1/console/script-assets${toQuery(params)}`, token),
  scriptVersions: (token: string, assetId: number) =>
    apiFetch<ScriptVersion[]>(`/api/v1/console/script-assets/${assetId}/versions`, token),
  updateScriptAsset: (token: string, id: number, body: Partial<Pick<ScriptAsset, "name" | "description" | "favorite" | "status" | "tags" | "metadata">>) =>
    apiFetch<ScriptAsset>(`/api/v1/console/script-assets/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  favoriteScriptAsset: (token: string, id: number) =>
    apiFetch<ScriptAsset>(`/api/v1/console/script-assets/${id}/favorite`, token, { method: "POST" }),
  copyScriptAsset: (token: string, id: number) =>
    apiFetch<ScriptAsset>(`/api/v1/console/script-assets/${id}/copy`, token, { method: "POST" }),
  rollbackScriptAsset: (token: string, id: number, versionId: number) =>
    apiFetch<ScriptAsset>(`/api/v1/console/script-assets/${id}/rollback`, token, { method: "POST", body: JSON.stringify({ version_id: versionId }) }),
  reuseScriptAssetTemplate: (token: string, id: number, body: { name?: string; category: string; workspace_id?: number | null }) =>
    apiFetch<Template>(`/api/v1/console/script-assets/${id}/reuse-template`, token, { method: "POST", body: JSON.stringify(body) }),
  modelAssets: (token: string, params: { workspace_id: number; q?: string; status?: string }) =>
    apiFetch<ModelAsset[]>(`/api/v1/console/model-assets${toQuery(params)}`, token),
  createModelAsset: (token: string, body: Omit<ModelAsset, "id" | "created_at" | "updated_at">) =>
    apiFetch<ModelAsset>("/api/v1/console/model-assets", token, { method: "POST", body: JSON.stringify(body) }),
  updateModelAsset: (token: string, id: number, body: Partial<Omit<ModelAsset, "id" | "workspace_id" | "created_at" | "updated_at">>) =>
    apiFetch<ModelAsset>(`/api/v1/console/model-assets/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  deleteModelAsset: (token: string, id: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/console/model-assets/${id}`, token, { method: "DELETE" }),
  usage: (token: string, workspaceId: number) =>
    apiFetch<UsageSummary>(`/api/v1/console/usage${toQuery({ workspace_id: workspaceId })}`, token),
  usageDaily: (token: string, workspaceId: number) =>
    apiFetch<UsageDailyItem[]>(`/api/v1/console/usage/daily${toQuery({ workspace_id: workspaceId, days: 14 })}`, token),
  usageByModel: (token: string, workspaceId: number) =>
    apiFetch<UsageByModelItem[]>(`/api/v1/console/usage/by-model${toQuery({ workspace_id: workspaceId })}`, token),
  usageByMember: (token: string, workspaceId: number) =>
    apiFetch<ConsoleUsageMemberItem[]>(`/api/v1/console/usage/by-member${toQuery({ workspace_id: workspaceId })}`, token),
  usageByProject: (token: string, workspaceId: number) =>
    apiFetch<ConsoleUsageProjectItem[]>(`/api/v1/console/usage/by-project${toQuery({ workspace_id: workspaceId })}`, token),
  billingPlans: (token: string) => apiFetch<BillingPlan[]>("/api/v1/console/billing/plans", token),
  billingSummary: (token: string, workspaceId: number) =>
    apiFetch<BillingSummary>(`/api/v1/console/billing/summary${toQuery({ workspace_id: workspaceId })}`, token),
  createCheckout: (token: string, body: { workspace_id: number; plan: string }) =>
    apiFetch<{ ok: boolean; provider: string; checkout_url?: string | null; message: string }>("/api/v1/console/billing/checkout", token, { method: "POST", body: JSON.stringify(body) }),
  auditLogs: (token: string, workspaceId: number, action?: string) =>
    apiFetch<AuditLog[]>(`/api/v1/console/audit-logs${toQuery({ workspace_id: workspaceId, limit: 100, action })}`, token),
  notifications: (token: string, workspaceId: number, unreadOnly?: boolean) =>
    apiFetch<ConsoleNotification[]>(`/api/v1/console/notifications${toQuery({ workspace_id: workspaceId, unread_only: unreadOnly })}`, token),
  readNotification: (token: string, id: number) =>
    apiFetch<ConsoleNotification>(`/api/v1/console/notifications/${id}/read`, token, { method: "POST" }),
  readAllNotifications: (token: string, workspaceId: number) =>
    apiFetch<{ ok: boolean; count: number }>(`/api/v1/console/notifications/read-all${toQuery({ workspace_id: workspaceId })}`, token, { method: "POST" })
};

export const adminApi = {
  me: (token: string) => apiFetch<AdminPrincipal>("/api/v1/admin/auth/me", token),
  logout: (token: string) => apiFetch<{ ok: boolean }>("/api/v1/admin/auth/logout", token, { method: "POST" }),
  health: async () => {
    const response = await fetch(appPath("/health"));
    if (!response.ok) throw new Error(await parseError(response));
    return response.json() as Promise<Health>;
  },
  workspaces: (token: string) => apiFetch<Workspace[]>("/api/v1/admin/workspaces", token),
  createWorkspace: (token: string, body: { name: string; plan: string; status: string }) =>
    apiFetch<Workspace>("/api/v1/admin/workspaces", token, { method: "POST", body: JSON.stringify(body) }),
  updateWorkspace: (token: string, id: number, body: Partial<Pick<Workspace, "name" | "plan" | "status">>) =>
    apiFetch<Workspace>(`/api/v1/admin/workspaces/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  usage: (token: string, workspaceId?: number | null) =>
    apiFetch<UsageSummary>(`/api/v1/admin/usage${toQuery({ workspace_id: workspaceId })}`, token),
  usageDaily: (token: string, workspaceId?: number | null) =>
    apiFetch<UsageDailyItem[]>(`/api/v1/admin/usage/daily${toQuery({ days: 14, workspace_id: workspaceId })}`, token),
  usageByModel: (token: string, workspaceId?: number | null) =>
    apiFetch<UsageByModelItem[]>(`/api/v1/admin/usage/by-model${toQuery({ workspace_id: workspaceId })}`, token),
  billingPlans: (token: string) => apiFetch<BillingPlan[]>("/api/v1/admin/billing/plans", token),
  billingSummary: (token: string, workspaceId?: number | null) =>
    apiFetch<BillingSummary>(`/api/v1/admin/billing/summary${toQuery({ workspace_id: workspaceId })}`, token),
  createCheckout: (token: string, body: { workspace_id: number; plan: string }) =>
    apiFetch<{ ok: boolean; provider: string; checkout_url?: string | null; message: string }>("/api/v1/admin/billing/checkout", token, { method: "POST", body: JSON.stringify(body) }),
  tasks: (
    token: string,
    params: { limit: number; offset: number; q?: string; status?: string; action?: string; modeling_mode?: string; workspace_id?: number | null }
  ) => apiFetch<TaskListItem[]>(`/api/v1/admin/tasks${toQuery(params)}`, token),
  taskDetail: (token: string, id: number) => apiFetch<TaskDetail>(`/api/v1/admin/tasks/${id}`, token),
  cancelTask: (token: string, id: number) => apiFetch<{ ok: boolean; task_id: number; status: string; message?: string }>(`/api/v1/admin/tasks/${id}/cancel`, token, { method: "POST" }),
  retryTask: (token: string, id: number) => apiFetch<{ ok: boolean; task_id: number; status: string; message?: string }>(`/api/v1/admin/tasks/${id}/retry`, token, { method: "POST" }),
  scriptAssets: (token: string, workspaceId?: number | null) =>
    apiFetch<ScriptAsset[]>(`/api/v1/admin/script-assets${toQuery({ workspace_id: workspaceId })}`, token),
  scriptVersions: (token: string, assetId: number) =>
    apiFetch<ScriptVersion[]>(`/api/v1/admin/script-assets/${assetId}/versions`, token),
  updateScriptAsset: (token: string, id: number, body: Partial<Pick<ScriptAsset, "name" | "description" | "favorite" | "status" | "tags" | "metadata">>) =>
    apiFetch<ScriptAsset>(`/api/v1/admin/script-assets/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  favoriteScriptAsset: (token: string, id: number) =>
    apiFetch<ScriptAsset>(`/api/v1/admin/script-assets/${id}/favorite`, token, { method: "POST" }),
  copyScriptAsset: (token: string, id: number) =>
    apiFetch<ScriptAsset>(`/api/v1/admin/script-assets/${id}/copy`, token, { method: "POST" }),
  rollbackScriptAsset: (token: string, id: number, versionId: number) =>
    apiFetch<ScriptAsset>(`/api/v1/admin/script-assets/${id}/rollback`, token, { method: "POST", body: JSON.stringify({ version_id: versionId }) }),
  reuseScriptAssetTemplate: (token: string, id: number, body: { name?: string; category: string; workspace_id?: number | null }) =>
    apiFetch<Template>(`/api/v1/admin/script-assets/${id}/reuse-template`, token, { method: "POST", body: JSON.stringify(body) }),
  modelAssets: (token: string, workspaceId?: number | null) =>
    apiFetch<ModelAsset[]>(`/api/v1/admin/model-assets${toQuery({ workspace_id: workspaceId })}`, token),
  createModelAsset: (token: string, body: Omit<ModelAsset, "id" | "created_at" | "updated_at">) =>
    apiFetch<ModelAsset>("/api/v1/admin/model-assets", token, { method: "POST", body: JSON.stringify(body) }),
  updateModelAsset: (token: string, id: number, body: Partial<Omit<ModelAsset, "id" | "workspace_id" | "created_at" | "updated_at">>) =>
    apiFetch<ModelAsset>(`/api/v1/admin/model-assets/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  deleteModelAsset: (token: string, id: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/admin/model-assets/${id}`, token, { method: "DELETE" }),
  templates: (token: string, workspaceId?: number | null) =>
    apiFetch<Template[]>(`/api/v1/admin/templates${toQuery({ include_disabled: true, workspace_id: workspaceId })}`, token),
  createTemplate: (token: string, body: Omit<Template, "id">) =>
    apiFetch<Template>("/api/v1/admin/templates", token, { method: "POST", body: JSON.stringify(body) }),
  updateTemplate: (token: string, id: number, body: Partial<Omit<Template, "id" | "workspace_id">>) =>
    apiFetch<Template>(`/api/v1/admin/templates/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  deleteTemplate: (token: string, id: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/admin/templates/${id}`, token, { method: "DELETE" }),
  importTemplates: (token: string, templates: Array<Omit<Template, "id">>) =>
    apiFetch<Template[]>("/api/v1/admin/templates/import", token, { method: "POST", body: JSON.stringify({ templates }) }),
  seedDefaultTemplates: (token: string) =>
    apiFetch<Template[]>("/api/v1/admin/templates/seed-defaults", token, { method: "POST" }),
  exportTemplates: (token: string, workspaceId?: number | null) =>
    apiFetch<Template[]>(`/api/v1/admin/templates/export${toQuery({ workspace_id: workspaceId })}`, token),
  apiKeys: (token: string, workspaceId?: number | null) =>
    apiFetch<ApiKey[]>(`/api/v1/admin/api-keys${toQuery({ workspace_id: workspaceId })}`, token),
  createApiKey: (token: string, body: { workspace_id: number; name: string }) =>
    apiFetch<ApiKeyCreateResponse>("/api/v1/admin/api-keys", token, { method: "POST", body: JSON.stringify(body) }),
  revokeApiKey: (token: string, id: number) =>
    apiFetch<ApiKey>(`/api/v1/admin/api-keys/${id}/revoke`, token, { method: "POST" }),
  enableApiKey: (token: string, id: number) =>
    apiFetch<ApiKey>(`/api/v1/admin/api-keys/${id}/enable`, token, { method: "POST" }),
  adminUsers: (token: string) => apiFetch<AdminUser[]>("/api/v1/admin/admin-users", token),
  createAdminUser: (token: string, body: { username: string; password: string; role: string; status: string }) =>
    apiFetch<AdminUser>("/api/v1/admin/admin-users", token, { method: "POST", body: JSON.stringify(body) }),
  updateAdminUser: (token: string, id: number, body: Partial<{ role: string; status: string; password: string }>) =>
    apiFetch<AdminUser>(`/api/v1/admin/admin-users/${id}`, token, { method: "PUT", body: JSON.stringify(body) }),
  changePassword: (token: string, body: { current_password: string; new_password: string }) =>
    apiFetch<{ ok: boolean }>("/api/v1/admin/auth/password", token, { method: "PUT", body: JSON.stringify(body) }),
  auditLogs: (token: string, workspaceId?: number | null) =>
    apiFetch<AuditLog[]>(`/api/v1/admin/audit-logs${toQuery({ limit: 100, workspace_id: workspaceId })}`, token)
};

export function downloadJson(filename: string, data: unknown) {
  downloadBlob(filename, new Blob([JSON.stringify(data, null, 2)], { type: "application/json;charset=utf-8" }));
}

export function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function exportTasksCsv(token: string, params: Record<string, QueryValue>) {
  const response = await fetch(appPath(`/api/v1/admin/tasks/export${toQuery({ ...params, limit: 1000, offset: 0 })}`), {
    headers: { Authorization: `Bearer ${token}` }
  });
  if (!response.ok) throw new Error(await parseError(response));
  downloadBlob("freecadai_tasks.csv", await response.blob());
}
