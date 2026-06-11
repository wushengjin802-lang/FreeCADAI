"use client";

import { CopyOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, PlusOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Modal, Space, Switch, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi, downloadJson } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { Template } from "@/lib/types";

const { Paragraph, Text, Title } = Typography;

type TemplateFormValues = {
  name: string;
  category: string;
  prompt: string;
  enabled: boolean;
};

export default function ConsoleTemplatesPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [q, setQ] = useState("");
  const [includeDisabled, setIncludeDisabled] = useState(true);
  const [editing, setEditing] = useState<Template | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<TemplateFormValues>();

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

  const templatesQuery = useQuery({
    queryKey: ["console-template-center", token, workspace?.id, includeDisabled, q],
    queryFn: () => consoleApi.templateCenter(token, { workspace_id: workspace?.id as number, include_disabled: includeDisabled, q }),
    enabled: Boolean(token && workspace?.id)
  });

  const createMutation = useMutation({
    mutationFn: (values: TemplateFormValues) =>
      consoleApi.createTemplate(token, { workspace_id: workspace?.id as number, ...values }),
    onSuccess: () => {
      message.success("模板已创建");
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["console-template-center"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: (values: TemplateFormValues) => consoleApi.updateTemplate(token, editing?.id as number, values),
    onSuccess: () => {
      message.success("模板已更新");
      setOpen(false);
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["console-template-center"] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => consoleApi.deleteTemplate(token, id),
    onSuccess: () => {
      message.success("模板已删除");
      queryClient.invalidateQueries({ queryKey: ["console-template-center"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const exportMutation = useMutation({
    mutationFn: () => consoleApi.exportTemplates(token, workspace?.id as number),
    onSuccess: (data) => downloadJson(`freecadai_workspace_${workspace?.id}_templates.json`, data)
  });

  function openCreate() {
    setEditing(null);
    form.setFieldsValue({ name: "", category: "企业模板", prompt: "", enabled: true });
    setOpen(true);
  }

  function openEdit(row: Template) {
    setEditing(row);
    form.setFieldsValue({ name: row.name, category: row.category, prompt: row.prompt, enabled: row.enabled });
    setOpen(true);
  }

  const columns: ColumnsType<Template> = [
    {
      title: "模板",
      dataIndex: "name",
      render: (value, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text className="muted">{row.category}</Text>
        </Space>
      )
    },
    { title: "来源", dataIndex: "workspace_id", width: 120, render: (value) => (value ? <Tag color="blue">企业</Tag> : <Tag>系统</Tag>) },
    { title: "状态", dataIndex: "enabled", width: 120, render: (value) => <Tag color={value ? "green" : "default"}>{value ? "启用" : "停用"}</Tag> },
    { title: "Prompt", dataIndex: "prompt", render: (value) => <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>{value}</Paragraph> },
    {
      title: "操作",
      width: 270,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(row.prompt).then(() => message.success("Prompt 已复制"))}>
            复制
          </Button>
          <Button size="small" icon={<EditOutlined />} disabled={!canManage || !row.workspace_id} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={!canManage || !row.workspace_id} onClick={() => deleteMutation.mutate(row.id)}>
            删除
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
            <Title level={3}>模板中心</Title>
            <Text className="muted">系统模板和企业模板统一展示，企业模板仅在当前工作区内可见。</Text>
          </div>
          <Space wrap>
            <Button icon={<DownloadOutlined />} onClick={() => exportMutation.mutate()} disabled={!workspace?.id}>
              导出
            </Button>
            <Button icon={<UploadOutlined />} disabled>
              导入 JSON
            </Button>
            <Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={openCreate}>
              新建模板
            </Button>
          </Space>
        </section>

        {!canManage ? <Alert type="info" showIcon message="当前角色可以查看和复用模板，新增、编辑、删除需要 Owner/Admin 权限。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {templatesQuery.error ? <Alert type="error" showIcon message={(templatesQuery.error as Error).message} /> : null}
        {createMutation.error ? <Alert type="error" showIcon message={(createMutation.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {deleteMutation.error ? <Alert type="error" showIcon message={(deleteMutation.error as Error).message} /> : null}

        <Card className="console-card">
          <Space wrap style={{ marginBottom: 16 }}>
            <Input.Search allowClear placeholder="搜索模板、分类或 Prompt" onSearch={setQ} style={{ width: 300 }} />
            <Space>
              <Switch checked={includeDisabled} onChange={setIncludeDisabled} />
              <Text>显示停用模板</Text>
            </Space>
          </Space>
          <Table
            rowKey="id"
            className="enterprise-template-table"
            columns={columns}
            dataSource={templatesQuery.data || []}
            loading={templatesQuery.isLoading}
            pagination={false}
            scroll={{ x: 1080 }}
          />
        </Card>
      </Space>

      <Modal title={editing ? "编辑企业模板" : "新建企业模板"} open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(values) => (editing ? updateMutation.mutate(values) : createMutation.mutate(values))}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入模板名称" }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: "请输入分类" }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Form.Item name="prompt" label="Prompt" rules={[{ required: true, message: "请输入 Prompt" }]}>
            <Input.TextArea rows={8} />
          </Form.Item>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending || updateMutation.isPending} block>
            保存
          </Button>
        </Form>
      </Modal>
    </ConsoleShell>
  );
}
