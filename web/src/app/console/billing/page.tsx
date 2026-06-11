"use client";

import { CreditCardOutlined } from "@ant-design/icons";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Alert, App as AntApp, Button, Card, Col, Progress, Row, Space, Tag, Typography } from "antd";
import { useRouter } from "next/navigation";
import { useEffect, useMemo } from "react";
import { ConsoleShell } from "@/components/ConsoleShell";
import { consoleApi } from "@/lib/api";
import { routePath } from "@/lib/routes";
import { canManageWorkspace, useConsoleStore } from "@/lib/store";
import type { BillingPlan } from "@/lib/types";

const { Text, Title } = Typography;

function money(cents: number) {
  return cents ? `$${(cents / 100).toFixed(2)}/月` : "免费/联系销售";
}

function limitText(value?: number | null) {
  return value == null ? "不限" : String(value);
}

function percent(used?: number, limit?: number | null) {
  if (!limit) return 0;
  return Math.min(100, Math.round(((used || 0) / limit) * 100));
}

export default function ConsoleBillingPage() {
  const router = useRouter();
  const { message } = AntApp.useApp();
  const token = useConsoleStore((state) => state.token);
  const workspaceId = useConsoleStore((state) => state.workspaceId);
  const setUser = useConsoleStore((state) => state.setUser);
  const setWorkspaces = useConsoleStore((state) => state.setWorkspaces);

  useEffect(() => {
    if (!token) router.replace(routePath("/console/login"));
  }, [router, token]);

  const meQuery = useQuery({ queryKey: ["console-me", token], queryFn: () => consoleApi.me(token), enabled: Boolean(token) });
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
  const plans = useQuery({ queryKey: ["console-billing-plans", token], queryFn: () => consoleApi.billingPlans(token), enabled: Boolean(token) });
  const summary = useQuery({ queryKey: ["console-billing-summary", token, workspace?.id], queryFn: () => consoleApi.billingSummary(token, workspace?.id as number), enabled: Boolean(token && workspace?.id) });
  const quota = summary.data?.workspaces[0];

  const checkout = useMutation({
    mutationFn: (plan: string) => consoleApi.createCheckout(token, { workspace_id: workspace?.id as number, plan }),
    onSuccess: (result) => message.success(result.message)
  });

  if (!token) return null;

  return (
    <ConsoleShell>
      <Space direction="vertical" size={18} className="full-width">
        <section className="enterprise-section-title">
          <div>
            <Title level={3}><CreditCardOutlined /> 账单与套餐</Title>
            <Text className="muted">查看当前套餐、额度使用和升级入口。</Text>
          </div>
          {quota ? <Tag color="blue">{quota.plan}</Tag> : null}
        </section>

        {summary.error || checkout.error ? <Alert type="error" showIcon message={((summary.error || checkout.error) as Error).message} /> : null}
        {!canManage ? <Alert type="info" showIcon message="当前角色可以查看套餐和额度，升级套餐需要 Owner/Admin 权限。" /> : null}
        {quota?.warnings?.length ? <Alert type="warning" showIcon message="额度提醒" description={quota.warnings.join("；")} /> : null}

        {quota ? (
          <Card className="console-card" title="当前周期">
            <Space direction="vertical" size={16} className="full-width">
              <div className="enterprise-plan-row"><Text>计费周期开始</Text><Text>{quota.usage.billing_period_start}</Text></div>
              <div>
                <div className="enterprise-plan-row"><Text>任务</Text><Text>{quota.usage.task_count} / {limitText(quota.limits.tasks)}</Text></div>
                <Progress percent={percent(quota.usage.task_count, quota.limits.tasks)} />
              </div>
              <div>
                <div className="enterprise-plan-row"><Text>模板</Text><Text>{quota.usage.template_count} / {limitText(quota.limits.templates)}</Text></div>
                <Progress percent={percent(quota.usage.template_count, quota.limits.templates)} />
              </div>
              <div>
                <div className="enterprise-plan-row"><Text>API Key</Text><Text>{quota.usage.api_key_count} / {limitText(quota.limits.api_keys)}</Text></div>
                <Progress percent={percent(quota.usage.api_key_count, quota.limits.api_keys)} />
              </div>
              <div className="enterprise-plan-grid">
                <span>并发：{quota.usage.concurrent_count} / {limitText(quota.limits.concurrent)}</span>
                <span>总 Token：{quota.usage.total_tokens}</span>
                <span>预估成本：${Number(quota.usage.estimated_cost || 0).toFixed(4)}</span>
                <span>月费：{money(quota.monthly_price_cents)}</span>
              </div>
            </Space>
          </Card>
        ) : null}

        <Row gutter={[16, 16]}>
          {(plans.data || []).map((plan: BillingPlan) => (
            <Col xs={24} md={12} xl={6} key={plan.name}>
              <Card className="console-card enterprise-plan-card" title={<Space><span>{plan.name}</span>{quota?.plan === plan.name ? <Tag color="green">当前</Tag> : null}</Space>}>
                <Space direction="vertical" size={10} className="full-width">
                  <Title level={4} style={{ margin: 0 }}>{money(plan.monthly_price_cents)}</Title>
                  <Text>任务：{limitText(plan.limits.tasks)}</Text>
                  <Text>模板：{limitText(plan.limits.templates)}</Text>
                  <Text>API Key：{limitText(plan.limits.api_keys)}</Text>
                  <Text>并发：{limitText(plan.limits.concurrent)}</Text>
                  <Button block type={quota?.plan === plan.name ? "default" : "primary"} disabled={!canManage || quota?.plan === plan.name} loading={checkout.isPending} onClick={() => checkout.mutate(plan.name)}>
                    {quota?.plan === plan.name ? "当前套餐" : "申请升级"}
                  </Button>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </Space>
    </ConsoleShell>
  );
}
