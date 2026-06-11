"use client";

import { FileTextOutlined, PlusOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Input, Select, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { formatShanghaiTime } from "@/lib/format";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ConsoleTaskListItem } from "@/lib/types";

const { Text, Title } = Typography;

const taskStatusLabel: Record<string, string> = {
  queued: "排队中",
  running: "生成中",
  succeeded: "已成功",
  failed: "已失败",
  canceled: "已取消"
};

function statusColor(status: string) {
  if (status === "succeeded") return "green";
  if (status === "failed") return "red";
  if (status === "queued" || status === "running") return "gold";
  if (status === "canceled") return "default";
  return "blue";
}

export default function ConsoleTasksPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);

  useEffect(() => {
    if (!token) router.replace(routePath("/console/login"));
  }, [router, token]);

  const meQuery = useQuery({
    queryKey: ["console-me", token],
    queryFn: () => consoleApi.me(token),
    enabled: Boolean(token)
  });

  useEffect(() => {
    if (meQuery.data) {
      setUser(meQuery.data.user);
      setWorkspaces(meQuery.data.workspaces);
    }
  }, [meQuery.data, setUser, setWorkspaces]);

  const workspace = useMemo(
    () => meQuery.data?.workspaces.find((item) => item.id === workspaceId) || meQuery.data?.workspaces[0],
    [meQuery.data?.workspaces, workspaceId]
  );
  const canWriteTask = workspace?.role === "owner" || workspace?.role === "admin" || workspace?.role === "member";
  const canOperateTask = canWriteTask || canManageWorkspace(workspace?.role);

  const tasksQuery = useQuery({
    queryKey: ["console-tasks", token, workspace?.id, q, status, mine],
    queryFn: () => consoleApi.tasks(token, { workspace_id: workspace?.id as number, q, status, mine }),
    enabled: Boolean(token && workspace?.id)
  });

  const cancelMutation = useMutation({
    mutationFn: (id: number) => consoleApi.cancelTask(token, id),
    onSuccess: (result) => {
      message[result.ok ? "success" : "warning"](result.message || "任务状态已更新");
      queryClient.invalidateQueries({ queryKey: ["console-tasks"] });
    }
  });

  const retryMutation = useMutation({
    mutationFn: (id: number) => consoleApi.retryTask(token, id),
    onSuccess: (result) => {
      message[result.ok ? "success" : "warning"](result.message || "任务状态已更新");
      queryClient.invalidateQueries({ queryKey: ["console-tasks"] });
    }
  });

  const columns: ColumnsType<ConsoleTaskListItem> = [
    {
      title: "任务",
      dataIndex: "prompt",
      render: (value, row) => (
        <Space direction="vertical" size={0}>
          <Button type="link" style={{ padding: 0, height: "auto", textAlign: "left" }} onClick={() => router.push(routePath(`/console/tasks/${row.id}`))}>
            #{row.id} {String(value).slice(0, 80)}
          </Button>
          <Text className="muted">
            {row.project_id || "未归档项目"} · {row.modeling_mode} · {row.source}
          </Text>
        </Space>
      )
    },
    { title: "状态", dataIndex: "status", width: 120, render: (value) => <Tag color={statusColor(value)}>{taskStatusLabel[value] || value}</Tag> },
    { title: "模型", dataIndex: "model", width: 180 },
    { title: "耗时", dataIndex: "latency_ms", width: 110, render: (value) => (value ? `${value} ms` : "-") },
    { title: "创建时间", dataIndex: "created_at", width: 190, render: (value) => formatShanghaiTime(value) },
    {
      title: "操作",
      width: 220,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button
            size="small"
            icon={<StopOutlined />}
            disabled={!canOperateTask || !["queued", "running"].includes(row.status)}
            onClick={() => cancelMutation.mutate(row.id)}
          >
            取消
          </Button>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            disabled={!canOperateTask || !["failed", "canceled"].includes(row.status)}
            onClick={() => retryMutation.mutate(row.id)}
          >
            重试
          </Button>
        </Space>
      )
    }
  ];

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}>
              <FileTextOutlined /> 任务中心
            </Title>
            <Text className="muted">查看 Web 和插件提交的生成任务，跟踪状态并进入脚本结果。</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} disabled={!canWriteTask} onClick={() => router.push(routePath("/console/tasks/new"))}>
            新建任务
          </Button>
        </section>

        {workspace?.role === "viewer" ? <Alert type="info" showIcon message="观察者角色只能查看任务，不能新建、取消或重试。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {tasksQuery.error ? <Alert type="error" showIcon message={(tasksQuery.error as Error).message} /> : null}
        {cancelMutation.error ? <Alert type="error" showIcon message={(cancelMutation.error as Error).message} /> : null}
        {retryMutation.error ? <Alert type="error" showIcon message={(retryMutation.error as Error).message} /> : null}

        <Card className="console-card">
          <Space wrap style={{ marginBottom: 16 }}>
            <Input.Search allowClear placeholder="搜索 Prompt / 项目 / 错误" onSearch={setQ} style={{ width: 280 }} />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 150 }}
              value={status || undefined}
              onChange={(value) => setStatus(value || "")}
              options={["queued", "running", "succeeded", "failed", "canceled"].map((item) => ({ value: item, label: taskStatusLabel[item] || item }))}
            />
            <Space>
              <Switch checked={mine} onChange={setMine} />
              <Text>只看我的</Text>
            </Space>
          </Space>
          <Table
            rowKey="id"
            className="enterprise-tasks-table"
            columns={columns}
            dataSource={tasksQuery.data || []}
            loading={tasksQuery.isLoading}
            pagination={false}
            scroll={{ x: 1100 }}
          />
        </Card>
      </Space>
    </ConsoleShell>
  );
}
