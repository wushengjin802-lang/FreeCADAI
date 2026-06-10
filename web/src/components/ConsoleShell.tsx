"use client";

import {
  AppstoreOutlined,
  ApiOutlined,
  KeyOutlined,
  LogoutOutlined,
  SettingOutlined,
  TeamOutlined,
  UserOutlined
} from "@ant-design/icons";
import { Button, Layout, Menu, Select, Space, Tag, Typography } from "antd";
import { usePathname, useRouter } from "next/navigation";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Content, Sider } = Layout;
const { Text, Title } = Typography;

export function ConsoleShell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const token = useConsoleStore((state) => state.token);
  const user = useConsoleStore((state) => state.user);
  const workspaces = useConsoleStore((state) => state.workspaces);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setWorkspaceId = useConsoleStore((state) => state.setWorkspaceId);
  const logout = useConsoleStore((state) => state.logout);
  const selectedWorkspace = workspaces.find((workspace) => workspace.id === workspaceId);

  async function handleLogout() {
    if (token) {
      try {
        await consoleApi.logout(token);
      } catch {
        // Local logout should still complete if the session was already invalid.
      }
    }
    logout();
    router.replace(routePath("/console/login"));
  }

  const selectedKey = pathname?.includes("/console/members")
    ? "members"
    : pathname?.includes("/console/plugin")
      ? "plugin"
      : pathname?.includes("/console/api-keys")
        ? "apiKeys"
        : "overview";

  return (
    <Layout className="enterprise-shell">
      <Sider width={236} className="enterprise-sider" breakpoint="lg" collapsedWidth={0}>
        <div className="enterprise-brand">
          <strong>FreeCADAI</strong>
          <span>企业工作台</span>
        </div>
        <Menu
          className="enterprise-menu"
          theme="dark"
          mode="inline"
          selectedKeys={[selectedKey]}
          items={[
            { key: "overview", icon: <AppstoreOutlined />, label: "工作区概览", onClick: () => router.push(routePath("/console")) },
            { key: "plugin", icon: <ApiOutlined />, label: "插件接入", onClick: () => router.push(routePath("/console/plugin")) },
            { key: "apiKeys", icon: <KeyOutlined />, label: "API Key", onClick: () => router.push(routePath("/console/api-keys")) },
            { key: "members", icon: <TeamOutlined />, label: "成员管理", onClick: () => router.push(routePath("/console/members")) },
            { key: "settings", icon: <SettingOutlined />, label: "工作区设置", disabled: true }
          ]}
        />
      </Sider>
      <Layout>
        <header className="enterprise-header">
          <Space direction="vertical" size={2}>
            <Title level={4} style={{ margin: 0 }}>
              {selectedWorkspace?.name || "企业工作区"}
            </Title>
            <Space size={8} wrap>
              <Text className="muted">{user?.display_name || user?.email || "未登录用户"}</Text>
              {selectedWorkspace ? <Tag color="green">{selectedWorkspace.role}</Tag> : null}
            </Space>
          </Space>
          <Space wrap>
            <Select
              style={{ minWidth: 220 }}
              value={workspaceId ?? undefined}
              placeholder="选择工作区"
              onChange={(value) => setWorkspaceId(value)}
              options={workspaces.map((workspace) => ({ value: workspace.id, label: workspace.name }))}
            />
            <Button icon={<UserOutlined />} onClick={() => router.push(routePath("/console"))}>
              我的工作台
            </Button>
            <Button icon={<LogoutOutlined />} onClick={handleLogout}>
              退出
            </Button>
          </Space>
        </header>
        <Content className="enterprise-content">{children}</Content>
      </Layout>
    </Layout>
  );
}
