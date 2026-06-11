"use client";

import { AuditOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Input, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { AuditLog } from "@/lib/types";

const { Text, Title } = Typography;

export default function ConsoleAuditPage() {
  const router = useRouter();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [action, setAction] = useState("");

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
  const canView = canManageWorkspace(workspace?.role);
  const logs = useQuery({
    queryKey: ["console-audit", token, workspace?.id, action],
    queryFn: () => consoleApi.auditLogs(token, workspace?.id as number, action),
    enabled: Boolean(token && workspace?.id && canView)
  });

  const columns: ColumnsType<AuditLog> = [
    { title: "时间", dataIndex: "created_at", width: 180 },
    { title: "操作者", dataIndex: "actor", width: 150 },
    { title: "动作", dataIndex: "action", width: 230, render: (value) => <Tag>{value}</Tag> },
    { title: "对象", width: 170, render: (_, row) => `${row.target_type} #${row.target_id}` },
    { title: "详情", dataIndex: "metadata", render: (value) => <Text code>{JSON.stringify(value).slice(0, 220)}</Text> }
  ];

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}><AuditOutlined /> 审计日志</Title>
            <Text className="muted">按当前工作区查看企业侧关键操作记录。</Text>
          </div>
        </section>

        {meQuery.error || logs.error ? <Alert type="error" showIcon message={((meQuery.error || logs.error) as Error).message} /> : null}
        {!canView ? <Alert type="info" showIcon message="审计日志仅 Owner/Admin 可查看。" /> : null}
        {canView ? (
          <Card className="console-card">
            <Space wrap style={{ marginBottom: 16 }}>
              <Input.Search allowClear placeholder="按 action 精确过滤" onSearch={setAction} style={{ width: 300 }} />
            </Space>
            <Table rowKey="id" className="enterprise-audit-table" columns={columns} dataSource={logs.data || []} loading={logs.isLoading} pagination={{ pageSize: 15 }} scroll={{ x: 980 }} />
          </Card>
        ) : null}
      </Space>
    </ConsoleShell>
  );
}
