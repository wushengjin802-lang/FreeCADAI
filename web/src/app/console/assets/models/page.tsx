"use client";

import { DatabaseOutlined, DeleteOutlined, DownloadOutlined, EditOutlined, EyeOutlined, PlusOutlined, UploadOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Drawer, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography, Upload } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { StlPreviewer } from "@/components/StlPreviewer";
import { consoleApi, downloadBlob } from "@/lib/api";
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
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [previewAsset, setPreviewAsset] = useState<ModelAsset | null>(null);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<ModelFormValues>();
  const [uploadForm] = Form.useForm<ModelFormValues>();

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
  const canUpload = workspace?.role === "owner" || workspace?.role === "admin" || workspace?.role === "member";

  const assetsQuery = useQuery({
    queryKey: ["console-model-assets", token, workspace?.id, q, status],
    queryFn: () => consoleApi.modelAssets(token, { workspace_id: workspace?.id as number, q, status }),
    enabled: Boolean(token && workspace?.id)
  });

  const scriptsQuery = useQuery({
    queryKey: ["console-script-assets", token, workspace?.id, "model-link"],
    queryFn: () => consoleApi.scriptAssets(token, { workspace_id: workspace?.id as number, status: "active" }),
    enabled: Boolean(token && workspace?.id)
  });

  const previewQuery = useQuery({
    queryKey: ["console-model-preview", token, previewAsset?.id],
    queryFn: () => consoleApi.previewModelAsset(token, previewAsset?.id as number),
    enabled: Boolean(token && previewAsset?.id)
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

  const uploadMutation = useMutation({
    mutationFn: async (values: ModelFormValues) => {
      if (!uploadFile) throw new Error("请选择模型文件");
      const prepared = await consoleApi.prepareModelUpload(token, {
        workspace_id: workspace?.id as number,
        file_name: uploadFile.name,
        size_bytes: uploadFile.size
      });
      const formData = new FormData();
      formData.set("workspace_id", String(workspace?.id));
      formData.set("upload_token", prepared.upload_token);
      formData.set("name", values.name || uploadFile.name);
      formData.set("project_id", values.project_id || "");
      if (values.script_asset_id) formData.set("script_asset_id", String(values.script_asset_id));
      if (values.task_id) formData.set("task_id", String(values.task_id));
      formData.set("file", uploadFile);
      return consoleApi.uploadModelAsset(token, formData);
    },
    onSuccess: () => {
      message.success("模型文件已上传");
      setUploadOpen(false);
      setUploadFile(null);
      uploadForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ["console-model-assets"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const downloadMutation = useMutation({
    mutationFn: (row: ModelAsset) => consoleApi.downloadModelAsset(token, row.id).then((blob) => downloadBlob(row.file_name || `${row.name}.model`, blob)),
    onSuccess: () => message.success("模型文件已开始下载")
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

  function openUpload() {
    setUploadFile(null);
    uploadForm.setFieldsValue({ name: "", project_id: "", script_asset_id: null, task_id: null, status: "active" });
    setUploadOpen(true);
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
      width: 330,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<DownloadOutlined />} disabled={!row.storage_uri} onClick={() => downloadMutation.mutate(row)}>
            下载
          </Button>
          <Button size="small" icon={<EyeOutlined />} disabled={!row.preview_uri || row.file_type.toLowerCase() !== "stl"} onClick={() => setPreviewAsset(row)}>
            预览
          </Button>
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
            <Text className="muted">上传 FCStd/STEP/STL 等模型文件，下载归档，并在 Web 端预览 STL。</Text>
          </div>
          <Space wrap>
            <Button icon={<PlusOutlined />} disabled={!canManage} onClick={openCreate}>
              登记元数据
            </Button>
            <Button type="primary" icon={<UploadOutlined />} disabled={!canUpload} onClick={openUpload}>
              上传模型
            </Button>
          </Space>
        </section>

        {!canUpload ? <Alert type="info" showIcon message="当前角色可以查看和下载模型资产，上传需要 Member 及以上权限。" /> : null}
        {workspace?.role === "member" ? <Alert type="info" showIcon message="Member 可以上传模型文件；编辑和删除资产元数据需要 Owner/Admin 权限。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {assetsQuery.error ? <Alert type="error" showIcon message={(assetsQuery.error as Error).message} /> : null}
        {createMutation.error ? <Alert type="error" showIcon message={(createMutation.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {deleteMutation.error ? <Alert type="error" showIcon message={(deleteMutation.error as Error).message} /> : null}
        {uploadMutation.error ? <Alert type="error" showIcon message={(uploadMutation.error as Error).message} /> : null}
        {downloadMutation.error ? <Alert type="error" showIcon message={(downloadMutation.error as Error).message} /> : null}

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
            scroll={{ x: 1380 }}
          />
        </Card>
      </Space>

      <Modal title="上传模型文件" open={uploadOpen} onCancel={() => setUploadOpen(false)} footer={null} destroyOnHidden>
        <Form form={uploadForm} layout="vertical" onFinish={(values) => uploadMutation.mutate(values)}>
          <Form.Item label="文件" required>
            <Upload
              maxCount={1}
              beforeUpload={(file) => {
                setUploadFile(file);
                if (!uploadForm.getFieldValue("name")) uploadForm.setFieldValue("name", file.name);
                return false;
              }}
              onRemove={() => setUploadFile(null)}
            >
              <Button icon={<UploadOutlined />}>选择 FCStd / STEP / STL / OBJ</Button>
            </Upload>
            <Text className="muted">STL 文件上传后可直接 Web 预览，其他格式支持归档和下载。</Text>
          </Form.Item>
          <Form.Item name="name" label="资产名称" rules={[{ required: true, message: "请输入资产名称" }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="project_id" label="项目 ID">
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="script_asset_id" label="关联脚本资产">
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              options={(scriptsQuery.data || []).map((item) => ({ value: item.id, label: `#${item.id} ${item.name}` }))}
            />
          </Form.Item>
          <Form.Item name="task_id" label="关联任务 ID">
            <InputNumber min={1} className="full-width" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={uploadMutation.isPending} block>
            上传
          </Button>
        </Form>
      </Modal>

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

      <Drawer title={previewAsset?.name || "模型预览"} open={Boolean(previewAsset)} width={900} onClose={() => setPreviewAsset(null)} destroyOnHidden>
        <Space direction="vertical" size={14} className="full-width">
          {previewAsset ? (
            <Space wrap>
              <Tag color="blue">{previewAsset.file_type}</Tag>
              <Text>{previewAsset.file_name}</Text>
              <Text className="muted">{bytesText(previewAsset.size_bytes)}</Text>
            </Space>
          ) : null}
          {previewQuery.error ? <Alert type="error" showIcon message={(previewQuery.error as Error).message} /> : null}
          <StlPreviewer blob={previewQuery.data || null} />
        </Space>
      </Drawer>
    </ConsoleShell>
  );
}
