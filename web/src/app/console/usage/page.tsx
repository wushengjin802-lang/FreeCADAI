"use client";

import { BarChartOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Col, Progress, Row, Space, Statistic, Table, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ConsoleUsageMemberItem, ConsoleUsageProjectItem, UsageDailyItem } from "@/lib/types";

const { Text, Title } = Typography;

function money(value?: number) {
  return `$${Number(value || 0).toFixed(4)}`;
}

export default function ConsoleUsagePage() {
  const router = useRouter();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);

  useEffect(() => {
    if (!token) router.replace(routePath("/console/login"));
  }, [router, token]);

  const meQuery = useQuery({ queryKey: ["console-me", token], queryFn: () => consoleApi.me(token), enabled: Boolean(token) });
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
  const canSeeWorkspace = canManageWorkspace(workspace?.role);
  const usage = useQuery({ queryKey: ["console-usage", token, workspace?.id], queryFn: () => consoleApi.usage(token, workspace?.id as number), enabled: Boolean(token && workspace?.id) });
  const daily = useQuery({ queryKey: ["console-usage-daily", token, workspace?.id], queryFn: () => consoleApi.usageDaily(token, workspace?.id as number), enabled: Boolean(token && workspace?.id) });
  const byMember = useQuery({ queryKey: ["console-usage-member", token, workspace?.id], queryFn: () => consoleApi.usageByMember(token, workspace?.id as number), enabled: Boolean(token && workspace?.id) });
  const byProject = useQuery({ queryKey: ["console-usage-project", token, workspace?.id], queryFn: () => consoleApi.usageByProject(token, workspace?.id as number), enabled: Boolean(token && workspace?.id) });

  const maxDailyTasks = Math.max(1, ...(daily.data || []).map((item) => item.task_count));
  const memberColumns: ColumnsType<ConsoleUsageMemberItem> = [
    { title: "成员", dataIndex: "display_name", width: 220, render: (value, row) => <Space direction="vertical" size={0}><Text strong>{value || row.email || "未绑定用户"}</Text><Text className="muted">{row.email}</Text></Space> },
    { title: "任务", dataIndex: "task_count", width: 120 },
    { title: "输入 Token", dataIndex: "input_tokens", width: 150 },
    { title: "输出 Token", dataIndex: "output_tokens", width: 150 },
    { title: "总 Token", dataIndex: "total_tokens", width: 150 },
    { title: "成本", dataIndex: "estimated_cost", width: 140, render: money }
  ];
  const projectColumns: ColumnsType<ConsoleUsageProjectItem> = [
    { title: "项目名称", dataIndex: "project_id", width: 220 },
    { title: "任务", dataIndex: "task_count", width: 120 },
    { title: "输入 Token", dataIndex: "input_tokens", width: 150 },
    { title: "输出 Token", dataIndex: "output_tokens", width: 150 },
    { title: "总 Token", dataIndex: "total_tokens", width: 150 },
    { title: "成本", dataIndex: "estimated_cost", width: 140, render: money }
  ];
  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}><BarChartOutlined /> 用量看板</Title>
            <Text className="muted">{canSeeWorkspace ? "当前展示工作区整体用量。" : "当前展示你的个人任务和个人消耗。"}</Text>
          </div>
        </section>
        {meQuery.error || usage.error ? <Alert type="error" showIcon message={((meQuery.error || usage.error) as Error).message} /> : null}
        {!canSeeWorkspace ? <Alert type="info" showIcon message="成员/观察者默认只能查看个人用量；拥有者/管理员可查看工作区整体用量。" /> : null}

        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="任务总数" value={usage.data?.task_count || 0} /></Card></Col>
          <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="成功任务" value={usage.data?.succeeded_count || 0} /></Card></Col>
          <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="总 Token" value={usage.data?.total_tokens || 0} /></Card></Col>
          <Col xs={24} sm={12} lg={6}><Card className="console-card metric-card"><Statistic title="估算成本" value={money(usage.data?.estimated_cost)} /></Card></Col>
        </Row>

        <Card className="console-card" title="近 14 天任务">
          <Space direction="vertical" size={10} className="full-width">
            {(daily.data || []).map((item: UsageDailyItem) => (
              <div className="enterprise-usage-row" key={item.day}>
                <Text>{item.day}</Text>
                <Progress percent={Math.round((item.task_count / maxDailyTasks) * 100)} showInfo={false} />
                <Text>{item.task_count} 个任务 · {item.total_tokens} token</Text>
              </div>
            ))}
          </Space>
        </Card>

        <Row gutter={[16, 16]}>
          <Col xs={24} xl={12}>
            <Card className="console-card" title="按项目">
              <Table rowKey="project_id" columns={projectColumns} dataSource={byProject.data || []} loading={byProject.isLoading} pagination={false} scroll={{ x: 930 }} tableLayout="fixed" />
            </Card>
          </Col>
          <Col xs={24} xl={12}>
            <Card className="console-card" title={canSeeWorkspace ? "按成员" : "我的消耗"}>
              <Table rowKey={(row) => String(row.user_id || row.email)} className="enterprise-usage-member-table" columns={memberColumns} dataSource={byMember.data || []} loading={byMember.isLoading} pagination={false} scroll={{ x: 930 }} tableLayout="fixed" />
            </Card>
          </Col>
        </Row>
      </Space>
    </ConsoleShell>
  );
}
