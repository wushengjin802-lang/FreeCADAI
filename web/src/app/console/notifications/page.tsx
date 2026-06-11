"use client";

import { BellOutlined, CheckOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, List, Space, Switch, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { formatShanghaiTime } from "@/lib/format";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";
import type { ConsoleNotification } from "@/lib/types";

const { Text, Title } = Typography;

function color(level: string) {
  if (level === "warning") return "gold";
  if (level === "error") return "red";
  if (level === "success") return "green";
  return "blue";
}

export default function ConsoleNotificationsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [unreadOnly, setUnreadOnly] = useState(false);

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
  const notifications = useQuery({
    queryKey: ["console-notifications", token, workspace?.id, unreadOnly],
    queryFn: () => consoleApi.notifications(token, workspace?.id as number, unreadOnly),
    enabled: Boolean(token && workspace?.id)
  });

  const readOne = useMutation({
    mutationFn: (id: number) => consoleApi.readNotification(token, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["console-notifications"] })
  });
  const readAll = useMutation({
    mutationFn: () => consoleApi.readAllNotifications(token, workspace?.id as number),
    onSuccess: (result) => {
      message.success(`已标记 ${result.count} 条通知`);
      queryClient.invalidateQueries({ queryKey: ["console-notifications"] });
    }
  });

  const unreadCount = (notifications.data || []).filter((item) => item.status === "unread").length;

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}><BellOutlined /> 通知中心</Title>
            <Text className="muted">接收额度、插件接入和企业治理相关提醒。</Text>
          </div>
          <Space wrap>
            <Tag color={unreadCount ? "gold" : "green"}>{unreadCount} 未读</Tag>
            <Space><Switch checked={unreadOnly} onChange={setUnreadOnly} /><Text>只看未读</Text></Space>
            <Button icon={<CheckOutlined />} onClick={() => readAll.mutate()} loading={readAll.isPending}>全部已读</Button>
          </Space>
        </section>

        {meQuery.error || notifications.error ? <Alert type="error" showIcon message={((meQuery.error || notifications.error) as Error).message} /> : null}
        <Card className="console-card">
          <List
            loading={notifications.isLoading}
            dataSource={notifications.data || []}
            locale={{ emptyText: "暂无通知" }}
            renderItem={(item: ConsoleNotification) => (
              <List.Item
                actions={[
                  <Button key="read" size="small" disabled={item.status === "read"} onClick={() => readOne.mutate(item.id)}>
                    标记已读
                  </Button>
                ]}
              >
                <List.Item.Meta
                  title={<Space><Tag color={color(item.level)}>{item.level}</Tag><Text strong={item.status === "unread"}>{item.title}</Text><Tag>{item.status === "unread" ? "未读" : "已读"}</Tag></Space>}
                  description={<Space direction="vertical" size={2}><Text>{item.body}</Text><Text className="muted">{formatShanghaiTime(item.created_at)}</Text></Space>}
                />
              </List.Item>
            )}
          />
        </Card>
      </Space>
    </ConsoleShell>
  );
}
