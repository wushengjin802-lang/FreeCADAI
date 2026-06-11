"use client";

import { ApiOutlined, CreditCardOutlined, KeyOutlined, SaveOutlined, SettingOutlined, TeamOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Col, Descriptions, Form, Input, Progress, Row, Space, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { formatShanghaiTime } from "@/lib/format";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";

const { Text, Title } = Typography;

const roleLabel: Record<string, string> = {
  owner: "拥有者",
  admin: "管理员",
  member: "成员",
  viewer: "观察者"
};

function limitText(value?: number | null) {
  return value == null ? "不限" : String(value);
}

function usagePercent(used?: number, limit?: number | null) {
  if (!limit) return 0;
  return Math.min(100, Math.round(((used || 0) / limit) * 100));
}

export default function ConsoleSettingsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [form] = Form.useForm<{ name: string }>();

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
  const canManage = canManageWorkspace(workspace?.role);

  useEffect(() => {
    if (workspace) form.setFieldsValue({ name: workspace.name });
  }, [form, workspace]);

  const updateMutation = useMutation({
    mutationFn: (values: { name: string }) => consoleApi.updateWorkspace(token, workspace?.id as number, { name: values.name }),
    onSuccess: (updated) => {
      message.success("工作区设置已保存");
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
      setWorkspaces((meQuery.data?.workspaces || []).map((item) => (item.id === updated.id ? updated : item)));
    }
  });

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}>
              <SettingOutlined /> 工作区设置
            </Title>
            <Text className="muted">维护工作区基础信息，并查看成员、插件接入和套餐治理入口。</Text>
          </div>
        </section>

        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {!canManage ? <Alert type="info" showIcon message="当前角色可以查看工作区设置，修改名称需要拥有者/管理员权限。" /> : null}
        {workspace?.quota?.warnings?.length ? <Alert type="warning" showIcon message="额度提醒" description={workspace.quota.warnings.join("；")} /> : null}

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={14}>
            <Card className="console-card" title="基础信息">
              <Form form={form} layout="vertical" onFinish={(values) => updateMutation.mutate(values)}>
                <Form.Item name="name" label="工作区名称" rules={[{ required: true, message: "请输入工作区名称" }]}>
                  <Input maxLength={128} disabled={!canManage} />
                </Form.Item>
                <Button type="primary" icon={<SaveOutlined />} htmlType="submit" disabled={!canManage} loading={updateMutation.isPending}>
                  保存设置
                </Button>
              </Form>
              <Descriptions column={{ xs: 1, md: 2 }} style={{ marginTop: 24 }}>
                <Descriptions.Item label="工作区 ID">{workspace?.id || "-"}</Descriptions.Item>
                <Descriptions.Item label="当前角色">{workspace ? roleLabel[workspace.role] || workspace.role : "-"}</Descriptions.Item>
                <Descriptions.Item label="状态">{workspace?.status === "active" ? <Tag color="green">正常</Tag> : <Tag>{workspace?.status || "-"}</Tag>}</Descriptions.Item>
                <Descriptions.Item label="套餐">{workspace?.plan || "-"}</Descriptions.Item>
                <Descriptions.Item label="创建时间">{formatShanghaiTime(workspace?.created_at)}</Descriptions.Item>
                <Descriptions.Item label="成员数">{workspace?.member_count ?? "-"}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>

          <Col xs={24} lg={10}>
            <Card className="console-card" title="治理入口">
              <Space direction="vertical" size={10} className="full-width">
                <Button block icon={<TeamOutlined />} onClick={() => router.push(routePath("/console/members"))}>
                  成员与角色
                </Button>
                <Button block icon={<ApiOutlined />} onClick={() => router.push(routePath("/console/plugin"))}>
                  插件接入向导
                </Button>
                <Button block icon={<KeyOutlined />} onClick={() => router.push(routePath("/console/api-keys"))}>
                  API Key 管理
                </Button>
                <Button block icon={<CreditCardOutlined />} onClick={() => router.push(routePath("/console/billing"))}>
                  账单与套餐
                </Button>
              </Space>
            </Card>
          </Col>
        </Row>

        <Card className="console-card" title="套餐额度">
          <Space direction="vertical" size={16} className="full-width">
            <div>
              <div className="enterprise-plan-row">
                <Text>本周期任务</Text>
                <Text>{workspace?.quota?.usage.task_count ?? 0} / {limitText(workspace?.quota?.limits.tasks)}</Text>
              </div>
              <Progress percent={usagePercent(workspace?.quota?.usage.task_count, workspace?.quota?.limits.tasks)} />
            </div>
            <div className="enterprise-plan-grid">
              <span>模板：{workspace?.quota?.usage.template_count ?? 0} / {limitText(workspace?.quota?.limits.templates)}</span>
              <span>API Key：{workspace?.quota?.usage.api_key_count ?? 0} / {limitText(workspace?.quota?.limits.api_keys)}</span>
              <span>并发：{workspace?.quota?.usage.concurrent_count ?? 0} / {limitText(workspace?.quota?.limits.concurrent)}</span>
              <span>预估成本：${Number(workspace?.quota?.usage.estimated_cost || 0).toFixed(4)}</span>
            </div>
          </Space>
        </Card>
      </Space>
    </ConsoleShell>
  );
}
