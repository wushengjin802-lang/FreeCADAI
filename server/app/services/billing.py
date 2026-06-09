"""Plan limits, quota checks, usage accounting, and billing placeholders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.models.entities import ApiKey, GenerationTask, Template, UsageRecord, Workspace


@dataclass(frozen=True)
class PlanLimits:
    name: str
    task_limit: int | None
    template_limit: int | None
    api_key_limit: int | None
    concurrent_limit: int | None
    monthly_price_cents: int


PLAN_LIMITS: dict[str, PlanLimits] = {
    "free": PlanLimits("free", task_limit=100, template_limit=10, api_key_limit=1, concurrent_limit=1, monthly_price_cents=0),
    "pro": PlanLimits("pro", task_limit=1000, template_limit=100, api_key_limit=5, concurrent_limit=3, monthly_price_cents=9900),
    "team": PlanLimits("team", task_limit=10000, template_limit=1000, api_key_limit=20, concurrent_limit=10, monthly_price_cents=49900),
    "enterprise": PlanLimits("enterprise", task_limit=None, template_limit=None, api_key_limit=None, concurrent_limit=None, monthly_price_cents=0),
}

RESOURCE_LABELS = {
    "tasks": "任务数",
    "templates": "模板数",
    "api_keys": "Key 数",
    "concurrent": "并发数",
}

MODEL_PRICING_PER_1K_TOKENS: dict[str, tuple[Decimal, Decimal]] = {
    "default": (Decimal("0.001"), Decimal("0.002")),
    "deepseek-chat": (Decimal("0.00014"), Decimal("0.00028")),
    "deepseek-v3": (Decimal("0.00014"), Decimal("0.00028")),
    "deepseek-v3-flash": (Decimal("0.00007"), Decimal("0.00014")),
    "gpt-4o-mini": (Decimal("0.00015"), Decimal("0.00060")),
    "gpt-4o": (Decimal("0.005"), Decimal("0.015")),
}


def current_billing_period_start(now: datetime | None = None) -> datetime:
    now = now or datetime.utcnow()
    return datetime(now.year, now.month, 1)


def plan_limits(plan: str | None) -> PlanLimits:
    return PLAN_LIMITS.get((plan or "free").lower(), PLAN_LIMITS["free"])


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def workspace_usage(db: Session, workspace: Workspace) -> dict[str, Any]:
    period_start = current_billing_period_start()
    task_count = _count(
        db,
        select(func.count())
        .select_from(GenerationTask)
        .where(GenerationTask.workspace_id == workspace.id, GenerationTask.created_at >= period_start),
    )
    template_count = _count(
        db,
        select(func.count()).select_from(Template).where(Template.workspace_id == workspace.id),
    )
    api_key_count = _count(
        db,
        select(func.count()).select_from(ApiKey).where(ApiKey.workspace_id == workspace.id, ApiKey.status == "active"),
    )
    concurrent_count = _count(
        db,
        select(func.count()).select_from(GenerationTask).where(GenerationTask.workspace_id == workspace.id, GenerationTask.status == "running"),
    )
    tokens = db.execute(
        select(
            func.coalesce(func.sum(UsageRecord.input_tokens), 0),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0),
            func.coalesce(func.sum(UsageRecord.total_tokens), 0),
            func.coalesce(func.sum(UsageRecord.estimated_cost), 0),
        ).where(UsageRecord.workspace_id == workspace.id, UsageRecord.created_at >= period_start)
    ).one()
    return {
        "billing_period_start": period_start.date().isoformat(),
        "task_count": task_count,
        "template_count": template_count,
        "api_key_count": api_key_count,
        "concurrent_count": concurrent_count,
        "input_tokens": int(tokens[0] or 0),
        "output_tokens": int(tokens[1] or 0),
        "total_tokens": int(tokens[2] or 0),
        "estimated_cost": float(tokens[3] or 0),
    }


def quota_summary(db: Session, workspace: Workspace) -> dict[str, Any]:
    limits = plan_limits(workspace.plan)
    usage = workspace_usage(db, workspace)
    limit_values = {
        "tasks": limits.task_limit,
        "templates": limits.template_limit,
        "api_keys": limits.api_key_limit,
        "concurrent": limits.concurrent_limit,
    }
    usage_values = {
        "tasks": usage["task_count"],
        "templates": usage["template_count"],
        "api_keys": usage["api_key_count"],
        "concurrent": usage["concurrent_count"],
    }
    warnings = []
    for key, limit in limit_values.items():
        used = usage_values[key]
        if limit is None:
            continue
        if used >= limit:
            warnings.append("{} 已达到套餐上限：{}/{}".format(RESOURCE_LABELS[key], used, limit))
        elif used / max(limit, 1) >= 0.8:
            warnings.append("{} 接近套餐上限：{}/{}".format(RESOURCE_LABELS[key], used, limit))
    return {
        "workspace_id": workspace.id,
        "workspace_name": workspace.name,
        "plan": limits.name,
        "status": workspace.status,
        "monthly_price_cents": limits.monthly_price_cents,
        "limits": limit_values,
        "usage": usage,
        "warnings": warnings,
    }


def assert_workspace_quota(db: Session, workspace: Workspace, resource: str, increment: int = 1) -> None:
    limits = plan_limits(workspace.plan)
    usage = workspace_usage(db, workspace)
    limit = {
        "tasks": limits.task_limit,
        "templates": limits.template_limit,
        "api_keys": limits.api_key_limit,
        "concurrent": limits.concurrent_limit,
    }[resource]
    used = {
        "tasks": usage["task_count"],
        "templates": usage["template_count"],
        "api_keys": usage["api_key_count"],
        "concurrent": usage["concurrent_count"],
    }[resource]
    if limit is not None and used + increment > limit:
        raise HTTPException(
            status_code=402,
            detail="工作区 {} 的 {} 已超过 {} 套餐限制：{}/{}。请升级套餐或释放资源。".format(
                workspace.name,
                RESOURCE_LABELS[resource],
                limits.name,
                used,
                limit,
            ),
        )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    key = (model or "").lower()
    pricing = MODEL_PRICING_PER_1K_TOKENS.get(key)
    if pricing is None:
        pricing = next((value for name, value in MODEL_PRICING_PER_1K_TOKENS.items() if name != "default" and name in key), None)
    input_price, output_price = pricing or MODEL_PRICING_PER_1K_TOKENS["default"]
    return (Decimal(input_tokens) / Decimal(1000) * input_price) + (Decimal(output_tokens) / Decimal(1000) * output_price)


def record_usage(db: Session, workspace: Workspace, task: GenerationTask, usage: dict[str, Any] | None) -> UsageRecord:
    usage = usage or {}
    input_tokens = int(usage.get("input_tokens") or usage.get("prompt_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    cost = usage.get("estimated_cost")
    if cost is None:
        cost = estimate_cost(task.model, input_tokens, output_tokens)
    item = UsageRecord(
        workspace_id=workspace.id,
        task_id=task.id,
        provider=task.provider,
        model=task.model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        estimated_cost=cost,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def billing_plans() -> list[dict[str, Any]]:
    return [
        {
            "name": item.name,
            "monthly_price_cents": item.monthly_price_cents,
            "limits": {
                "tasks": item.task_limit,
                "templates": item.template_limit,
                "api_keys": item.api_key_limit,
                "concurrent": item.concurrent_limit,
            },
        }
        for item in PLAN_LIMITS.values()
    ]
