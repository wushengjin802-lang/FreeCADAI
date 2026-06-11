"use client";

import {
  ApiOutlined,
  AuditOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  KeyOutlined,
  LogoutOutlined,
  PlusOutlined,
  ReloadOutlined,
  TeamOutlined,
  UserOutlined
} from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App as AntApp,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Form,
  Input,
  Layout,
  Menu,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography
} from "antd";
import type { ColumnsType } from "antd/es/table";
import ReactECharts from "echarts-for-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { Providers } from "@/components/Providers";
import { adminApi, downloadJson, exportTasksCsv } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageAdmins, canOperate, useAppStore } from "@/lib/store";
import type { AdminUser, ApiKey, AuditLog, BillingSummary, ModelAsset, ScriptAsset, ScriptVersion, TaskDetail, TaskListItem, Template, UsageByModelItem, Workspace } from "@/lib/types";

const { Content, Sider } = Layout;
const { Text, Title } = Typography;

type ViewKey = "dashboard" | "workspaces" | "tasks" | "assets" | "templates" | "keys" | "adminUsers" | "audit";

const taskLimit = 50;

const templateCategoryOptions = [
  { value: "通用", label: "通用" },
  { value: "零件建模", label: "零件建模" },
  { value: "草图绘制", label: "草图绘制" },
  { value: "装配设计", label: "装配设计" },
  { value: "钣金结构", label: "钣金结构" },
  { value: "工程图", label: "工程图" },
  { value: "夹具工装", label: "夹具工装" },
  { value: "参数化", label: "参数化" }
];

function statusColor(status: string) {
  if (["succeeded", "active"].includes(status)) return "green";
  if (["failed", "revoked", "suspended"].includes(status)) return "red";
  if (["running", "queued"].includes(status)) return "gold";
  return "blue";
}

function shortJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

function formatMoney(value?: number) {
  return `$${Number(value || 0).toFixed(4)}`;
}

function formatShanghaiTime(value?: string | null) {
  if (!value) return "-";
  const source = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value) ? value : `${value}Z`;
  const date = new Date(source);
  if (Number.isNaN(date.getTime())) return value;
  const parts = new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  }).formatToParts(date);
  const get = (type: string) => parts.find((part) => part.type === type)?.value || "";
  return `${get("year")}-${get("month")}-${get("day")} ${get("hour")}:${get("minute")}:${get("second")}`;
}

function formatLimit(value?: number | null) {
  return value == null ? "不限" : String(value);
}

const planOptions = [
  { value: "free", label: "免费版" },
  { value: "pro", label: "专业版" },
  { value: "team", label: "团队版" },
  { value: "enterprise", label: "企业版" }
];

const statusOptions = [
  { value: "active", label: "正常" },
  { value: "suspended", label: "停用" }
];

const statusLabel: Record<string, string> = {
  active: "正常",
  suspended: "停用",
  succeeded: "成功",
  failed: "失败",
  running: "运行中",
  queued: "排队中",
  canceled: "已取消",
  revoked: "已撤销"
};

const adminRoleOptions = [
  { value: "operator", label: "操作员" },
  { value: "owner", label: "拥有者" },
  { value: "viewer", label: "观察者" }
];

const adminRoleLabel: Record<string, string> = {
  owner: "拥有者",
  operator: "操作员",
  viewer: "观察者"
};

function useConsoleData() {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const enabled = Boolean(token);

  return {
    health: useQuery({ queryKey: ["health"], queryFn: adminApi.health }),
    me: useQuery({ queryKey: ["me", token], queryFn: () => adminApi.me(token), enabled }),
    workspaces: useQuery({ queryKey: ["workspaces", token], queryFn: () => adminApi.workspaces(token), enabled }),
    usage: useQuery({ queryKey: ["usage", token, workspaceId], queryFn: () => adminApi.usage(token, workspaceId), enabled }),
    usageDaily: useQuery({ queryKey: ["usageDaily", token, workspaceId], queryFn: () => adminApi.usageDaily(token, workspaceId), enabled }),
    usageByModel: useQuery({ queryKey: ["usageByModel", token, workspaceId], queryFn: () => adminApi.usageByModel(token, workspaceId), enabled }),
    billing: useQuery({ queryKey: ["billingSummary", token, workspaceId], queryFn: () => adminApi.billingSummary(token, workspaceId), enabled })
  };
}

function ConsolePageContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useAppStore((state) => state.token);
  const principal = useAppStore((state) => state.principal);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const setPrincipal = useAppStore((state) => state.setPrincipal);
  const setWorkspaceId = useAppStore((state) => state.setWorkspaceId);
  const logoutStore = useAppStore((state) => state.logout);
  const [view, setView] = useState<ViewKey>("dashboard");
  const data = useConsoleData();

  useEffect(() => {
    if (!token) router.replace(routePath("/login"));
  }, [router, token]);

  useEffect(() => {
    if (data.me.data) setPrincipal(data.me.data);
  }, [data.me.data, setPrincipal]);

  const logoutMutation = useMutation({
    mutationFn: () => adminApi.logout(token),
    onSettled: () => {
      logoutStore();
      router.replace(routePath("/login"));
    }
  });

  const refreshAll = () => {
    queryClient.invalidateQueries();
    message.success("数据已刷新");
  };

  const menuItems = [
    { key: "dashboard", icon: <BarChartOutlined />, label: "总览" },
    { key: "workspaces", icon: <DatabaseOutlined />, label: "工作区" },
    { key: "tasks", icon: <ApiOutlined />, label: "任务历史" },
    { key: "assets", icon: <FileTextOutlined />, label: "资产库" },
    { key: "templates", icon: <DatabaseOutlined />, label: "模板库" },
    { key: "keys", icon: <KeyOutlined />, label: "API Key" },
    { key: "adminUsers", icon: <TeamOutlined />, label: "管理员" },
    { key: "audit", icon: <AuditOutlined />, label: "审计日志" }
  ];

  if (!token) return null;

  return (
    <Layout className="console-shell">
      <Sider width={230} breakpoint="lg" collapsedWidth={0} className="console-sider">
        <div className="console-brand">
          <strong>FreeCADAI</strong>
          <span>SaaS 控制台<br />工作区、任务、模板、密钥和审计</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[view]}
          items={menuItems}
          onClick={(item) => setView(item.key as ViewKey)}
          style={{ background: "transparent", borderInlineEnd: 0, paddingTop: 12 }}
        />
      </Sider>
      <Layout>
        <header className="console-header">
          <div>
            <Title level={3} style={{ margin: 0 }}>
              {menuItems.find((item) => item.key === view)?.label}
            </Title>
            <Text className="muted">
              {principal?.username || "admin"} · {principal?.role || "loading"} · {data.health.data?.redis ? "Redis 正常" : "Redis 未确认"}
            </Text>
          </div>
          <Space wrap>
            <Select
              style={{ minWidth: 220 }}
              value={workspaceId ?? ""}
              onChange={(value) => setWorkspaceId(value ? Number(value) : null)}
              options={[
                { value: "", label: "全部工作区" },
                ...(data.workspaces.data || []).map((item) => ({ value: item.id, label: `${item.id} ${item.name}` }))
              ]}
            />
            <Button icon={<ReloadOutlined />} onClick={refreshAll}>
              刷新
            </Button>
            <Button icon={<LogoutOutlined />} onClick={() => logoutMutation.mutate()} loading={logoutMutation.isPending}>
              退出
            </Button>
          </Space>
        </header>
        <Content className="console-content">
          {data.me.error ? <Alert type="error" showIcon message={data.me.error.message} style={{ marginBottom: 16 }} /> : null}
          {view === "dashboard" && <Dashboard usage={data.usage.data} daily={data.usageDaily.data || []} usageByModel={data.usageByModel.data || []} billing={data.billing.data} health={data.health.data} />}
          {view === "workspaces" && <WorkspacesView workspaces={data.workspaces.data || []} role={principal?.role} />}
          {view === "tasks" && <TasksView role={principal?.role} />}
          {view === "assets" && <AssetsView role={principal?.role} />}
          {view === "templates" && <TemplatesView role={principal?.role} />}
          {view === "keys" && <KeysView role={principal?.role} workspaces={data.workspaces.data || []} />}
          {view === "adminUsers" && <AdminUsersView role={principal?.role} />}
          {view === "audit" && <AuditView workspaces={data.workspaces.data || []} />}
        </Content>
      </Layout>
    </Layout>
  );
}

function Dashboard({
  usage,
  daily,
  usageByModel,
  billing,
  health
}: {
  usage?: { task_count: number; succeeded_count: number; failed_count: number; report_count: number; total_tokens: number; estimated_cost: number };
  daily: Array<{ day: string; task_count: number; succeeded_count: number; failed_count: number; report_count: number; total_tokens: number; estimated_cost: number }>;
  usageByModel: UsageByModelItem[];
  billing?: BillingSummary;
  health?: { ok: boolean; service: string; redis: boolean };
}) {
  const taskTrendOption = useMemo(
    () => ({
      tooltip: { trigger: "axis" },
      legend: { top: 0 },
      grid: { left: 28, right: 16, top: 44, bottom: 28 },
      xAxis: { type: "category", data: daily.map((item) => item.day) },
      yAxis: { type: "value", name: "次数", minInterval: 1 },
      series: [
        { name: "任务", type: "line", smooth: true, data: daily.map((item) => item.task_count), color: "#355263" },
        { name: "成功", type: "line", smooth: true, data: daily.map((item) => item.succeeded_count), color: "#16734a" },
        { name: "失败", type: "line", smooth: true, data: daily.map((item) => item.failed_count), color: "#a23b3b" }
      ]
    }),
    [daily]
  );
  const tokenTrendOption = useMemo(
    () => ({
      tooltip: { trigger: "axis" },
      legend: { top: 0 },
      grid: { left: 56, right: 16, top: 44, bottom: 28 },
      xAxis: { type: "category", data: daily.map((item) => item.day) },
      yAxis: { type: "value", name: "Token" },
      series: [
        { name: "Token", type: "bar", data: daily.map((item) => item.total_tokens), color: "#9a6a24", barMaxWidth: 36 }
      ]
    }),
    [daily]
  );
  const warnings = billing?.workspaces.flatMap((workspace) => workspace.warnings.map((warning) => `${workspace.workspace_name}: ${warning}`)) || [];
  const displayProvider = (provider: string, model: string) => {
    const providerText = (provider || "").toLowerCase();
    const modelText = (model || "").toLowerCase();
    if (providerText.includes("deepseek") || modelText.includes("deepseek")) return "deepseek";
    if ((providerText === "openai" || providerText === "openai-compatible") && modelText.startsWith("gpt-")) return "openai";
    return provider || "openai-compatible";
  };
  const modelColumns: ColumnsType<UsageByModelItem> = [
    { title: "Provider", dataIndex: "provider", width: 140, render: (value, row) => {
      const provider = displayProvider(value, row.model);
      return <Tag color={provider === "deepseek" ? "blue" : "default"}>{provider}</Tag>;
    } },
    { title: "模型", dataIndex: "model" },
    { title: "请求数", dataIndex: "request_count", width: 100 },
    { title: "输入 Token", dataIndex: "input_tokens", width: 130 },
    { title: "输出 Token", dataIndex: "output_tokens", width: 130 },
    { title: "总 Token", dataIndex: "total_tokens", width: 130 },
    { title: "估算成本", dataIndex: "estimated_cost", width: 130, render: (value) => formatMoney(value) }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      {warnings.length ? <Alert type="warning" showIcon message="套餐用量提醒" description={warnings.join("；")} /> : null}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="任务总数" value={usage?.task_count || 0} /></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="成功任务" value={usage?.succeeded_count || 0} /></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="总 Token" value={usage?.total_tokens || 0} /></Card></Col>
        <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="估算成本" value={formatMoney(usage?.estimated_cost)} /></Card></Col>
      </Row>
      <Card title="服务状态" className="console-card">
        <Descriptions column={{ xs: 1, sm: 3 }}>
          <Descriptions.Item label="服务">{health?.service || "FreeCADAI SaaS"}</Descriptions.Item>
          <Descriptions.Item label="API">{health?.ok ? <Tag color="green">正常</Tag> : <Tag>未知</Tag>}</Descriptions.Item>
          <Descriptions.Item label="Redis">{health?.redis ? <Tag color="green">正常</Tag> : <Tag color="red">异常</Tag>}</Descriptions.Item>
        </Descriptions>
      </Card>
      <Row gutter={[16, 16]}>
        <Col xs={24} lg={12}>
          <Card title="近 14 天任务趋势" className="console-card">
            <ReactECharts option={taskTrendOption} style={{ height: 320 }} />
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title="近 14 天 Token 消耗" className="console-card">
            <ReactECharts option={tokenTrendOption} style={{ height: 320 }} />
          </Card>
        </Col>
      </Row>
      <Card title="按模型用量" className="console-card">
        <Table rowKey={(row) => `${row.provider}-${row.model}`} className="usage-model-table balanced-table" columns={modelColumns} dataSource={usageByModel} pagination={false} scroll={{ x: 1120 }} tableLayout="fixed" />
      </Card>
    </Space>
  );
}

