"use client";

import { ApiOutlined, CheckCircleOutlined, KeyOutlined, LoginOutlined } from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Card, Col, Descriptions, Row, Space, Spin, Steps, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Paragraph, Text, Title } = Typography;

export default function ConsolePluginPage() {
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

  const guideQuery = useQuery({
    queryKey: ["console-plugin-guide", token, workspace?.id],
    queryFn: () => consoleApi.pluginGuide(token, workspace?.id as number),
    enabled: Boolean(token && workspace?.id)
  });

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}>
              <ApiOutlined /> 插件接入
            </Title>
            <Text className="muted">企业用户可以在 FreeCAD 插件内登录账号、选择工作区并绑定 API Key。</Text>
          </div>
        </section>

        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {guideQuery.error ? <Alert type="error" showIcon message={(guideQuery.error as Error).message} /> : null}
        {guideQuery.isLoading ? <Spin /> : null}

        <Row gutter={[16, 16]}>
          <Col xs={24} lg={14}>
            <Card className="console-card" title="接入向导">
              <Steps
                direction="vertical"
                items={[
                  {
                    title: "填写 SaaS Base URL",
                    icon: <ApiOutlined />,
                    description: guideQuery.data?.saas_base_url || "加载中"
                  },
                  {
                    title: "在插件内登录企业账号",
                    icon: <LoginOutlined />,
                    description: "使用 /api/v1/plugin/account/login，账号为企业用户邮箱。旧管理员账号仍处于兼容期。"
                  },
                  {
                    title: "选择工作区并绑定",
                    icon: <KeyOutlined />,
                    description: "拥有者/管理员 可生成插件 API Key；成员/观察者 只能使用已绑定配置。"
                  },
                  {
                    title: "检查连接",
                    icon: <CheckCircleOutlined />,
                    description: "插件通过 /api/v1/plugin/auth/verify 验证 Key 是否可用。"
                  }
                ]}
              />
            </Card>
          </Col>
          <Col xs={24} lg={10}>
            <Card className="console-card" title="当前工作区">
              <Descriptions column={1} size="small" bordered>
                <Descriptions.Item label="工作区">{workspace?.name || "-"}</Descriptions.Item>
                <Descriptions.Item label="角色">{workspace?.role || "-"}</Descriptions.Item>
                <Descriptions.Item label="套餐">{workspace?.plan || "-"}</Descriptions.Item>
                <Descriptions.Item label="API Key 数">{workspace?.api_key_count ?? 0}</Descriptions.Item>
              </Descriptions>
            </Card>
          </Col>
        </Row>

        <Card className="console-card" title="插件配置">
          <Descriptions column={1} bordered>
            <Descriptions.Item label="SaaS Base URL">
              <Text copyable>{guideQuery.data?.saas_base_url || "-"}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="登录接口">
              <Text copyable>{guideQuery.data?.login_path || "/api/v1/plugin/account/login"}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="绑定接口">
              <Text copyable>{guideQuery.data?.bind_path || "/api/v1/plugin/account/bind-workspace"}</Text>
            </Descriptions.Item>
            <Descriptions.Item label="验证接口">
              <Text copyable>{guideQuery.data?.verify_path || "/api/v1/plugin/auth/verify"}</Text>
            </Descriptions.Item>
          </Descriptions>
          <Paragraph className="muted" style={{ marginTop: 14, marginBottom: 0 }}>
            API Key 明文只会在创建或轮换时显示一次，请保存到 FreeCAD 插件配置中。
          </Paragraph>
        </Card>
      </Space>
    </ConsoleShell>
  );
}
