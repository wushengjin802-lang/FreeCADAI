"use client";

import {
  ApiOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  CloudUploadOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  KeyOutlined,
  LoginOutlined,
  SafetyCertificateOutlined
} from "@ant-design/icons";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, Col, Descriptions, Row, Space, Spin, Steps, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Paragraph, Text, Title } = Typography;

const roleLabel: Record<string, string> = {
  owner: "拥有者",
  admin: "管理员",
  member: "成员",
  viewer: "观察者"
};

const planLabel: Record<string, string> = {
  free: "免费版",
  pro: "专业版",
  team: "团队版",
  enterprise: "企业版"
};

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
            <Text className="muted">配置 FreeCAD 插件连接企业工作区，使用模板生成任务，并回传模型资产。</Text>
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
                    title: "配置 SaaS Base URL",
                    icon: <ApiOutlined />,
                    description: guideQuery.data?.saas_base_url || "加载中"
                  },
                  {
                    title: "在插件内登录企业账号",
                    icon: <LoginOutlined />,
                    description: "使用企业用户邮箱登录插件，选择当前工作区后进入绑定流程。"
                  },
                  {
                    title: "绑定并管理 API Key",
                    icon: <KeyOutlined />,
                    description: "拥有者/管理员可创建、禁用和轮换插件 API Key；成员/观察者可使用已绑定配置。"
                  },
                  {
                    title: "使用企业模板提交任务",
                    icon: <FileTextOutlined />,
                    description: "插件可拉取系统模板和当前工作区企业模板，生成任务进入任务中心和脚本资产库。"
                  },
                  {
                    title: "回传模型资产",
                    icon: <CloudUploadOutlined />,
                    description: "插件可上传 FCStd/STEP/STL 等模型文件；STL 文件可在 Web 端预览。"
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
              <Space direction="vertical" size={16} className="full-width">
                <Descriptions column={1} size="small" bordered>
                  <Descriptions.Item label="工作区">{workspace?.name || "-"}</Descriptions.Item>
                  <Descriptions.Item label="角色">{workspace ? roleLabel[workspace.role] || workspace.role : "-"}</Descriptions.Item>
                  <Descriptions.Item label="套餐">{workspace ? planLabel[workspace.plan] || workspace.plan : "-"}</Descriptions.Item>
                  <Descriptions.Item label="API Key 数">{workspace?.api_key_count ?? 0}</Descriptions.Item>
                </Descriptions>
                <Space wrap>
                  <Tag icon={<SafetyCertificateOutlined />} color="green">企业账号认证</Tag>
                  <Tag icon={<AppstoreOutlined />} color="blue">模板拉取</Tag>
                  <Tag icon={<DatabaseOutlined />} color="purple">模型回传</Tag>
                </Space>
                <Space direction="vertical" className="full-width">
                  <Button block icon={<KeyOutlined />} onClick={() => router.push(routePath("/console/api-keys"))}>
                    管理插件 API Key
                  </Button>
                  <Button block icon={<AppstoreOutlined />} onClick={() => router.push(routePath("/console/templates"))}>
                    查看企业模板
                  </Button>
                  <Button block icon={<DatabaseOutlined />} onClick={() => router.push(routePath("/console/assets/models"))}>
                    查看模型资产
                  </Button>
                </Space>
              </Space>
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
            <Descriptions.Item label="模板接口">
              <Text copyable>/api/v1/plugin/templates</Text>
            </Descriptions.Item>
            <Descriptions.Item label="模型回传接口">
              <Text copyable>/api/v1/plugin/model-assets/upload</Text>
            </Descriptions.Item>
          </Descriptions>
          <Paragraph className="muted" style={{ marginTop: 14, marginBottom: 0 }}>
            API Key 明文只会在创建或轮换时显示一次。生产使用时建议为插件单独创建 Key，并定期轮换。
          </Paragraph>
        </Card>
      </Space>
    </ConsoleShell>
  );
}