function WorkspacesView({ workspaces, role }: { workspaces: Workspace[]; role?: string }) {
  const token = useAppStore((state) => state.token);
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const [editForm] = Form.useForm();
  const [editingWorkspace, setEditingWorkspace] = useState<Workspace | null>(null);
  const canWrite = canOperate(role);

  const createMutation = useMutation({
    mutationFn: (values: { name: string; plan: string; status: string }) => adminApi.createWorkspace(token, values),
    onSuccess: () => {
      message.success("工作区已创建");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<Workspace, "name" | "plan" | "status">> }) => adminApi.updateWorkspace(token, id, body),
    onSuccess: () => {
      message.success("工作区信息已更新");
      setEditingWorkspace(null);
      queryClient.invalidateQueries({ queryKey: ["workspaces"] });
    }
  });

  const openEditWorkspace = (workspace: Workspace) => {
    setEditingWorkspace(workspace);
    editForm.setFieldsValue({
      name: workspace.name,
      plan: workspace.plan,
      status: workspace.status
    });
  };

  const columns: ColumnsType<Workspace> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "名称", dataIndex: "name" },
    { title: "套餐", dataIndex: "plan", width: 120, render: (plan) => {
      const planLabel: Record<string, string> = { free: "免费版", pro: "专业版", team: "团队版", enterprise: "企业版" };
      return <Tag>{planLabel[plan] || plan}</Tag>;
    } },
    { title: "状态", dataIndex: "status", width: 120, render: (status) => <Tag color={statusColor(status)}>{statusLabel[status] || status}</Tag> },
    { title: "Key 数", dataIndex: "api_key_count", width: 100 },
    { title: "任务数", dataIndex: "task_count", width: 100 },
    {
      title: "套餐限制",
      width: 260,
      render: (_, row) => row.quota ? (
        <Text>
          任务 {row.quota.usage.task_count}/{formatLimit(row.quota.limits.tasks)} ·
          模板 {row.quota.usage.template_count}/{formatLimit(row.quota.limits.templates)} ·
          Key {row.quota.usage.api_key_count}/{formatLimit(row.quota.limits.api_keys)} ·
          并发 {row.quota.usage.concurrent_count}/{formatLimit(row.quota.limits.concurrent)}
        </Text>
      ) : "-"
    },
    {
      title: "提示",
      width: 220,
      render: (_, row) => row.quota?.warnings.length ? row.quota.warnings.map((warning) => <Tag key={warning} color="gold">{warning}</Tag>) : <Tag color="green">正常</Tag>
    },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 180,
      render: (_, row) => (
        <Space>
          <Button disabled={!canWrite} onClick={() => openEditWorkspace(row)}>
            修改
          </Button>
          <Button disabled={!canWrite} onClick={() => updateMutation.mutate({ id: row.id, body: { status: row.status === "active" ? "suspended" : "active" } })}>
            {row.status === "active" ? "停用" : "启用"}
          </Button>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Card title="创建工作区" className="console-card">
        <Form form={form} layout="inline" onFinish={(values) => createMutation.mutate(values)} initialValues={{ plan: "free", status: "active" }}>
          <Form.Item name="name" rules={[{ required: true, message: "请输入名称" }]}><Input placeholder="工作区名称" /></Form.Item>
          <Form.Item name="plan"><Select style={{ width: 130 }} options={planOptions} /></Form.Item>
          <Form.Item name="status"><Select style={{ width: 140 }} options={statusOptions} /></Form.Item>
          <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createMutation.isPending}>创建</Button>
        </Form>
      </Card>
      <Card title="工作区列表" className="console-card">
        <Table rowKey="id" className="workspace-table balanced-table" columns={columns} dataSource={workspaces} scroll={{ x: 1540 }} tableLayout="fixed" pagination={false} />
      </Card>
      <Modal
        title={`修改工作区${editingWorkspace ? ` #${editingWorkspace.id}` : ""}`}
        open={Boolean(editingWorkspace)}
        onCancel={() => setEditingWorkspace(null)}
        onOk={() => editForm.submit()}
        okButtonProps={{ disabled: !canWrite, loading: updateMutation.isPending }}
        destroyOnHidden
      >
        <Form
          form={editForm}
          layout="vertical"
          onFinish={(values) => {
            if (!editingWorkspace) return;
            updateMutation.mutate({ id: editingWorkspace.id, body: values });
          }}
        >
          <Form.Item name="name" label="工作区名称" rules={[{ required: true, message: "请输入工作区名称" }]}>
            <Input />
          </Form.Item>
          <Form.Item name="plan" label="套餐">
            <Select options={planOptions} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={statusOptions} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

function TasksView({ role }: { role?: string }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const { message } = AntApp.useApp();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState({ q: "", status: "", action: "", modeling_mode: "" });
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const params = { ...filters, limit: taskLimit, offset, workspace_id: workspaceId };
  const tasks = useQuery({ queryKey: ["tasks", token, params], queryFn: () => adminApi.tasks(token, params), enabled: Boolean(token) });
  const detail = useQuery({ queryKey: ["taskDetail", token, selectedId], queryFn: () => adminApi.taskDetail(token, selectedId as number), enabled: Boolean(token && selectedId) });
  const canWrite = canOperate(role);
  const refreshTasks = () => queryClient.invalidateQueries({ queryKey: ["tasks"] });
  const cancelMutation = useMutation({ mutationFn: (id: number) => adminApi.cancelTask(token, id), onSuccess: (data) => { message.success(data.message || "任务已取消"); refreshTasks(); } });
  const retryMutation = useMutation({ mutationFn: (id: number) => adminApi.retryTask(token, id), onSuccess: (data) => { message.success(data.message || "任务已重试"); refreshTasks(); } });

  const columns: ColumnsType<TaskListItem> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "工作区", dataIndex: "workspace_id", width: 90 },
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{statusLabel[status] || status}</Tag> },
    { title: "动作", dataIndex: "action", width: 110 },
    { title: "模式", dataIndex: "modeling_mode", width: 130 },
    { title: "模型", dataIndex: "model", width: 160 },
    { title: "需求", dataIndex: "prompt", ellipsis: true },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 180,
      render: (_, row) => (
        <Space>
          <Button disabled={!canWrite || !["queued", "running"].includes(row.status)} onClick={(event) => { event.stopPropagation(); cancelMutation.mutate(row.id); }}>取消</Button>
          <Button disabled={!canWrite || !["failed", "canceled"].includes(row.status)} onClick={(event) => { event.stopPropagation(); retryMutation.mutate(row.id); }}>重试</Button>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Card className="console-card">
        <Space wrap>
          <Input.Search placeholder="搜索需求、项目、模型或错误" allowClear style={{ width: 280 }} onSearch={(q) => { setOffset(0); setFilters((old) => ({ ...old, q })); }} />
          <Select placeholder="状态" allowClear style={{ width: 130 }} onChange={(status) => { setOffset(0); setFilters((old) => ({ ...old, status: status || "" })); }} options={["succeeded", "failed", "running"].map((value) => ({ value, label: value }))} />
          <Select placeholder="动作" allowClear style={{ width: 130 }} onChange={(action) => { setOffset(0); setFilters((old) => ({ ...old, action: action || "" })); }} options={["generate", "repair", "regenerate"].map((value) => ({ value, label: value }))} />
          <Select placeholder="模式" allowClear style={{ width: 150 }} onChange={(modeling_mode) => { setOffset(0); setFilters((old) => ({ ...old, modeling_mode: modeling_mode || "" })); }} options={["3d_solid", "2d_sketch", "techdraw"].map((value) => ({ value, label: value }))} />
          <Button onClick={() => tasks.refetch()}>查询</Button>
          <Button type="primary" onClick={() => exportTasksCsv(token, params).then(() => message.success("CSV 已导出")).catch((error: Error) => message.error(error.message))}>导出 CSV</Button>
        </Space>
      </Card>
      <Card title="任务历史" className="console-card">
        <Table
          rowKey="id"
          columns={columns}
          dataSource={tasks.data || []}
          loading={tasks.isLoading}
          scroll={{ x: 1050 }}
          pagination={false}
          onRow={(row) => ({ onClick: () => setSelectedId(row.id) })}
        />
        <Space style={{ marginTop: 14 }}>
          <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - taskLimit))}>上一页</Button>
          <Text className="muted">第 {Math.floor(offset / taskLimit) + 1} 页，当前 {tasks.data?.length || 0} 条</Text>
          <Button disabled={(tasks.data?.length || 0) < taskLimit} onClick={() => setOffset(offset + taskLimit)}>下一页</Button>
        </Space>
      </Card>
      <Drawer title={`任务详情${selectedId ? ` #${selectedId}` : ""}`} open={Boolean(selectedId)} onClose={() => setSelectedId(null)} width={760}>
        <pre className="pre-block">{detail.isLoading ? "加载中..." : shortJson(detail.data as TaskDetail | undefined)}</pre>
      </Drawer>
    </Space>
  );
}

