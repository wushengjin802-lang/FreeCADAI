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

export type ApiKey = {
  id: number;
  workspace_id: number;
  name: string;
  prefix: string;
  status: string;
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
