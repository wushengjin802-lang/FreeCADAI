"use client";

import { DatabaseOutlined, DeleteOutlined, EditOutlined, PlusOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ModelAsset } from "@/lib/types";

const { Paragraph, Text, Title } = Typography;

type ModelFormValues = {
  name: string;
  project_id?: string;
  file_name?: string;
  file_type?: string;
  storage_uri?: string;
  preview_uri?: string;
  checksum?: string;
  size_bytes?: number;
  status: string;
  script_asset_id?: number | null;
  task_id?: number | null;
};

function statusColor(status: string) {
  if (status === "active") return "green";
  if (status === "archived") return "default";
  return "blue";
}

function bytesText(value: number) {
  if (!value) return "-";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

export default function ConsoleModelAssetsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [editing, setEditing] = useState<ModelAsset | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ModelFormValues>();

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

  const assetsQuery = useQuery({
    queryKey: ["console-model-assets", token, workspace?.id, q, status],
    queryFn: () => consoleApi.modelAssets(token, { workspace_id: workspace?.id as number, q, status }),
    enabled: Boolean(token && workspace?.id)
  });

  const createMutation = useMutation({
    mutationFn: (values: ModelFormValues) =>
      consoleApi.createModelAsset(token, {
        workspace_id: workspace?.id as number,
        script_asset_id: values.script_asset_id || null,
        task_id: values.task_id || null,
        project_id: values.project_id || "",
        name: values.name,
        file_name: values.file_name || "",
        file_type: values.file_type || "",
        storage_uri: values.storage_uri || "",
        preview_uri: values.preview_uri || "",
        checksum: values.checksum || "",
        size_bytes: values.size_bytes || 0,
        status: values.status || "active",
        metadata: {}
      }),
    onSuccess: () => {
      message.success("模型资产已创建");
      setOpen(false);
      form.resetFields();
      queryClient.invalidateQueries({ queryKey: ["console-model-assets"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: (values: ModelFormValues) =>
      consoleApi.updateModelAsset(token, editing?.id as number, {
        script_asset_id: values.script_asset_id || null,
        task_id: values.task_id || null,
        project_id: values.project_id || "",
        name: values.name,
        file_name: values.file_name || "",
        file_type: values.file_type || "",
        storage_uri: values.storage_uri || "",
        preview_uri: values.preview_uri || "",
        checksum: values.checksum || "",
        size_bytes: values.size_bytes || 0,
        status: values.status || "active"
      }),
    onSuccess: () => {
      message.success("模型资产已更新");
      setOpen(false);
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["console-model-assets"] });
    }
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => consoleApi.deleteModelAsset(token, id),
    onSuccess: () => {
      message.success("模型资产已删除");
      queryClient.invalidateQueries({ queryKey: ["console-model-assets"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  function openCreate() {
    setEditing(null);
    form.setFieldsValue({ name: "", project_id: "", file_name: "", file_type: "FCStd", storage_uri: "", preview_uri: "", checksum: "", size_bytes: 0, status: "active" });
    setOpen(true);
  }

  function openEdit(row: ModelAsset) {
    setEditing(row);
    form.setFieldsValue({
      name: row.name,
      project_id: row.project_id,
      file_name: row.file_name,
      file_type: row.file_type,
      storage_uri: row.storage_uri,
      preview_uri: row.preview_uri,
      checksum: row.checksum,
      size_bytes: row.size_bytes,
      status: row.status,
      script_asset_id: row.script_asset_id,
      task_id: row.task_id
    });
    setOpen(true);
  }

  const columns: ColumnsType<ModelAsset> = [
    {
      title: "模型资产",
      dataIndex: "name",
      render: (value, row) => (
        <Space direction="vertical" size={0}>
          <Text strong>{value}</Text>
          <Text className="muted">{row.file_name || "未登记文件"} · {row.file_type || "unknown"}</Text>
        </Space>
      )
    },
    { title: "项目", dataIndex: "project_id", width: 150, render: (value) => value || "-" },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <Tag color={statusColor(value)}>{value}</Tag> },
    { title: "大小", dataIndex: "size_bytes", width: 110, render: bytesText },
    { title: "存储 URI", dataIndex: "storage_uri", render: (value) => <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>{value || "-"}</Paragraph> },
    { title: "更新时间", dataIndex: "updated_at", width: 180 },
    {
      title: "操作",
      width: 190,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} disabled={!canManage} onClick={() => openEdit(row)}>
            编辑
          </Button>
          <Button size="small" danger icon={<DeleteOutlined />} disabled={!canManage} onClick={() => deleteMutation.mutate(row.id)}>
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
            <Title level={3}>
              <DatabaseOutlined /> 模型资产
            </Title>
            <Text className="muted">维护企业工作区的 FreeCAD 模型文件、预览地址和关联任务。</Text>
          </div>
          <Button type="primary" icon={<PlusOutlined />} disabled={!canManage} onClick={openCreate}>
            新建模型资产
          </Button>
        </section>

        {!canManage ? <Alert type="info" showIcon message="当前角色可以查看模型资产，新增、编辑和删除需要 Owner/Admin 权限。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {assetsQuery.error ? <Alert type="error" showIcon message={(assetsQuery.error as Error).message} /> : null}
        {createMutation.error ? <Alert type="error" showIcon message={(createMutation.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {deleteMutation.error ? <Alert type="error" showIcon message={(deleteMutation.error as Error).message} /> : null}

        <Card className="console-card">
          <Space wrap style={{ marginBottom: 16 }}>
            <Input.Search allowClear placeholder="搜索名称、文件或项目" onSearch={setQ} style={{ width: 300 }} />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 150 }}
              value={status || undefined}
              onChange={(value) => setStatus(value || "")}
              options={["active", "archived"].map((item) => ({ value: item, label: item }))}
            />
          </Space>
          <Table
            rowKey="id"
            className="enterprise-model-asset-table"
            columns={columns}
            dataSource={assetsQuery.data || []}
            loading={assetsQuery.isLoading}
            pagination={false}
            scroll={{ x: 1240 }}
          />
        </Card>
      </Space>

      <Modal title={editing ? "编辑模型资产" : "新建模型资产"} open={open} onCancel={() => setOpen(false)} footer={null} destroyOnHidden>
        <Form form={form} layout="vertical" onFinish={(values) => (editing ? updateMutation.mutate(values) : createMutation.mutate(values))}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="file_name" label="文件名">
            <Input maxLength={255} />
          </Form.Item>
          <Form.Item name="file_type" label="文件类型">
            <Input maxLength={64} placeholder="FCStd / STEP / STL" />
          </Form.Item>
          <Form.Item name="storage_uri" label="存储 URI">
            <Input maxLength={512} />
          </Form.Item>
          <Form.Item name="preview_uri" label="预览 URI">
            <Input maxLength={512} />
          </Form.Item>
          <Form.Item name="checksum" label="Checksum">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="size_bytes" label="文件大小">
            <InputNumber min={0} className="full-width" addonAfter="bytes" />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={["active", "archived"].map((item) => ({ value: item, label: item }))} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending || updateMutation.isPending} block>
            保存
          </Button>
        </Form>
      </Modal>
    </ConsoleShell>
  );
}