function AssetsView({ role }: { role?: string }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const queryClient = useQueryClient();
  const { message, modal } = AntApp.useApp();
  const [modelForm] = Form.useForm();
  const [selectedScript, setSelectedScript] = useState<ScriptAsset | null>(null);
  const canWrite = canOperate(role);
  const scripts = useQuery({ queryKey: ["scriptAssets", token, workspaceId], queryFn: () => adminApi.scriptAssets(token, workspaceId), enabled: Boolean(token) });
  const models = useQuery({ queryKey: ["modelAssets", token, workspaceId], queryFn: () => adminApi.modelAssets(token, workspaceId), enabled: Boolean(token) });
  const versions = useQuery({
    queryKey: ["scriptVersions", token, selectedScript?.id],
    queryFn: () => adminApi.scriptVersions(token, selectedScript?.id as number),
    enabled: Boolean(token && selectedScript)
  });
  const invalidateAssets = () => {
    queryClient.invalidateQueries({ queryKey: ["scriptAssets"] });
    queryClient.invalidateQueries({ queryKey: ["modelAssets"] });
  };
  const favoriteMutation = useMutation({ mutationFn: (id: number) => adminApi.favoriteScriptAsset(token, id), onSuccess: invalidateAssets });
  const copyMutation = useMutation({
    mutationFn: (id: number) => adminApi.copyScriptAsset(token, id),
    onSuccess: () => {
      message.success("脚本资产已复制");
      invalidateAssets();
    }
  });
  const rollbackMutation = useMutation({
    mutationFn: ({ assetId, versionId }: { assetId: number; versionId: number }) => adminApi.rollbackScriptAsset(token, assetId, versionId),
    onSuccess: (asset) => {
      message.success("已回滚到所选版本");
      setSelectedScript(asset);
      invalidateAssets();
      queryClient.invalidateQueries({ queryKey: ["scriptVersions"] });
    }
  });
  const reuseMutation = useMutation({
    mutationFn: (asset: ScriptAsset) => adminApi.reuseScriptAssetTemplate(token, asset.id, { name: asset.name, category: "复用脚本", workspace_id: workspaceId ?? asset.workspace_id }),
    onSuccess: () => {
      message.success("已复用为模板");
      queryClient.invalidateQueries({ queryKey: ["templates"] });
    },
    onError: (error: Error) => message.error(error.message)
  });
  const createModelMutation = useMutation({
    mutationFn: (values: Omit<ModelAsset, "id" | "created_at" | "updated_at">) => adminApi.createModelAsset(token, values),
    onSuccess: () => {
      message.success("模型元数据已保存");
      modelForm.resetFields();
      invalidateAssets();
    },
    onError: (error: Error) => message.error(error.message)
  });
  const deleteModelMutation = useMutation({
    mutationFn: (id: number) => adminApi.deleteModelAsset(token, id),
    onSuccess: () => {
      message.success("模型元数据已删除");
      invalidateAssets();
    }
  });

  const currentVersion = versions.data?.find((item) => item.id === selectedScript?.current_version_id) || versions.data?.[0];
  const copyScriptText = (version?: ScriptVersion) => {
    if (!version) return;
    navigator.clipboard.writeText(version.script).then(() => message.success("脚本已复制")).catch(() => message.error("复制失败"));
  };

  const scriptColumns: ColumnsType<ScriptAsset> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "工作区", dataIndex: "workspace_name", width: 160, render: (value, row) => value || `工作区 ID ${row.workspace_id}` },
    { title: "名称", dataIndex: "name", width: 220, ellipsis: true },
    { title: "版本", dataIndex: "current_version", width: 90, render: (value) => value ? `v${value}` : "-" },
    { title: "模式", dataIndex: "modeling_mode", width: 120 },
    { title: "项目名称", dataIndex: "project_id", width: 140, render: (value) => value || "-" },
    { title: "收藏", dataIndex: "favorite", width: 90, render: (value) => <Tag color={value ? "gold" : "default"}>{value ? "已收藏" : "普通"}</Tag> },
    { title: "摘要", dataIndex: "summary", ellipsis: true },
    { title: "更新时间", dataIndex: "updated_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 260,
      render: (_, row) => (
        <Space>
          <Button onClick={() => setSelectedScript(row)}>版本</Button>
          <Button disabled={!canWrite} onClick={() => favoriteMutation.mutate(row.id)}>{row.favorite ? "取消收藏" : "收藏"}</Button>
          <Button disabled={!canWrite} onClick={() => copyMutation.mutate(row.id)}>复制资产</Button>
          <Button disabled={!canWrite} onClick={() => reuseMutation.mutate(row)}>复用</Button>
        </Space>
      )
    }
  ];

  const modelColumns: ColumnsType<ModelAsset> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "工作区", dataIndex: "workspace_id", width: 90 },
    { title: "名称", dataIndex: "name", width: 200, ellipsis: true },
    { title: "文件名", dataIndex: "file_name", width: 220, ellipsis: true },
    { title: "类型", dataIndex: "file_type", width: 100, render: (value) => value || "-" },
    { title: "脚本资产", dataIndex: "script_asset_id", width: 110, render: (value) => value || "-" },
    { title: "状态", dataIndex: "status", width: 100, render: (value) => <Tag color={statusColor(value)}>{statusLabel[value] || value}</Tag> },
    { title: "预览地址", dataIndex: "preview_uri", ellipsis: true, render: (value) => value || "-" },
    { title: "更新时间", dataIndex: "updated_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 100,
      render: (_, row) => <Button danger disabled={!canWrite} onClick={() => modal.confirm({ title: "确认删除模型元数据？", onOk: () => deleteModelMutation.mutate(row.id) })}>删除</Button>
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Tabs
        items={[
          {
            key: "scripts",
            label: "脚本资产",
            children: (
              <Card title="脚本资产库" className="console-card">
                <Table rowKey="id" className="balanced-table" columns={scriptColumns} dataSource={scripts.data || []} loading={scripts.isLoading} scroll={{ x: 1480 }} tableLayout="fixed" pagination={{ pageSize: 10 }} />
              </Card>
            )
          },
          {
            key: "models",
            label: "模型元数据",
            children: (
              <Space direction="vertical" size={16} className="full-width">
                <Card title="新增模型元数据" className="console-card">
                  <Form
                    form={modelForm}
                    layout="vertical"
                    initialValues={{ workspace_id: workspaceId ?? 1, status: "active", size_bytes: 0 }}
                    onFinish={(values) => {
                      createModelMutation.mutate({
                        workspace_id: Number(values.workspace_id),
                        script_asset_id: values.script_asset_id ? Number(values.script_asset_id) : null,
                        task_id: values.task_id ? Number(values.task_id) : null,
                        project_id: values.project_id || "",
                        name: values.name,
                        file_name: values.file_name || "",
                        file_type: values.file_type || "",
                        storage_uri: values.storage_uri || "",
                        preview_uri: values.preview_uri || "",
                        checksum: values.checksum || "",
                        size_bytes: Number(values.size_bytes || 0),
                        status: values.status || "active",
                        metadata: {}
                      });
                    }}
                  >
                    <Row gutter={12}>
                      <Col xs={24} md={6}><Form.Item name="workspace_id" label="工作区 ID" rules={[{ required: true }]}><Input /></Form.Item></Col>
                      <Col xs={24} md={8}><Form.Item name="name" label="模型名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
                      <Col xs={24} md={10}><Form.Item name="file_name" label="文件名"><Input /></Form.Item></Col>
                      <Col xs={24} md={6}><Form.Item name="file_type" label="文件类型"><Input placeholder="FCStd / STEP" /></Form.Item></Col>
                      <Col xs={24} md={6}><Form.Item name="script_asset_id" label="关联脚本资产 ID"><Input /></Form.Item></Col>
                      <Col xs={24} md={6}><Form.Item name="task_id" label="关联任务 ID"><Input /></Form.Item></Col>
                      <Col xs={24} md={6}><Form.Item name="project_id" label="项目名称"><Input /></Form.Item></Col>
                      <Col xs={24} md={12}><Form.Item name="storage_uri" label="存储地址"><Input /></Form.Item></Col>
                      <Col xs={24} md={12}><Form.Item name="preview_uri" label="预览地址"><Input /></Form.Item></Col>
                    </Row>
                    <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createModelMutation.isPending}>保存模型元数据</Button>
                  </Form>
                </Card>
                <Card title="模型资产列表" className="console-card">
                  <Table rowKey="id" className="balanced-table" columns={modelColumns} dataSource={models.data || []} loading={models.isLoading} scroll={{ x: 1280 }} tableLayout="fixed" pagination={{ pageSize: 10 }} />
                </Card>
              </Space>
            )
          }
        ]}
      />
      <Drawer title={selectedScript ? `脚本版本 #${selectedScript.id}` : "脚本版本"} open={Boolean(selectedScript)} onClose={() => setSelectedScript(null)} width={860}>
        <Space direction="vertical" size={12} className="full-width">
          <Descriptions size="small" column={2} bordered>
            <Descriptions.Item label="名称">{selectedScript?.name}</Descriptions.Item>
            <Descriptions.Item label="当前版本">{selectedScript?.current_version ? `v${selectedScript.current_version}` : "-"}</Descriptions.Item>
            <Descriptions.Item label="项目名称">{selectedScript?.project_id || "-"}</Descriptions.Item>
            <Descriptions.Item label="模式">{selectedScript?.modeling_mode}</Descriptions.Item>
          </Descriptions>
          <Space>
            <Button onClick={() => copyScriptText(currentVersion)}>复制当前脚本</Button>
            <Button disabled={!selectedScript || !canWrite} onClick={() => selectedScript && reuseMutation.mutate(selectedScript)}>复用为模板</Button>
          </Space>
          <pre className="pre-block">{versions.isLoading ? "加载中..." : currentVersion?.script || "暂无脚本"}</pre>
          <Table
            rowKey="id"
            columns={[
              { title: "版本", dataIndex: "version", width: 90, render: (value) => `v${value}` },
              { title: "摘要", dataIndex: "summary", ellipsis: true },
              { title: "创建人", dataIndex: "created_by", width: 100 },
              { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
              {
                title: "操作",
                width: 180,
                render: (_, row: ScriptVersion) => (
                  <Space>
                    <Button onClick={() => copyScriptText(row)}>复制</Button>
                    <Button disabled={!canWrite || row.id === selectedScript?.current_version_id} onClick={() => selectedScript && rollbackMutation.mutate({ assetId: selectedScript.id, versionId: row.id })}>回滚</Button>
                  </Space>
                )
              }
            ]}
            dataSource={versions.data || []}
            loading={versions.isLoading}
            pagination={false}
            tableLayout="fixed"
          />
        </Space>
      </Drawer>
    </Space>
  );
}

