"use client";

import { BankOutlined, LockOutlined, MailOutlined, UserOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Form, Input, Space, Typography } from "antd";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { consoleRegister } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useConsoleStore } from "@/lib/store";

const { Text, Title } = Typography;

export default function ConsoleRegisterPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const hydrateAuth = useConsoleStore((state) => state.hydrateAuth);
  const mutation = useMutation({
    mutationFn: consoleRegister,
    onSuccess: (data) => {
      hydrateAuth(data.token, data.user, data.workspaces);
      message.success("工作区已创建");
      router.replace(routePath("/console"));
    }
  });

  return (
    <main className="enterprise-auth-page">
      <Card className="enterprise-auth-card" bordered>
        <Space direction="vertical" size={6} className="full-width">
          <Title level={2} style={{ margin: 0 }}>
            创建企业工作区
          </Title>
          <Text className="muted">阶段 16 将先建立账号、工作区和成员权限基础。</Text>
        </Space>
        {mutation.error ? <Alert style={{ marginTop: 18 }} type="error" message={(mutation.error as Error).message} showIcon /> : null}
        <Form layout="vertical" style={{ marginTop: 22 }} onFinish={(values) => mutation.mutate(values)}>
          <Form.Item name="display_name" label="姓名" rules={[{ required: true, message: "请输入姓名" }]}>
            <Input prefix={<UserOutlined />} placeholder="张工" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={[{ required: true, message: "请输入邮箱" }]}>
            <Input prefix={<MailOutlined />} placeholder="you@company.com" />
          </Form.Item>
          <Form.Item name="workspace_name" label="工作区名称" rules={[{ required: true, message: "请输入工作区名称" }]}>
            <Input prefix={<BankOutlined />} placeholder="某某机械设计团队" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, min: 8, message: "密码至少 8 位" }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="至少 8 位" />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={mutation.isPending} block>
            创建并进入
          </Button>
        </Form>
        <div className="enterprise-auth-footer">
          <Text className="muted">已有账号？</Text>
          <Link href={routePath("/console/login")}>返回登录</Link>
        </div>
      </Card>
    </main>
  );
}
