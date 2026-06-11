export type Role = "owner" | "operator" | "viewer" | string;

export type AdminPrincipal = {
  id?: number;
  username: string;
  role: Role;
  status?: string;
};

export type LoginResponse = {
  token: string;
  token_type: string;
  expires_at: string;
  user: AdminPrincipal;
};

export type Workspace = {
  id: number;
  name: string;
  plan: string;
  status: string;
  created_at: string;
  api_key_count: number;
  task_count: number;
  quota?: BillingWorkspaceSummary;
};

export type UsageSummary = {
  task_count: number;
  succeeded_count: number;
  failed_count: number;
  report_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
};

export type UsageDailyItem = {
  day: string;
  task_count: number;
  succeeded_count: number;
  failed_count: number;
  report_count: number;
  total_tokens: number;
  estimated_cost: number;
};

export type UsageByModelItem = {
  provider: string;
  model: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
};

export type ConsoleUsageMemberItem = {
  user_id?: number | null;
  email: string;
  display_name: string;
  task_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
};

export type ConsoleUsageProjectItem = {
  project_id: string;
  task_count: number;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  estimated_cost: number;
};

export type BillingWorkspaceSummary = {
  workspace_id: number;
  workspace_name: string;
  plan: string;
  status: string;
  monthly_price_cents: number;
  limits: Record<"tasks" | "templates" | "api_keys" | "concurrent", number | null>;
  usage: {
    billing_period_start: string;
    task_count: number;
    template_count: number;
    api_key_count: number;
    concurrent_count: number;
    input_tokens: number;
    output_tokens: number;
    total_tokens: number;
    estimated_cost: number;
  };
  warnings: string[];
};

export type BillingSummary = {
  workspaces: BillingWorkspaceSummary[];
};

export type BillingPlan = {
  name: string;
  monthly_price_cents: number;
  limits: Record<"tasks" | "templates" | "api_keys" | "concurrent", number | null>;
};

export type TaskListItem = {
  id: number;
  workspace_id: number;
  project_id: string;
  action: string;
  modeling_mode: string;
  prompt: string;
  model: string;
  status: string;
  latency_ms: number;
  created_at: string;
};

export type TaskDetail = {
  task: Record<string, unknown>;
  scripts: Array<Record<string, unknown>>;
  reports: Array<Record<string, unknown>>;
};

export type Template = {
  id: number;
  workspace_id?: number | null;
  name: string;
  category: string;
  prompt: string;
  enabled: boolean;
};

export type ScriptVersion = {
  id: number;
  asset_id: number;
  task_id?: number | null;
  version: number;
  script: string;
  summary: string;
  parameters: Record<string, unknown>;
  expected_objects: unknown[];
  validation_status: string;
  validation_error: string;
  created_by: string;
  created_at: string;
};

export type ScriptAsset = {
  id: number;
  workspace_id: number;
  task_id?: number | null;
  current_version_id?: number | null;
  current_version?: number | null;
  name: string;
  description: string;
  modeling_mode: string;
  project_id: string;
  source: string;
  favorite: boolean;
  status: string;
  tags: string[];
  metadata: Record<string, unknown>;
  summary: string;
  script_preview: string;
  created_at: string;
  updated_at: string;
};

export type ModelAsset = {
  id: number;
  workspace_id: number;
  script_asset_id?: number | null;
  task_id?: number | null;
  project_id: string;
  name: string;
  file_name: string;
  file_type: string;
  storage_uri: string;
  preview_uri: string;
  checksum: string;
  size_bytes: number;
  status: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ApiKey = {
  id: number;
  workspace_id: number;
  name: string;
  prefix: string;
  status: string;
  scopes?: string[];
  created_by_user_id?: number | null;
  expires_at?: string | null;
  last_used_at?: string | null;
  created_at: string;
};

export type ApiKeyCreateResponse = {
  id: number;
  api_key: string;
  prefix: string;
};

export type AuditLog = {
  id: number;
  actor: string;
  action: string;
  target_type: string;
  target_id: string;
  workspace_id?: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
};

export type ConsoleNotification = {
  id: number;
  workspace_id: number;
  user_id?: number | null;
  title: string;
  body: string;
  level: string;
  status: string;
  metadata: Record<string, unknown>;
  read_at?: string | null;
  created_at: string;
};

export type AdminUser = {
  id: number;
  username: string;
  role: Role;
  status: string;
  last_login_at?: string | null;
  created_at: string;
};

export type Health = {
  ok: boolean;
  service: string;
  redis: boolean;
};

export type ConsoleUser = {
  id: number;
  email: string;
  phone: string;
  display_name: string;
  status: string;
  last_login_at?: string | null;
  created_at: string;
};

export type ConsoleWorkspace = {
  id: number;
  name: string;
  plan: string;
  status: string;
  role: string;
  created_at: string;
  member_count: number;
  api_key_count: number;
  task_count: number;
  asset_count: number;
  quota?: BillingWorkspaceSummary;
};

export type ConsoleAuthResponse = {
  token: string;
  token_type: string;
  expires_at: string;
  user: ConsoleUser;
  workspaces: ConsoleWorkspace[];
};

export type ConsoleMeResponse = {
  user: ConsoleUser;
  workspaces: ConsoleWorkspace[];
};

export type ConsoleMember = {
  id: number;
  workspace_id: number;
  user_id: number;
  email: string;
  display_name: string;
  role: string;
  status: string;
  joined_at?: string | null;
  created_at: string;
};

export type ConsoleInvite = {
  id: number;
  workspace_id: number;
  email: string;
  role: string;
  status: string;
  expires_at: string;
  invite_token?: string | null;
  created_at: string;
};

export type ConsoleApiKeyCreateResponse = {
  id: number;
  api_key: string;
  prefix: string;
  item: ApiKey;
};

export type ConsolePluginGuide = {
  workspace_id: number;
  workspace_name: string;
  saas_base_url: string;
  verify_path: string;
  login_path: string;
  bind_path: string;
};

export type ConsoleTaskListItem = {
  id: number;
  workspace_id: number;
  created_by_user_id?: number | null;
  project_id: string;
  source: string;
  action: string;
  modeling_mode: string;
  prompt: string;
  model: string;
  status: string;
  error_message: string;
  latency_ms: number;
  created_at: string;
  updated_at: string;
};

export type ConsoleTaskSubmitResponse = {
  task_id: number;
  status: string;
  message: string;
};

export type ConsoleTaskDetail = {
  task: Record<string, unknown>;
  scripts: Array<Record<string, unknown>>;
  reports: Array<Record<string, unknown>>;
};

export type ConsoleTaskActionResponse = {
  ok: boolean;
  task_id: number;
  status: string;
  message: string;
};