function TemplatesView({ role }: { role?: string }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const queryClient = useQueryClient();
  const { message, modal } = AntApp.useApp();
  const [form] = Form.useForm();
  const [importText, setImportText] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const canWrite = canOperate(role);
  const templates = useQuery({ queryKey: ["templates", token, workspaceId], queryFn: () => adminApi.templates(token, workspaceId), enabled: Boolean(token) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["templates"] });
  const createMutation = useMutation({
    mutationFn: (values: { name: string; category: string; prompt: string; enabled: boolean }) =>
      adminApi.createTemplate(token, { ...values, workspace_id: workspaceId }),
    onSuccess: () => {
      message.success("模板已保存");
      form.resetFields();
      setCreateOpen(false);
      invalidate();
    }
  });
  const updateMutation = useMutation({ mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => adminApi.updateTemplate(token, id, { enabled }), onSuccess: invalidate });
  const deleteMutation = useMutation({ mutationFn: (id: number) => adminApi.deleteTemplate(token, id), onSuccess: invalidate });
  const seedMutation = useMutation({
    mutationFn: () => adminApi.seedDefaultTemplates(token),
    onSuccess: () => {
      message.success("内置模板已导入");
      invalidate();
    },
    onError: (error: Error) => message.error(error.message)
  });

  const importTemplates = () => {
    try {
      const parsed = JSON.parse(importText) as { templates?: Array<Omit<Template, "id">> } | Array<Omit<Template, "id">>;
      const rows = Array.isArray(parsed) ? parsed : parsed.templates || [];
      const scopedRows = rows.map((row) => ({ ...row, workspace_id: workspaceId ?? row.workspace_id ?? null }));
      adminApi.importTemplates(token, scopedRows).then(() => {
        message.success("模板已导入");
        setImportText("");
        setImportOpen(false);
        invalidate();
      }).catch((error: Error) => message.error(error.message));
    } catch {
      message.error("JSON 格式不正确");
    }
  };

  const columns: ColumnsType<Template> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "工作区", dataIndex: "workspace_id", width: 100, render: (value) => value || "全局" },
    { title: "名称", dataIndex: "name", width: 180 },
    { title: "分类", dataIndex: "category", width: 120 },
    { title: "状态", dataIndex: "enabled", width: 100, render: (enabled) => <Tag color={enabled ? "green" : "red"}>{enabled ? "启用" : "停用"}</Tag> },
    { title: "Prompt", dataIndex: "prompt", ellipsis: true },
    {
      title: "操作",
      width: 180,
      render: (_, row) => (
        <Space>
          <Button disabled={!canWrite} onClick={() => updateMutation.mutate({ id: row.id, enabled: !row.enabled })}>{row.enabled ? "停用" : "启用"}</Button>
          <Button danger disabled={!canWrite} onClick={() => modal.confirm({ title: "确认删除模板？", onOk: () => deleteMutation.mutate(row.id) })}>删除</Button>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Card
        title="模板列表"
        className="console-card"
        extra={(
          <Space>
            <Button type="primary" icon={<PlusOutlined />} disabled={!canWrite} onClick={() => setCreateOpen(true)}>
              新增模板
            </Button>
            <Button disabled={!canWrite} onClick={() => setImportOpen(true)}>
              模板导入
            </Button>
            <Button disabled={!canWrite} loading={seedMutation.isPending} onClick={() => seedMutation.mutate()}>导入内置模板</Button>
            <Button onClick={() => adminApi.exportTemplates(token, workspaceId).then((rows) => downloadJson("freecadai_templates.json", { templates: rows }))}>导出 JSON</Button>
          </Space>
        )}
      >
        <Table rowKey="id" className="template-table balanced-table" columns={columns} dataSource={templates.data || []} loading={templates.isLoading} scroll={{ x: 1260 }} tableLayout="fixed" pagination={{ pageSize: 10 }} />
      </Card>

      <Modal title="新增模板" open={createOpen} onCancel={() => setCreateOpen(false)} footer={null} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ category: "通用", enabled: true }} onFinish={(values) => createMutation.mutate(values)}>
          <Row gutter={12}>
            <Col xs={24} md={10}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item name="category" label="分类"><Select options={templateCategoryOptions} /></Form.Item></Col>
            <Col xs={24} md={6}><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          <Form.Item name="prompt" label="Prompt" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createMutation.isPending} block>保存模板</Button>
        </Form>
      </Modal>

      <Modal title="模板导入" open={importOpen} onCancel={() => { setImportOpen(false); setImportText(""); }} footer={null} destroyOnClose>
        <Space direction="vertical" size={12} className="full-width">
          <Input.TextArea rows={6} value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='{"templates":[{"name":"...","category":"通用","prompt":"...","enabled":true}]}' />
          <Button type="primary" disabled={!canWrite || !importText.trim()} onClick={importTemplates} block>导入 JSON</Button>
        </Space>
      </Modal>
    </Space>
  );
}

