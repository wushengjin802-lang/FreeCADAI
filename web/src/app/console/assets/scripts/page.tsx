"use client";

import { CodeOutlined, CopyOutlined, EditOutlined, FileAddOutlined, ReloadOutlined, StarFilled, StarOutlined } from "@ant-design/icons";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Drawer, Form, Input, Modal, Select, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { ScriptAsset, ScriptVersion } from "@/lib/types";

const { Paragraph, Text, Title } = Typography;

function statusColor(status: string) {
  if (status === "active") return "green";
  if (status === "archived") return "default";
  return "blue";
}

export default function ConsoleScriptAssetsPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [favorite, setFavorite] = useState<boolean | null>(null);
  const [selected, setSelected] = useState<ScriptAsset | null>(null);
  const [editing, setEditing] = useState<ScriptAsset | null>(null);
  const [reuseAsset, setReuseAsset] = useState<ScriptAsset | null>(null);
  const [editForm] = Form.useForm();
  const [reuseForm] = Form.useForm();

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
  const canWrite = workspace?.role === "owner" || workspace?.role === "admin" || workspace?.role === "member";
  const canManage = canManageWorkspace(workspace?.role);

  const assetsQuery = useQuery({
    queryKey: ["console-script-assets", token, workspace?.id, q, status, favorite],
    queryFn: () => consoleApi.scriptAssets(token, { workspace_id: workspace?.id as number, q, status, favorite }),
    enabled: Boolean(token && workspace?.id)
  });

  const versionsQuery = useQuery({
    queryKey: ["console-script-versions", token, selected?.id],
    queryFn: () => consoleApi.scriptVersions(token, selected?.id as number),
    enabled: Boolean(token && selected?.id)
  });

  const favoriteMutation = useMutation({
    mutationFn: (id: number) => consoleApi.favoriteScriptAsset(token, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["console-script-assets"] });
    }
  });

  const copyMutation = useMutation({
    mutationFn: (id: number) => consoleApi.copyScriptAsset(token, id),
    onSuccess: () => {
      message.success("脚本资产已复制");
      queryClient.invalidateQueries({ queryKey: ["console-script-assets"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  const rollbackMutation = useMutation({
    mutationFn: (args: { assetId: number; versionId: number }) => consoleApi.rollbackScriptAsset(token, args.assetId, args.versionId),
    onSuccess: () => {
      message.success("已回滚到所选版本");
      queryClient.invalidateQueries({ queryKey: ["console-script-assets"] });
      queryClient.invalidateQueries({ queryKey: ["console-script-versions"] });
    }
  });

  const updateMutation = useMutation({
    mutationFn: (values: { name: string; description?: string; status?: string; tags?: string }) =>
      consoleApi.updateScriptAsset(token, editing?.id as number, {
        name: values.name,
        description: values.description || "",
        status: values.status,
        tags: (values.tags || "").split(",").map((item) => item.trim()).filter(Boolean)
      }),
    onSuccess: () => {
      message.success("脚本资产已更新");
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ["console-script-assets"] });
    }
  });

  const reuseMutation = useMutation({
    mutationFn: (values: { name?: string; category: string }) =>
      consoleApi.reuseScriptAssetTemplate(token, reuseAsset?.id as number, { ...values, workspace_id: workspace?.id }),
    onSuccess: () => {
      message.success("已复用为企业模板");
      setReuseAsset(null);
      queryClient.invalidateQueries({ queryKey: ["console-template-center"] });
      queryClient.invalidateQueries({ queryKey: ["console-me"] });
    }
  });

  function openEdit(row: ScriptAsset) {
    setEditing(row);
    editForm.setFieldsValue({
      name: row.name,
      description: row.description,
      status: row.status,
      tags: row.tags.join(", ")
    });
  }

  function openReuse(row: ScriptAsset) {
    setReuseAsset(row);
    reuseForm.setFieldsValue({ name: row.name, category: "复用脚本" });
  }

  const versionColumns: ColumnsType<ScriptVersion> = [
    { title: "版本", dataIndex: "version", width: 90, render: (value, row) => <Tag color={row.id === selected?.current_version_id ? "green" : "blue"}>v{value}</Tag> },
    { title: "摘要", dataIndex: "summary", render: (value) => <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>{value || "-"}</Paragraph> },
    { title: "校验", dataIndex: "validation_status", width: 110 },
    { title: "创建人", dataIndex: "created_by", width: 130 },
    { title: "时间", dataIndex: "created_at", width: 180 },
    {
      title: "操作",
      width: 170,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={<CopyOutlined />} onClick={() => navigator.clipboard?.writeText(row.script).then(() => message.success("脚本已复制"))}>
            复制
          </Button>
          <Button size="small" icon={<ReloadOutlined />} disabled={!canManage || row.id === selected?.current_version_id} onClick={() => rollbackMutation.mutate({ assetId: row.asset_id, versionId: row.id })}>
            回滚
          </Button>
        </Space>
      )
    }
  ];

  const columns: ColumnsType<ScriptAsset> = [
    {
      title: "脚本资产",
      dataIndex: "name",
      render: (value, row) => (
        <Space direction="vertical" size={0}>
          <Button type="link" style={{ padding: 0, height: "auto", textAlign: "left" }} onClick={() => setSelected(row)}>
            {value}
          </Button>
          <Text className="muted">{row.project_id || "未归档项目"} · {row.modeling_mode} · v{row.current_version || "-"}</Text>
        </Space>
      )
    },
    { title: "来源", dataIndex: "source", width: 120 },
    { title: "状态", dataIndex: "status", width: 110, render: (value) => <Tag color={statusColor(value)}>{value}</Tag> },
    { title: "摘要", dataIndex: "summary", render: (value) => <Paragraph ellipsis={{ rows: 2 }} style={{ margin: 0 }}>{value || "-"}</Paragraph> },
    { title: "更新时间", dataIndex: "updated_at", width: 180 },
    {
      title: "操作",
      width: 360,
      align: "right",
      render: (_, row) => (
        <Space>
          <Button size="small" icon={row.favorite ? <StarFilled /> : <StarOutlined />} disabled={!canWrite} onClick={() => favoriteMutation.mutate(row.id)}>
            收藏
          </Button>
          <Button size="small" icon={<CopyOutlined />} disabled={!canWrite} onClick={() => copyMutation.mutate(row.id)}>
            复制
          </Button>
          <Button size="small" icon={<FileAddOutlined />} disabled={!canManage} onClick={() => openReuse(row)}>
            转模板
          </Button>
          <Button size="small" icon={<EditOutlined />} disabled={!canManage} onClick={() => openEdit(row)}>
            编辑
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
              <CodeOutlined /> 脚本资产
            </Title>
            <Text className="muted">沉淀生成结果，查看版本、回滚、复制或复用为企业模板。</Text>
          </div>
        </section>

        {workspace?.role === "viewer" ? <Alert type="info" showIcon message="Viewer 可以查看资产，复用、收藏和复制需要 Member 及以上角色。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {assetsQuery.error ? <Alert type="error" showIcon message={(assetsQuery.error as Error).message} /> : null}
        {copyMutation.error ? <Alert type="error" showIcon message={(copyMutation.error as Error).message} /> : null}
        {rollbackMutation.error ? <Alert type="error" showIcon message={(rollbackMutation.error as Error).message} /> : null}
        {updateMutation.error ? <Alert type="error" showIcon message={(updateMutation.error as Error).message} /> : null}
        {reuseMutation.error ? <Alert type="error" showIcon message={(reuseMutation.error as Error).message} /> : null}

        <Card className="console-card">
          <Space wrap style={{ marginBottom: 16 }}>
            <Input.Search allowClear placeholder="搜索名称、描述或项目" onSearch={setQ} style={{ width: 300 }} />
            <Select
              allowClear
              placeholder="状态"
              style={{ width: 150 }}
              value={status || undefined}
              onChange={(value) => setStatus(value || "")}
              options={["active", "archived"].map((item) => ({ value: item, label: item }))}
            />
            <Select
              allowClear
              placeholder="收藏"
              style={{ width: 150 }}
              value={favorite === null ? undefined : String(favorite)}
              onChange={(value) => setFavorite(value === undefined ? null : value === "true")}
              options={[
                { value: "true", label: "已收藏" },
                { value: "false", label: "未收藏" }
              ]}
            />
          </Space>
          <Table
            rowKey="id"
            className="enterprise-script-asset-table"
            columns={columns}
            dataSource={assetsQuery.data || []}
            loading={assetsQuery.isLoading}
            pagination={false}
            scroll={{ x: 1280 }}
          />
        </Card>
      </Space>

      <Drawer title={selected?.name || "脚本版本"} open={Boolean(selected)} width={900} onClose={() => setSelected(null)} destroyOnHidden>
        <Space direction="vertical" size={16} className="full-width">
          <Paragraph className="muted">{selected?.description || "暂无描述"}</Paragraph>
          <Table rowKey="id" columns={versionColumns} dataSource={versionsQuery.data || []} loading={versionsQuery.isLoading} pagination={false} scroll={{ x: 900 }} />
        </Space>
      </Drawer>

      <Modal title="编辑脚本资产" open={Boolean(editing)} onCancel={() => setEditing(null)} footer={null} destroyOnHidden>
        <Form form={editForm} layout="vertical" onFinish={(values) => updateMutation.mutate(values)}>
          <Form.Item name="name" label="名称" rules={[{ required: true, message: "请输入名称" }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={["active", "archived"].map((item) => ({ value: item, label: item }))} />
          </Form.Item>
          <Form.Item name="tags" label="标签">
            <Input placeholder="用英文逗号分隔" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={updateMutation.isPending} block>
            保存
          </Button>
        </Form>
      </Modal>

      <Modal title="复用为企业模板" open={Boolean(reuseAsset)} onCancel={() => setReuseAsset(null)} footer={null} destroyOnHidden>
        <Form form={reuseForm} layout="vertical" onFinish={(values) => reuseMutation.mutate(values)}>
          <Form.Item name="name" label="模板名称" rules={[{ required: true, message: "请输入模板名称" }]}>
            <Input maxLength={128} />
          </Form.Item>
          <Form.Item name="category" label="分类" rules={[{ required: true, message: "请输入分类" }]}>
            <Input maxLength={64} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={reuseMutation.isPending} block>
            生成模板
          </Button>
        </Form>
      </Modal>
    </ConsoleShell>
  );
}
