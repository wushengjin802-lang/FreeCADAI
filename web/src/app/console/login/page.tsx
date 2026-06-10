"use client";

import { LockOutlined, MailOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Space, Typography } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { consoleLogin } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Text, Title } = Typography;

export default function ConsoleLoginPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const hydrateAuth = useConsoleStore((state) => state.hydrateAuth);
  const mutation = useMutation({
    mutationFn: (values: { email: string; password: string }) => consoleLogin(values.email, values.password),
    onSuccess: (data) => {
      hydrateAuth(data.token, data.user, data.workspaces);
      message.success("登录成功");
      router.replace(routePath("/console"));
    }
  });

  return (
    <main className="enterprise-auth-page">
      <Card className="enterprise-auth-card" bordered>
        <Space direction="vertical" size={6} className="full-width">
          <Title level={2} style={{ margin: 0 }}>
            企业工作台
          </Title>
          <Text className="muted">登录后管理团队成员、工作区和 FreeCADAI 企业资产。</Text>
        </Space>
        {mutation.error ? <Alert style={{ marginTop: 18 }} type="error" message={(mutation.error as Error).message} showIcon /> : null}
        <Form layout="vertical" style={{ marginTop: 22 }} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input prefix={<MailOutlined />} placeholder="you@company.com" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending} block>
            登录
          </Button>
        </Form>
        <div className="enterprise-auth-footer">
          <Text className="muted">还没有企业账号？</Text>
          <Link href={routePath("/console/register")}>创建工作区</Link>
        </div>
      </Card>
    </main>
  );
}
