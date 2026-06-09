"use client";

import { LockOutlined, UserOutlined } from "@ant-design/icons";
import { useMutation } from "@tanstack/react-query";
import { Alert, Button, Card, Form, Input, Typography, App as AntApp } from "antd";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { useAppStore } from "@/lib/store";
import { Providers } from "@/components/Providers";

type LoginValues = {
  username: string;
  password: string;
};

function LoginContent() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const setToken = useAppStore((state) => state.setToken);
  const setPrincipal = useAppStore((state) => state.setPrincipal);

  const mutation = useMutation({
    mutationFn: (values: LoginValues) => login(values.username, values.password),
    onSuccess: (data) => {
      setToken(data.token);
      setPrincipal(data.user);
      message.success("登录成功");
      router.push(routePath("/admin"));
    }
  });

  return (
    <main
      className="login-page"
      style={{
        display: "grid",
        minHeight: "100vh",
        placeItems: "center",
        padding: 18,
        background: "#f4f3ed"
      }}
    >
      <Card className="login-card console-card" style={{ width: "min(430px, 100%)", maxWidth: 430 }}>
        <Typography.Title level={2} style={{ marginBottom: 4 }}>
          FreeCADAI
        </Typography.Title>
        <Typography.Paragraph className="muted">平台管理后台登录</Typography.Paragraph>
        {mutation.error ? <Alert type="error" showIcon message={mutation.error.message} style={{ marginBottom: 16 }} /> : null}
        <Form<LoginValues>
          layout="vertical"
          initialValues={{ username: "admin" }}
          onFinish={(values) => mutation.mutate(values)}
        >
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: "请输入用户名" }]}>
            <Input prefix={<UserOutlined />} autoComplete="username" />
          </Form.Item>
          <Form.Item name="password" label="密码" rules={[{ required: true, message: "请输入密码" }]}>
            <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={mutation.isPending}>
            登录
          </Button>
        </Form>
      </Card>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Providers>
      <LoginContent />
    </Providers>
  );
}
