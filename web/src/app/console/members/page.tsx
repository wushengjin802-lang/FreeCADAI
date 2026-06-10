"use client";

import { CopyOutlined, PlusOutlined, TeamOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Modal, Select, Space, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ConsoleInvite, ConsoleMember } from "@/lib/types";

const { Text, Title } = Typography;

const roleOptions = [
  { value: "admin", label: "Admin" },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" }
];

function roleColor(role: string) {
  if (role === "owner") return "green";
  if (role === "admin") return "blue";
  if (role === "viewer") return "default";
  return "gold";
}

export default function ConsoleMembersPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [latestInvite, setLatestInvite] = useState<ConsoleInvite | null>(null);
  const [form] = Form.useForm();

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
  const activeWorkspaceId = workspace?.id;
  const canManage = canManageWorkspace(workspace?.role);

  const membersQuery = useQuery({
    queryKey: ["console-members", token, activeWorkspaceId],
    queryFn: () => consoleApi.members(token, activeWorkspaceId as number),
    enabled: Boolean(token && activeWorkspaceId)
  });

  const inviteMutation = useMutation({
    mutationFn: (values: { email: string; role: string }) => consoleApi.inviteMember(token, activeWorkspaceId as number, values),
    onSuccess: (invite) => {
      setLatestInvite(invite);
      message.success(invite.status === "accepted" ? "成员已加入工作区" : "邀请已创建");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["console-members"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: ({ memberId, body }: { memberId: number; body: Partial<{ role: string; status: string }> }) =>
      consoleApi.updateMember(token, activeWorkspaceId as number, memberId, body),
    onSuccess: () => {
      message.success("成员已更新");
      queryClient.invalidateQueries({ queryKey: ["console-members"] });
    }
  });

  const removeMutation = useMutation({
    mutationFn: (memberId: number) => consoleApi.removeMember(token, activeWorkspaceId as number, memberId),
    onSuccess: () => {
      message.success("成员已移除");
      queryClient.invalidateQueries({ queryKey: ["console-members"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const columns: ColumnsType<ConsoleMember> = [
    { title: "成员", dataIndex: "display_name", render: (_, row) => <Space direction="vertical" size={0}><Text strong>{row.display_name || row.email}</Text><Text className="muted">{row.email}</Text></Space> },
    { title: "角色", dataIndex: "role", width: 140, render: (role) => <Tag color={roleColor(role)}>{role}</Tag> },
    { title: "状态", dataIndex: "status", width: 120, render: (status) => <Tag color={status === "active" ? "green" : "red"}>{status}</Tag> },
    { title: "加入时间", dataIndex: "joined_at", width: 190, render: (value) => value || "-" },
    {
      title: "操作",
      width: 280,
      align: "right",
      render: (_, row) => (
        <Space>
          <Select
            size="small"
            disabled={!canManage || row.role === "owner"}
            value={row.role}
            style={{ width: 110 }}
            options={roleOptions}
            onChange={(role) => updateMutation.mutate({ memberId: row.id, body: { role } })}
          />
          <Button
            size="small"
            danger
            disabled={!canManage || row.role === "owner"}
            loading={removeMutation.isPending}
            onClick={() => removeMutation.mutate(row.id)}
          >
            移除
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
              <TeamOutlined /> 成员管理
            </Title>
            <Text className="muted">Owner/Admin 可以邀请成员、调整角色和移除成员。</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={() => setInviteOpen(true)}>
            邀请成员
          </Button>
        </section>

        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {membersQuery.error ? <Alert type="error" showIcon message={(membersQuery.error as Error).message} /> : null}
        {inviteMutation.error ? <Alert type="error" showIcon message={(inviteMutation.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {removeMutation.error ? <Alert type="error" showIcon message={(removeMutation.error as Error).message} /> : null}

        <Card className="console-card">
          {membersQuery.isLoading ? <Spin /> : null}
          <Table
            rowKey="id"
            className="enterprise-members-table"
            columns={columns}
            dataSource={membersQuery.data || []}
            pagination={false}
            scroll={{ x: 900 }}
          />
        </Card>
      </Space>

      <Modal title="邀请成员" open={inviteOpen} onCancel={() => setInviteOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(values) => inviteMutation.mutate(values)} initialValues={{ role: "member" }}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input placeholder="member@company.com" />
          </Form.Item>
          <Form.Item name="role" label="角色" rules={[{ required: true, message: "请选择角色" }]}>
            <Select options={roleOptions} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={inviteMutation.isPending} block>
            发送邀请
          </Button>
        </Form>
        {latestInvite?.invite_token ? (
          <Alert
            style={{ marginTop: 16 }}
            type="success"
            showIcon
            message="邀请链接已生成"
            description={
              <Space direction="vertical" className="full-width">
                <Text copyable={{ text: `${window.location.origin}${routePath(`/console/invites/${latestInvite.invite_token}`)}` }}>
                  {routePath(`/console/invites/${latestInvite.invite_token}`)}
                </Text>
                <Button
                  icon={<CopyOutlined />}
                  onClick={() => navigator.clipboard.writeText(`${window.location.origin}${routePath(`/console/invites/${latestInvite.invite_token}`)}`)}
                >
                  复制完整链接
                </Button>
              </Space>
            }
          />
        ) : null}
      </Modal>
    </ConsoleShell>
  );
}
