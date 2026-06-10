"use client";

import { KeyOutlined, PlusOutlined, ReloadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Spin, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ApiKey, ConsoleApiKeyCreateResponse } from "@/lib/types";

const { Paragraph, Text, Title } = Typography;

function statusColor(status: string) {
  if (status === "active") return "green";
  if (status === "disabled" || status === "expired" || status === "revoked") return "red";
  return "default";
}

export default function ConsoleApiKeysPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [createOpen, setCreateOpen] = useState(false);
  const [generated, setGenerated] = useState<ConsoleApiKeyCreateResponse | null>(null);
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
  const canManage = canManageWorkspace(workspace?.role);

  const keysQuery = useQuery({
    queryKey: ["console-api-keys", token, workspace?.id],
    queryFn: () => consoleApi.apiKeys(token, workspace?.id as number),
    enabled: Boolean(token && workspace?.id)
  });

  const createMutation = useMutation({
    mutationFn: (values: { name: string; expires_in_days?: number | null }) =>
      consoleApi.createApiKey(token, { workspace_id: workspace?.id as number, name: values.name, expires_in_days: values.expires_in_days || null, scopes: ["plugin"] }),
    onSuccess: (data) => {
      setGenerated(data);
      message.success("API Key 已创建");
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["console-api-keys"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const enableMutation = useMutation({
    mutationFn: (id: number) => consoleApi.enableApiKey(token, id),
    onSuccess: () => {
      message.success("API Key 已启用");
      queryClient.invalidateQueries({ queryKey: ["console-api-keys"] });
    }
  });

  const disableMutation = useMutation({
    mutationFn: (id: number) => consoleApi.disableApiKey(token, id),
    onSuccess: () => {
      message.success("API Key 已禁用");
      queryClient.invalidateQueries({ queryKey: ["console-api-keys"] });
    }
  });

  const rotateMutation = useMutation({
    mutationFn: (id: number) => consoleApi.rotateApiKey(token, id),
    onSuccess: (data) => {
      setGenerated(data);
      message.success("API Key 已轮换");
      queryClient.invalidateQueries({ queryKey: ["console-api-keys"] });
    }
  });

  const columns: ColumnsType<ApiKey> = [
    { title: "名称", dataIndex: "name", render: (value, row) => <Space direction="vertical" size={0}><Text strong>{value}</Text><Text className="muted">{row.scopes?.join(", ") || "plugin"}</Text></Space> },
    { title: "前缀", dataIndex: "prefix", width: 160, render: (value) => <Text code>{value}</Text> },
    { title: "状态", dataIndex: "status", width: 120, render: (status) => <Tag color={statusColor(status)}>{status}</Tag> },
    { title: "过期时间", dataIndex: "expires_at", width: 190, render: (value) => value || "长期" },
    { title: "最后使用", dataIndex: "last_used_at", width: 190, render: (value) => value || "-" },
    {
      title: "操作",
      width: 270,
      align: "right",
      render: (_, row) => (
        <Space>
          {row.status === "active" ? (
            <Button size="small" disabled={!canManage} onClick={() => disableMutation.mutate(row.id)}>
              禁用
            </Button>
          ) : (
            <Button size="small" disabled={!canManage} onClick={() => enableMutation.mutate(row.id)}>
              启用
            </Button>
          )}
          <Button size="small" icon={<ReloadOutlined />} disabled={!canManage} onClick={() => rotateMutation.mutate(row.id)}>
            轮换
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
              <KeyOutlined /> API Key
            </Title>
            <Text className="muted">用于 FreeCAD 插件连接企业工作区。明文只在创建或轮换时显示一次。</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={() => setCreateOpen(true)}>
            创建 Key
          </Button>
        </section>

        {!canManage ? <Alert type="info" showIcon message="当前角色只能查看 API Key，创建和轮换需要 Owner/Admin 权限。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {keysQuery.error ? <Alert type="error" showIcon message={(keysQuery.error as Error).message} /> : null}
        {createMutation.error ? <Alert type="error" showIcon message={(createMutation.error as Error).message} /> : null}
        {enableMutation.error ? <Alert type="error" showIcon message={(enableMutation.error as Error).message} /> : null}
        {disableMutation.error ? <Alert type="error" showIcon message={(disableMutation.error as Error).message} /> : null}
        {rotateMutation.error ? <Alert type="error" showIcon message={(rotateMutation.error as Error).message} /> : null}

        {generated ? (
          <Alert
            type="success"
            showIcon
            message="请立即保存 API Key"
            description={
              <Space direction="vertical" className="full-width">
                <Text copyable={{ text: generated.api_key }} code>
                  {generated.api_key}
                </Text>
                <Paragraph className="muted" style={{ margin: 0 }}>
                  关闭此提示后将无法再次查看明文，只能轮换生成新的 Key。
                </Paragraph>
              </Space>
            }
            closable
            onClose={() => setGenerated(null)}
          />
        ) : null}

        <Card className="console-card">
          {keysQuery.isLoading ? <Spin /> : null}
          <Table
            rowKey="id"
            className="enterprise-api-key-table"
            columns={columns}
            dataSource={keysQuery.data || []}
            pagination={false}
            scroll={{ x: 980 }}
          />
        </Card>
      </Space>

      <Modal title="创建插件 API Key" open={createOpen} onCancel={() => setCreateOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" initialValues={{ name: "FreeCAD Plugin Key" }} onFinish={(values) => createMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入 Key 名称" }]}>
            <Input placeholder="设计部 FreeCAD 插件" />
          </Form.Item>
          <Form.Item name="expires_in_days" label="有效期">
            <InputNumber min={1} max={3650} className="full-width" placeholder="留空表示长期有效" addonAfter="天" />
          </Form.Item>
          <Form.Item label="权限范围">
            <Select value="plugin" disabled options={[{ value: "plugin", label: "plugin" }]} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending} block>
            创建
          </Button>
        </Form>
      </Modal>
    </ConsoleShell>
  );
}
