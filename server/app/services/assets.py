"""Script and model asset helpers."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.models.entities import GeneratedScript, GenerationTask, ModelAsset, ScriptAsset, ScriptVersion


def _asset_name(task: GenerationTask, summary: str) -> str:
    text = (summary or task.prompt or "").strip().replace("\n", " ")
    return (text[:60] or "生成脚本").strip()


def create_script_asset_from_task(db: Session, task: GenerationTask, payload: dict) -> tuple[ScriptAsset, ScriptVersion]:
    asset = ScriptAsset(
        workspace_id=task.workspace_id,
        task_id=task.id,
        name=_asset_name(task, payload.get("summary", "")),
        description=task.prompt or "",
        modeling_mode=task.modeling_mode,
        project_id=task.project_id or "",
        source="generation",
        metadata_json={
            "provider": task.provider,
            "model": task.model,
            "action": task.action,
        },
    )
    db.add(asset)
    db.flush()
    version = ScriptVersion(
        asset_id=asset.id,
        task_id=task.id,
        version=1,
        script=payload.get("script", ""),
        summary=payload.get("summary", ""),
        parameters_json=payload.get("parameters", {}),
        expected_objects_json=payload.get("expected_objects", []),
        validation_status="passed",
        validation_error="",
        created_by="system",
    )
    db.add(version)
    db.flush()
    asset.current_version_id = version.id
    return asset, version


def backfill_script_assets(db: Session, limit: int = 200) -> int:
    rows = db.execute(
        select(GeneratedScript)
        .where(GeneratedScript.asset_id.is_(None))
        .order_by(GeneratedScript.id)
        .limit(limit)
    ).scalars().all()
    count = 0
    for script in rows:
        task = db.get(GenerationTask, script.task_id)
        if task is None:
            continue
        asset, version = create_script_asset_from_task(
            db,
            task,
            {
                "script": script.script,
                "summary": script.summary,
                "parameters": script.parameters_json,
                "expected_objects": script.expected_objects_json,
            },
        )
        version.validation_status = script.validation_status
        version.validation_error = script.validation_error
        script.asset_id = asset.id
        script.version_id = version.id
        count += 1
    db.flush()
    return count


def current_script_version(db: Session, asset: ScriptAsset) -> ScriptVersion | None:
    if asset.current_version_id:
        return db.get(ScriptVersion, asset.current_version_id)
    return db.execute(
        select(ScriptVersion).where(ScriptVersion.asset_id == asset.id).order_by(ScriptVersion.version.desc())
    ).scalars().first()


def copy_script_asset(db: Session, source: ScriptAsset, actor: str) -> ScriptAsset:
    current = current_script_version(db, source)
    copied = ScriptAsset(
        workspace_id=source.workspace_id,
        task_id=source.task_id,
        name=f"{source.name} 副本"[:128],
        description=source.description,
        modeling_mode=source.modeling_mode,
        project_id=source.project_id,
        source="copy",
        favorite=False,
        status="active",
        tags_json=list(source.tags_json or []),
        metadata_json={**(source.metadata_json or {}), "copied_from_asset_id": source.id},
    )
    db.add(copied)
    db.flush()
    if current is not None:
        version = ScriptVersion(
            asset_id=copied.id,
            task_id=current.task_id,
            version=1,
            script=current.script,
            summary=current.summary,
            parameters_json=current.parameters_json,
            expected_objects_json=current.expected_objects_json,
            validation_status=current.validation_status,
            validation_error=current.validation_error,
            created_by=actor or "admin",
        )
        db.add(version)
        db.flush()
        copied.current_version_id = version.id
    return copied


def next_script_version_number(db: Session, asset_id: int) -> int:
    value = db.scalar(select(func.max(ScriptVersion.version)).where(ScriptVersion.asset_id == asset_id)) or 0
    return int(value) + 1


def touch_asset(asset: ScriptAsset | ModelAsset):
    asset.updated_at = datetime.utcnow()
