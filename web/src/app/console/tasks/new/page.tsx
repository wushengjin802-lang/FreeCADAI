"use client";

import { ArrowLeftOutlined, RocketOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Select, Space, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Text, Title } = Typography;

const modelingModes = [
  { value: "3d_solid", label: "3D 实体" },
  { value: "2d_sketch", label: "2D 草图" },
  { value: "assembly", label: "装配设计" },
  { value: "drawing", label: "工程图" }
];

export default function ConsoleNewTaskPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);
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
  const canSubmit = workspace?.role === "owner" || workspace?.role === "admin" || workspace?.role === "member";

  const templatesQuery = useQuery({
    queryKey: ["console-templates", token, workspace?.id],
    queryFn: () => consoleApi.templates(token, workspace?.id as number),
    enabled: Boolean(token && workspace?.id)
  });

  const createMutation = useMutation({
    mutationFn: (values: { prompt: string; context?: string; modeling_mode: string; project_id?: string; template_id?: number | null }) =>
      consoleApi.createTask(token, { workspace_id: workspace?.id as number, ...values }),
    onSuccess: (result) => {
      message.success("任务已进入队列");
      router.replace(routePath(`/console/tasks/${result.task_id}`));
    }
  });

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}>
              <RocketOutlined /> 新建生成任务
            </Title>
            <Text className="muted">Web 端提交的任务会进入同一条 Redis 队列，由 worker 异步生成脚本。</Text>
          </div>
          <Button icon={<ArrowLeftOutlined />} onClick={() => router.push(routePath("/console/tasks"))}>
            返回任务中心
          </Button>
        </section>

        {!canSubmit ? <Alert type="info" showIcon message="当前角色不能新建任务，请联系工作区拥有者/管理员。" /> : null}
        {meQuery.error ? <Alert type="error" showIcon message={(meQuery.error as Error).message} /> : null}
        {templatesQuery.error ? <Alert type="error" showIcon message={(templatesQuery.error as Error).message} /> : null}
        {createMutation.error ? <Alert type="error" showIcon message={(createMutation.error as Error).message} /> : null}

        <Card className="console-card">
          <Form
            form={form}
            layout="vertical"
            initialValues={{ modeling_mode: "3d_solid" }}
            onFinish={(values) => createMutation.mutate({ ...values, template_id: values.template_id || null })}
          >
            <Form.Item name="prompt" label="建模需求" rules={[{ required: true, message: "请输入建模需求" }]}>
              <Input.TextArea rows={6} placeholder="例如：生成一个带 4 个安装孔的法兰盘，外径 120mm，内孔 40mm，厚度 12mm。" />
            </Form.Item>
            <Space className="full-width" size={16} align="start" wrap>
              <Form.Item name="modeling_mode" label="建模模式" rules={[{ required: true, message: "请选择建模模式" }]} style={{ minWidth: 220 }}>
                <Select options={modelingModes} />
              </Form.Item>
              <Form.Item name="project_id" label="项目名称" style={{ minWidth: 260 }}>
                <Input placeholder="可选，例如 demo-flange" />
              </Form.Item>
              <Form.Item name="template_id" label="模板" style={{ minWidth: 280 }}>
                <Select
                  allowClear
                  loading={templatesQuery.isLoading}
                  placeholder="可选"
                  options={(templatesQuery.data || []).map((item) => ({ value: item.id, label: `${item.category} / ${item.name}` }))}
                />
              </Form.Item>
            </Space>
            <Form.Item name="context" label="附加上下文">
              <Input.TextArea rows={4} placeholder="可选：尺寸约束、当前 FreeCAD 文档信息、材料、命名规则等。" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending} disabled={!canSubmit}>
              提交生成
            </Button>
          </Form>
        </Card>
      </Space>
    </ConsoleShell>
  );
}
