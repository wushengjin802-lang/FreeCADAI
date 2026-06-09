"use client";

import {
  ApiOutlined,
  AuditOutlined,
  BarChartOutlined,
  DatabaseOutlined,
  KeyOutlined,
  LogoutOutlined,
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
import type { AdminUser, ApiKey, AuditLog, BillingSummary, TaskDetail, TaskListItem, Template, UsageByModelItem, Workspace } from "@/lib/types";

const { Content, Sider } = Layout;
const { Text, Title } = Typography;

type ViewKey = "dashboard" | "workspaces" | "tasks" | "templates" | "keys" | "adminUsers" | "audit";

const taskLimit = 50;

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

function formatLimit(value?: number | null) {
  return value == null ? "不限" : String(value);
}

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
  const option = useMemo(
    () => ({
      tooltip: { trigger: "axis" },
      legend: { top: 0 },
      grid: { left: 28, right: 16, top: 44, bottom: 28 },
      xAxis: { type: "category", data: daily.map((item) => item.day) },
      yAxis: { type: "value" },
      series: [
        { name: "任务", type: "line", smooth: true, data: daily.map((item) => item.task_count), color: "#355263" },
        { name: "成功", type: "line", smooth: true, data: daily.map((item) => item.succeeded_count), color: "#16734a" },
        { name: "失败", type: "line", smooth: true, data: daily.map((item) => item.failed_count), color: "#a23b3b" },
        { name: "Token", type: "bar", data: daily.map((item) => item.total_tokens), color: "#9a6a24" }
      ]
    }),
    [daily]
  );
  const warnings = billing?.workspaces.flatMap((workspace) => workspace.warnings.map((warning) => `${workspace.workspace_name}: ${warning}`)) || [];
  const modelColumns: ColumnsType<UsageByModelItem> = [
    { title: "Provider", dataIndex: "provider", width: 150 },
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
      <Card title="近 14 天用量趋势" className="console-card">
        <ReactECharts option={option} style={{ height: 330 }} />
      </Card>
      <Card title="按模型用量" className="console-card">
        <Table rowKey={(row) => `${row.provider}-${row.model}`} columns={modelColumns} dataSource={usageByModel} pagination={false} scroll={{ x: 950 }} />
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
    { title: "套餐", dataIndex: "plan", width: 120 },
    { title: "状态", dataIndex: "status", width: 120, render: (status) => <Tag color={statusColor(status)}>{status}</Tag> },
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
    { title: "创建时间", dataIndex: "created_at", width: 180 },
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
          <Form.Item name="plan"><Select style={{ width: 130 }} options={["free", "pro", "team", "enterprise"].map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="status"><Select style={{ width: 140 }} options={["active", "suspended"].map((value) => ({ value }))} /></Form.Item>
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
            <Select options={["free", "pro", "team", "enterprise"].map((value) => ({ value }))} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={["active", "suspended"].map((value) => ({ value }))} />
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
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{status}</Tag> },
    { title: "动作", dataIndex: "action", width: 110 },
    { title: "模式", dataIndex: "modeling_mode", width: 130 },
    { title: "模型", dataIndex: "model", width: 160 },
    { title: "需求", dataIndex: "prompt", ellipsis: true },
    { title: "创建时间", dataIndex: "created_at", width: 180 },
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

function TemplatesView({ role }: { role?: string }) {
  const token = useAppStore((state) => state.token);
  const workspaceId = useAppStore((state) => state.workspaceId);
  const queryClient = useQueryClient();
  const { message, modal } = AntApp.useApp();
  const [form] = Form.useForm();
  const [importText, setImportText] = useState("");
  const canWrite = canOperate(role);
  const templates = useQuery({ queryKey: ["templates", token, workspaceId], queryFn: () => adminApi.templates(token, workspaceId), enabled: Boolean(token) });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["templates"] });
  const createMutation = useMutation({
    mutationFn: (values: { name: string; category: string; prompt: string; enabled: boolean }) =>
      adminApi.createTemplate(token, { ...values, workspace_id: workspaceId }),
    onSuccess: () => {
      message.success("模板已保存");
      form.resetFields();
      invalidate();
    }
  });
  const updateMutation = useMutation({ mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => adminApi.updateTemplate(token, id, { enabled }), onSuccess: invalidate });
  const deleteMutation = useMutation({ mutationFn: (id: number) => adminApi.deleteTemplate(token, id), onSuccess: invalidate });

  const importTemplates = () => {
    try {
      const parsed = JSON.parse(importText) as { templates?: Array<Omit<Template, "id">> } | Array<Omit<Template, "id">>;
      const rows = Array.isArray(parsed) ? parsed : parsed.templates || [];
      const scopedRows = rows.map((row) => ({ ...row, workspace_id: workspaceId ?? row.workspace_id ?? null }));
      adminApi.importTemplates(token, scopedRows).then(() => {
        message.success("模板已导入");
        setImportText("");
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
      <Card title="新增模板" className="console-card">
        <Form form={form} layout="vertical" initialValues={{ category: "common", enabled: true }} onFinish={(values) => createMutation.mutate(values)}>
          <Row gutter={12}>
            <Col xs={24} md={10}><Form.Item name="name" label="名称" rules={[{ required: true }]}><Input /></Form.Item></Col>
            <Col xs={24} md={8}><Form.Item name="category" label="分类"><Input /></Form.Item></Col>
            <Col xs={24} md={6}><Form.Item name="enabled" label="启用" valuePropName="checked"><Switch /></Form.Item></Col>
          </Row>
          <Form.Item name="prompt" label="Prompt" rules={[{ required: true }]}><Input.TextArea rows={4} /></Form.Item>
          <Button type="primary" htmlType="submit" disabled={!canWrite} loading={createMutation.isPending}>保存模板</Button>
        </Form>
      </Card>
      <Card title="模板导入" className="console-card" extra={<Button type="primary" disabled={!canWrite} onClick={importTemplates}>导入 JSON</Button>}>
        <Input.TextArea rows={4} value={importText} onChange={(event) => setImportText(event.target.value)} placeholder='{"templates":[{"name":"...","category":"common","prompt":"...","enabled":true}]}' />
      </Card>
      <Card title="模板列表" className="console-card" extra={<Button onClick={() => adminApi.exportTemplates(token, workspaceId).then((rows) => downloadJson("freecadai_templates.json", { templates: rows }))}>导出 JSON</Button>}>
        <Table rowKey="id" className="template-table balanced-table" columns={columns} dataSource={templates.data || []} loading={templates.isLoading} scroll={{ x: 1260 }} tableLayout="fixed" pagination={{ pageSize: 10 }} />
      </Card>
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
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{status}</Tag> },
    { title: "最近使用", dataIndex: "last_used_at", width: 170, render: (value) => value || "-" },
    { title: "创建时间", dataIndex: "created_at", width: 180 },
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
    { title: "角色", dataIndex: "role", width: 120 },
    { title: "状态", dataIndex: "status", width: 110, render: (status) => <Tag color={statusColor(status)}>{status}</Tag> },
    { title: "最近登录", dataIndex: "last_login_at", width: 170, render: (value) => value || "-" },
    { title: "创建时间", dataIndex: "created_at", width: 180 },
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
          <Form.Item name="role"><Select style={{ width: 130 }} options={["operator", "owner", "viewer"].map((value) => ({ value }))} /></Form.Item>
          <Form.Item name="status"><Select style={{ width: 130 }} options={["active", "suspended"].map((value) => ({ value }))} /></Form.Item>
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
  const columns: ColumnsType<AuditLog> = [
    { title: "ID", dataIndex: "id", width: 80 },
    { title: "时间", dataIndex: "created_at", width: 180 },
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
          width: 180,
          render: (value) => value ? (workspaceNameById.get(value) ? `${workspaceNameById.get(value)}（ID ${value}）` : `工作区 ID ${value}`) : "-"
        }
      : column
  );
  return (
    <Card title="审计日志" className="console-card">
      <Table rowKey="id" columns={displayColumns} dataSource={logs.data || []} loading={logs.isLoading} scroll={{ x: 1130 }} pagination={{ pageSize: 15 }} />
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
