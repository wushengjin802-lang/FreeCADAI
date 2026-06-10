"use client";

import { LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Space, Typography } from "antd";
import { useParams, useRouter } from "next/navigation";
import { consoleAcceptInvite } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Text, Title } = Typography;

export default function ConsoleInvitePage() {
  const params = useParams<{ token: string }>();
  const router = useRouter();
  const { message } = AntApp.useApp();
  const hydrateAuth = useConsoleStore((state) => state.hydrateAuth);
  const mutation = useMutation({
    mutationFn: (values: { email: string; password: string; display_name: string }) =>
      consoleAcceptInvite(params.token, values),
    onSuccess: (data) => {
      hydrateAuth(data.token, data.user, data.workspaces);
      message.success("已加入工作区");
      router.replace(routePath("/console"));
    }
  });

  return (
    <main className="enterprise-auth-page">
      <Card className="enterprise-auth-card" bordered>
        <Space direction="vertical" size={6} className="full-width">
          <Title level={2} style={{ margin: 0 }}>
            接受企业邀请
          </Title>
          <Text className="muted">请使用被邀请的邮箱完成加入。</Text>
        </Space>
        {mutation.error ? <Alert style={{ marginTop: 18 }} type="error" message={(mutation.error as Error).message} showIcon /> : null}
        <Form layout="vertical" style={{ marginTop: 22 }} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="display_name" label="姓名" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input prefix={<UserOutlined />} placeholder="张工" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input prefix={<MailOutlined />} placeholder="member@company.com" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 8, message: "密码至少 8 位" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending} block>
            接受邀请
          </Button>
        </Form>
      </Card>
    </main>
  );
}