function KeysView({ role, workspaces }: { role?: string; workspaces: Workspace[] }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const queryClient = useQueryClient();
  const { message, modal } = AntApp.useApp();
  const [form] = Form.useForm();
  const [createdKey, setCreatedKey] = useState<string>("");
  const canWrite = canOperate(role);
  const keys = useQuery({ queryKey: ["apiKeys", token, workspaceId], queryFn: () => adminApi.apiKeys(token, workspaceId), enabled: Boolean(token) });
  const workspaceNameById = useMemo(
    () => new Map(workspaces.map((workspace) => [workspace.id, workspace.name])),
    [workspaces]
  );
  const workspaceOptions = workspaces.length
    ? workspaces.map((workspace) => ({ value: workspace.id, label: `${workspace.name}（ID ${workspace.id}）` }))
    : [{ value: 1, label: "默认工作区（ID 1）" }];
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["apiKeys"] });
  const createMutation = useMutation({
    mutationFn: (values: { name: string; workspace_id: number }) => adminApi.createApiKey(token, values),
    onSuccess: (data) => {
      setCreatedKey(data.api_key);
      message.success("API Key 已创建，只显示这一次");
      invalidate();
    }
  });
  const revokeMutation = useMutation({ mutationFn: (id: number) => adminApi.revokeApiKey(token, id), onSuccess: invalidate });
  const enableMutation = useMutation({ mutationFn: (id: number) => adminApi.enableApiKey(token, id), onSuccess: invalidate });

  const columns: ColumnsType<ApiKey> = [
    { title: "ID", dataIndex: "id", width: 72 },
    {
      title: "工作区",
      dataIndex: "workspace_id",
      width: 250,
      render: (value: number) => workspaceNameById.get(value) ? `${workspaceNameById.get(value)}（ID ${value}）` : `工作区 ID ${value}`
    },
    { title: "名称", dataIndex: "name" },
    { title: "前缀", dataIndex: "prefix", width: 140 },
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{statusLabel[status] || status}</Tag> },
    { title: "最近使用", dataIndex: "last_used_at", width: 170, render: (value) => formatShanghaiTime(value) },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 180,
      render: (_, row) => (
        <Space>
          <Button danger disabled={!canWrite || row.status === "revoked"} onClick={() => modal.confirm({ title: "确认撤销这个 Key？", onOk: () => revokeMutation.mutate(row.id) })}>撤销</Button>
          <Button disabled={!canWrite || row.status === "active"} onClick={() => enableMutation.mutate(row.id)}>启用</Button>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Card title="创建插件 API Key" className="console-card">
        <Form form={form} layout="inline" initialValues={{ name: "Plugin Key", workspace_id: workspaceId || workspaces[0]?.id || 1 }} onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item name="name" label="名称"><Input placeholder="Plugin Key" /></Form.Item>
          <Form.Item name="workspace_id" label="工作区" rules={[{ required: true }]}>
            <Select style={{ minWidth: 220 }} options={workspaceOptions} />
          </Form.Item>
          <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createMutation.isPending}>创建</Button>
        </Form>
        {createdKey ? <Alert style={{ marginTop: 14 }} type="success" showIcon message="新 Key" description={<Text copyable>{createdKey}</Text>} /> : null}
      </Card>
      <Card title="密钥列表" className="console-card">
        <Table rowKey="id" className="api-key-table" columns={columns} dataSource={keys.data || []} loading={keys.isLoading} scroll={{ x: 1380 }} tableLayout="fixed" pagination={{ pageSize: 10 }} />
      </Card>
    </Space>
  );
}

