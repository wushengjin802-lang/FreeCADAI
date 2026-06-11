"use client";

import { ApiOutlined, AppstoreOutlined, DatabaseOutlined, FileTextOutlined, KeyOutlined, TeamOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Empty, Progress, Row, Space, Spin, Statistic, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Paragraph, Text, Title } = Typography;

function limitText(value?: number | null) {
  return value == null ? "不限" : String(value);
}

export default function ConsoleHomePage() {
  const router = useRouter();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);

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

  if (!token) return null;

  return (
    <ConsoleShell>
      {meQuery.isLoading ? <Spin /> : null}
      {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
      {!meQuery.isLoading && !workspace ? (
        <Card className="console-card">
          <Empty description="暂无可访问的工作区" />
        </Card>
      ) : null}
      {workspace ? (
        <Space direction="vertical" size={18} className="full-width">
          <section className="enterprise-hero">
            <div>
              <Text className="enterprise-kicker">Workspace</Text>
              <Title level={2}>{workspace.name}</Title>
              <Paragraph>
                在这里统一管理团队成员、FreeCAD 插件接入、生成任务、企业模板和模型资产。
              </Paragraph>
            </div>
            <Button type="primary" icon={<TeamOutlined />} onClick={() => router.push(routePath("/console/members"))}>
              管理成员
            </Button>
          </section>

          <Row gutter={[16, 16]}>
            <Col xs={24} md={12} xl={6}>
              <Card className="console-card metric-card">
                <Statistic title="成员" value={workspace.member_count} prefix={<TeamOutlined />} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="console-card metric-card">
                <Statistic title="任务" value={workspace.task_count} prefix={<AppstoreOutlined />} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="console-card metric-card">
                <Statistic title="API Key" value={workspace.api_key_count} prefix={<ApiOutlined />} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="console-card metric-card">
                <Statistic title="资产" value={workspace.asset_count} prefix={<DatabaseOutlined />} />
              </Card>
            </Col>
          </Row>

          <Row gutter={[16, 16]}>
            <Col xs={24} lg={14}>
              <Card className="console-card" title="套餐额度">
                <Space direction="vertical" size={16} className="full-width">
                  <div className="enterprise-plan-row">
                    <Text strong>当前套餐</Text>
                    <Text>{workspace.plan}</Text>
                  </div>
                  <div>
                    <div className="enterprise-plan-row">
                      <Text>本周期任务</Text>
                      <Text>
                        {workspace.quota?.usage.task_count ?? 0} / {limitText(workspace.quota?.limits.tasks)}
                      </Text>
                    </div>
                    <Progress
                      percent={
                        workspace.quota?.limits.tasks
                          ? Math.min(100, Math.round(((workspace.quota.usage.task_count || 0) / workspace.quota.limits.tasks) * 100))
                          : 0
                      }
                      showInfo={false}
                    />
                  </div>
                  <div className="enterprise-plan-grid">
                    <span>模板上限：{limitText(workspace.quota?.limits.templates)}</span>
                    <span>API Key 上限：{limitText(workspace.quota?.limits.api_keys)}</span>
                    <span>并发上限：{limitText(workspace.quota?.limits.concurrent)}</span>
                    <span>预估成本：${Number(workspace.quota?.usage.estimated_cost || 0).toFixed(4)}</span>
                  </div>
                </Space>
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card className="console-card" title="常用入口">
                <Space direction="vertical" size={10} className="full-width">
                  <Button block icon={<FileTextOutlined />} onClick={() => router.push(routePath("/console/tasks"))}>
                    查看与提交生成任务
                  </Button>
                  <Button block icon={<AppstoreOutlined />} onClick={() => router.push(routePath("/console/templates"))}>
                    管理企业模板
                  </Button>
                  <Button block icon={<DatabaseOutlined />} onClick={() => router.push(routePath("/console/assets/models"))}>
                    上传与下载模型资产
                  </Button>
                  <Button block icon={<KeyOutlined />} onClick={() => router.push(routePath("/console/api-keys"))}>
                    配置插件 API Key
                  </Button>
                </Space>
              </Card>
            </Col>
          </Row>
        </Space>
      ) : null}
    </ConsoleShell>
  );
}
