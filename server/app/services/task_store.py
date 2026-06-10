"""Persistence helpers for generation tasks and execution reports."""

from datetime import datetime

from sqlalchemy.orm import Session

from server.app.core.config import settings
from server.app.models.entities import ExecutionReport, GeneratedScript, GenerationTask, Workspace


def create_task(db: Session, workspace: Workspace, action, prompt, context, modeling_mode, project_id, status="running"):
    task = GenerationTask(
        workspace_id=workspace.id,
        project_id=project_id or "",
        action=action,
        modeling_mode=modeling_mode,
        prompt=prompt,
        context_snapshot=context or "",
        provider=settings.llm_provider,
        model=settings.llm_model,
        status=status,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def mark_task_running(db: Session, task: GenerationTask):
    task.status = "running"
    task.updated_at = datetime.utcnow()
    db.commit()


def mark_task_success(db: Session, task: GenerationTask, payload, latency_ms):
    task.status = "succeeded"
    task.latency_ms = latency_ms
    task.updated_at = datetime.utcnow()
    script = GeneratedScript(
        task_id=task.id,
        script=payload.get("script", ""),
        summary=payload.get("summary", ""),
        parameters_json=payload.get("parameters", {}),
        expected_objects_json=payload.get("expected_objects", []),
        validation_status="passed",
    )
    db.add(script)
    db.commit()
    db.refresh(script)
    return script


def mark_task_failed(db: Session, task: GenerationTask, error, latency_ms):
    task.status = "failed"
    task.error_message = str(error)
    task.latency_ms = latency_ms
    task.updated_at = datetime.utcnow()
    db.commit()


def mark_task_canceled(db: Session, task: GenerationTask):
    task.status = "canceled"
    task.updated_at = datetime.utcnow()
    db.commit()


def save_execution_report(db: Session, report):
    item = ExecutionReport(
        task_id=report.task_id,
        script_id=report.script_id,
        plugin_version=report.plugin_version,
        freecad_version=report.freecad_version,
        status=report.status,
        document_name=report.document_name,
        object_count=report.object_count,
        new_objects_json=report.new_objects,
        error_trace=report.error_trace,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