function AdminUsersView({ role }: { role?: string }) {
  const token = useAppStore((state) => state.token);
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const [createForm] = Form.useForm();
  const canWrite = canManageAdmins(role);
  const users = useQuery({ queryKey: ["adminUsers", token], queryFn: () => adminApi.adminUsers(token), enabled: Boolean(token && canWrite), retry: false });
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["adminUsers"] });
  const createMutation = useMutation({
    mutationFn: (values: { username: string; password: string; role: string; status: string }) => adminApi.createAdminUser(token, values),
    onSuccess: () => {
      message.success("管理员已创建");
      createForm.resetFields();
      invalidate();
    }
  });
  const updateMutation = useMutation({ mutationFn: ({ id, body }: { id: number; body: Partial<{ role: string; status: string; password: string }> }) => adminApi.updateAdminUser(token, id, body), onSuccess: invalidate });


  const columns: ColumnsType<AdminUser> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "用户名", dataIndex: "username" },
    { title: "角色", dataIndex: "role", width: 120, render: (role) => <Tag>{adminRoleLabel[role] || role}</Tag> },
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{statusLabel[status] || status}</Tag> },
    { title: "最近登录", dataIndex: "last_login_at", width: 170, render: (value) => formatShanghaiTime(value) },
    { title: "创建时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 220,
      render: (_, row) => (
        <Space>
          <Button disabled={!canWrite} onClick={() => updateMutation.mutate({ id: row.id, body: { status: row.status === "active" ? "suspended" : "active" } })}>{row.status === "active" ? "停用" : "启用"}</Button>
          <Button danger disabled={!canWrite} onClick={() => {
            const password = window.prompt("请输入新密码，至少 8 位");
            if (password) updateMutation.mutate({ id: row.id, body: { password } });
          }}>重置密码</Button>
        </Space>
      )
    }
  ];

  return (
    <Space direction="vertical" size={16} className="full-width">
      <Card title="创建管理员" className="console-card">
        <Form form={createForm} layout="inline" initialValues={{ role: "operator", status: "active" }} onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item name="username" rules={[{ required: true }]}><Input placeholder="用户名" /></Form.Item>
          <Form.Item name="password" rules={[{ required: true, min: 8 }]}><Input.Password placeholder="初始密码" /></Form.Item>
          <Form.Item name="role"><Select style={{ width: 130 }} options={adminRoleOptions} /></Form.Item>
          <Form.Item name="status"><Select style={{ width: 130 }} options={statusOptions} /></Form.Item>
          <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createMutation.isPending}>创建</Button>
        </Form>
      </Card>
      <Card title="管理员列表" className="console-card">
        {!canWrite ? <Alert type="info" showIcon message="当前角色不能查看或维护管理员列表" /> : <Table rowKey="id" className="admin-user-table balanced-table" columns={columns} dataSource={users.data || []} loading={users.isLoading} scroll={{ x: 1040 }} tableLayout="fixed" pagination={false} />}
      </Card>
    </Space>
  );
}

