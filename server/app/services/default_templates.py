"""Default template seeding helpers."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from freecad_ai.templates import TEMPLATES
from server.app.models.entities import Template


def _category_for_template(name: str) -> str:
    if name.startswith("二维草图"):
        return "草图绘制"
    if "钣金" in name:
        return "钣金结构"
    if "机架" in name or "电控盒" in name:
        return "装配设计"
    if name.startswith("修改选中对象"):
        return "参数化"
    if any(keyword in name for keyword in ("支架", "角码", "底座", "支撑", "导轨", "联轴器", "齿轮", "带轮", "散热片", "法兰", "轴承", "轴")):
        return "零件建模"
    return "通用"


def builtin_template_rows() -> list[dict]:
    return [
        {
            "workspace_id": None,
            "name": item["name"],
            "category": item.get("category") or _category_for_template(item["name"]),
            "prompt": item["prompt"],
            "enabled": True,
        }
        for item in TEMPLATES
    ]


def ensure_default_templates(db: Session, update_existing: bool = False) -> list[Template]:
    seeded: list[Template] = []
    for item in builtin_template_rows():
        existing = db.execute(
            select(Template).where(
                Template.workspace_id.is_(None),
                Template.name == item["name"],
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = Template(**item)
            db.add(existing)
        elif update_existing:
            existing.category = item["category"]
            existing.prompt = item["prompt"]
            existing.enabled = item["enabled"]
        seeded.append(existing)
    db.flush()
    return seeded
