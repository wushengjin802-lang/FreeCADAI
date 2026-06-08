"""Plugin-facing API endpoints."""

import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from freecad_ai.templates import TEMPLATES

from server.app.db.session import get_db
from server.app.models.entities import Template
from server.app.schemas.plugin import (
    ExecutionReportRequest,
    ExecutionReportResponse,
    GenerateRequest,
    GenerationResponse,
    PluginTemplate,
    PluginTemplatesResponse,
    RegenerateRequest,
    RepairRequest,
    VerifyRequest,
    VerifyResponse,
)
from server.app.services.auth import authenticate_plugin
from server.app.services.llm_orchestrator import generate_script, regenerate_script, repair_script
from server.app.services.task_store import create_task, mark_task_failed, mark_task_success, save_execution_report


router = APIRouter(prefix="/api/v1/plugin", tags=["plugin"])


@router.get("/health")
def health():
    return {"ok": True, "service": "FreeCADAI SaaS"}


@router.post("/auth/verify", response_model=VerifyResponse)
def verify_plugin(
    payload: VerifyRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return VerifyResponse(ok=True, workspace_id=workspace.id, message="Plugin API Key is valid.")


@router.get("/templates", response_model=PluginTemplatesResponse)
def plugin_templates(
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    rows = db.execute(
        select(Template).where(Template.enabled.is_(True)).order_by(Template.category, Template.name)
    ).scalars().all()
    if rows:
        return PluginTemplatesResponse(
            templates=[
                PluginTemplate(id=str(row.id), name=row.name, category=row.category, prompt=row.prompt)
                for row in rows
            ]
        )
    return PluginTemplatesResponse(
        templates=[
            PluginTemplate(
                id="builtin-{}".format(index),
                name=item["name"],
                category="builtin",
                prompt=item["prompt"],
            )
            for index, item in enumerate(TEMPLATES, start=1)
        ]
    )


def _run_generation(db, workspace, action, request, callback):
    task = create_task(
        db,
        workspace,
        action,
        request.prompt,
        request.context,
        request.modeling_mode,
        request.project_id,
    )
    started = time.time()
    try:
        payload = callback()
        latency_ms = int((time.time() - started) * 1000)
        script = mark_task_success(db, task, payload, latency_ms)
        payload["task_id"] = task.id
        payload["script_id"] = script.id
        return GenerationResponse(**payload)
    except Exception as exc:
        latency_ms = int((time.time() - started) * 1000)
        mark_task_failed(db, task, exc, latency_ms)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate", response_model=GenerationResponse)
def generate(
    request: GenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "generate",
        request,
        lambda: generate_script(request.prompt, request.context, request.modeling_mode),
    )


@router.post("/repair", response_model=GenerationResponse)
def repair(
    request: RepairRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "repair",
        request,
        lambda: repair_script(
            request.prompt,
            request.context,
            request.failed_script,
            request.error_text,
            request.modeling_mode,
        ),
    )


@router.post("/regenerate", response_model=GenerationResponse)
def regenerate(
    request: RegenerateRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    return _run_generation(
        db,
        workspace,
        "regenerate",
        request,
        lambda: regenerate_script(
            request.prompt,
            request.context,
            request.parameters,
            request.modeling_mode,
        ),
    )


@router.post("/execution-reports", response_model=ExecutionReportResponse)
def execution_report(
    request: ExecutionReportRequest,
    db: Session = Depends(get_db),
    workspace=Depends(authenticate_plugin),
):
    item = save_execution_report(db, request)
    return ExecutionReportResponse(ok=True, report_id=item.id)