function AuditView({ workspaces }: { workspaces: Workspace[] }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const logs = useQuery({ queryKey: ["auditLogs", token, workspaceId], queryFn: () => adminApi.auditLogs(token, workspaceId), enabled: Boolean(token) });
  const workspaceNameById = useMemo(
    () => new Map(workspaces.map((workspace) => [workspace.id, workspace.name])),
    [workspaces]
  );
  const displayWorkspace = (value?: number | null) => value ? (workspaceNameById.get(value) || `工作区 ID ${value}`) : "-";
  const columns: ColumnsType<AuditLog> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "时间", dataIndex: "created_at", width: 180, render: (value) => formatShanghaiTime(value) },
    { title: "操作者", dataIndex: "actor", width: 150 },
    { title: "动作", dataIndex: "action", width: 180 },
    { title: "对象", width: 160, render: (_, row) => `${row.target_type} #${row.target_id}` },
    { title: "工作区", dataIndex: "workspace_id", width: 100, render: (value) => value || "-" },
    { title: "详情", dataIndex: "metadata", render: (value) => <Text code>{JSON.stringify(value).slice(0, 180)}</Text> }
  ];
  const displayColumns: ColumnsType<AuditLog> = columns.map((column) =>
    "dataIndex" in column && column.dataIndex === "workspace_id"
      ? {
          ...column,
          width: 293,
          render: (value) => displayWorkspace(value)
        }
      : column
  );
  return (
    <Card title="审计日志" className="console-card">
      <Table rowKey="id" className="audit-log-table balanced-table" columns={displayColumns} dataSource={logs.data || []} loading={logs.isLoading} scroll={{ x: 1393 }} tableLayout="fixed" pagination={{ pageSize: 15 }} />
    </Card>
  );
}

export default function AdminPage() {
  return (
    <Providers>
      <ConsolePageContent />
    </Providers>
  );
}
