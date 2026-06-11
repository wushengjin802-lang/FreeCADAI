"use client";

import { ArrowLeftOutlined, CopyOutlined, ReloadOutlined, StopOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Descriptions, Empty, Space, Tabs, Tag, Typography } from "antd";
import { useParams, useRouter } from "next/navigation";
import { useEffect } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { formatShanghaiTime } from "@/lib/format";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Paragraph, Text, Title } = Typography;

const taskStatusLabel: Record<string, string> = {
  queued: "排队中",
  running: "生成中",
  succeeded: "已成功",
  failed: "已失败",
  canceled: "已取消"
};

function statusColor(status?: string) {
  if (status === "succeeded") return "green";
  if (status === "failed") return "red";
  if (status === "queued" || status === "running") return "gold";
  if (status === "canceled") return "default";
  return "blue";
}

function jsonText(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export default function ConsoleTaskDetailPage() {
  const params = useParams<{ taskId: string }>();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const taskId = Number(params.taskId);

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

  const detailQuery = useQuery({
    queryKey: ["console-task-detail", token, taskId],
    queryFn: () => consoleApi.taskDetail(token, taskId),
    enabled: Boolean(token && taskId)
  });

  const cancelMutation = useMutation({
    mutationFn: () => consoleApi.cancelTask(token, taskId),
    onSuccess: (result) => {
      message[result.ok ? "success" : "warning"](result.message || "任务状态已更新");
      queryClient.invalidateQueries({ queryKey: ["console-task-detail"] });
    }
  });

  const retryMutation = useMutation({
    mutationFn: () => consoleApi.retryTask(token, taskId),
    onSuccess: (result) => {
      message[result.ok ? "success" : "warning"](result.message || "任务状态已更新");
      queryClient.invalidateQueries({ queryKey: ["console-task-detail"] });
    }
  });

  if (!token) return null;

  const task = detailQuery.data?.task || {};
  const status = String(task.status || "");
  const scripts = detailQuery.data?.scripts || [];
  const reports = detailQuery.data?.reports || [];
  const firstScript = scripts[0];

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}>任务 #{taskId}</Title>
            <Space>
              {status ? <Tag color={statusColor(status)}>{taskStatusLabel[status] || status}</Tag> : null}
              <Text className="muted">{String(task.model || "")}</Text>
            </Space>
          </div>
          <Space wrap>
            <Button icon={<ArrowLeftOutlined />} onClick={() => router.push(routePath("/console/tasks"))}>
              返回任务中心
            </Button>
            <Button icon={<StopOutlined />} disabled={!["queued", "running"].includes(status)} onClick={() => cancelMutation.mutate()}>
              取消
            </Button>
            <Button icon={<ReloadOutlined />} disabled={!["failed", "canceled"].includes(status)} onClick={() => retryMutation.mutate()}>
              重试
            </Button>
          </Space>
        </section>

        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {detailQuery.error ? <Alert type="error" showIcon message={(detailQuery.error as Error).message} /> : null}
        {cancelMutation.error ? <Alert type="error" showIcon message={(cancelMutation.error as Error).message} /> : null}
        {retryMutation.error ? <Alert type="error" showIcon message={(retryMutation.error as Error).message} /> : null}

        <Card className="console-card" loading={detailQuery.isLoading}>
          <Descriptions column={{ xs: 1, md: 2 }} bordered>
            <Descriptions.Item label="工作区">{String(task.workspace_id || "-")}</Descriptions.Item>
            <Descriptions.Item label="项目名称">{String(task.project_id || "-")}</Descriptions.Item>
            <Descriptions.Item label="来源">{String(task.source || "-")}</Descriptions.Item>
            <Descriptions.Item label="动作">{String(task.action || "-")}</Descriptions.Item>
            <Descriptions.Item label="模式">{String(task.modeling_mode || "-")}</Descriptions.Item>
            <Descriptions.Item label="耗时">{task.latency_ms ? `${task.latency_ms} ms` : "-"}</Descriptions.Item>
            <Descriptions.Item label="创建时间">{formatShanghaiTime(String(task.created_at || ""))}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{formatShanghaiTime(String(task.updated_at || ""))}</Descriptions.Item>
          </Descriptions>
        </Card>

        <Tabs
          items={[
            {
              key: "prompt",
              label: "需求与上下文",
              children: (
                <Space direction="vertical" size={16} className="full-width">
                  <Card className="console-card" title="Prompt">
                    <Paragraph>{String(task.prompt || "")}</Paragraph>
                  </Card>
                  <Card className="console-card" title="Context">
                    <pre className="pre-block">{String(task.context_snapshot || "") || "无"}</pre>
                  </Card>
                  {task.error_message ? (
                    <Alert type="error" showIcon message="错误信息" description={<pre className="enterprise-error-text">{String(task.error_message)}</pre>} />
                  ) : null}
                </Space>
              )
            },
            {
              key: "script",
              label: "生成脚本",
              children: firstScript ? (
                <Space direction="vertical" size={16} className="full-width">
                  <Card
                    className="console-card"
                    title={String(firstScript.summary || "脚本")}
                    extra={
                      <Button icon={<CopyOutlined />} onClick={() => navigator.clipboard.writeText(String(firstScript.script || ""))}>
                        复制脚本
                      </Button>
                    }
                  >
                    <pre className="pre-block">{String(firstScript.script || "")}</pre>
                  </Card>
                  <Card className="console-card" title="参数与预期对象">
                    <pre className="pre-block">{jsonText({ parameters: firstScript.parameters, expected_objects: firstScript.expected_objects })}</pre>
                  </Card>
                </Space>
              ) : (
                <Card className="console-card">
                  <Empty description="暂无生成脚本" />
                </Card>
              )
            },
            {
              key: "reports",
              label: "执行报告",
              children: reports.length ? (
                <Space direction="vertical" size={12} className="full-width">
                  {reports.map((report) => (
                    <Card key={String(report.id)} className="console-card" title={`报告 #${report.id}`}>
                      <pre className="pre-block">{jsonText(report)}</pre>
                    </Card>
                  ))}
                </Space>
              ) : (
                <Card className="console-card">
                  <Empty description="暂无插件执行报告" />
                </Card>
              )
            }
          ]}
        />
      </Space>
    </ConsoleShell>
  );
}
