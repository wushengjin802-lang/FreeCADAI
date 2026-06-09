"""Background worker for asynchronous FreeCADAI generation tasks."""

import signal
import time
import traceback

from server.app.db.session import SessionLocal
from server.app.models.entities import GenerationTask, Workspace
from server.app.services.billing import record_usage
from server.app.services.llm_orchestrator import generate_script, regenerate_script, repair_script
from server.app.services.task_queue import bump_generation_task_attempt, load_generation_task_payload, pop_generation_task
from server.app.services.task_store import mark_task_failed, mark_task_running, mark_task_success


_running = True


def _stop(_signum, _frame):
    global _running
    _running = False


def _execute_payload(payload):
    action = payload.get("action")
    if action == "generate":
        return generate_script(payload.get("prompt", ""), payload.get("context", ""), payload.get("modeling_mode", "3d_solid"))
    if action == "repair":
        return repair_script(
            payload.get("prompt", ""),
            payload.get("context", ""),
            payload.get("failed_script", ""),
            payload.get("error_text", ""),
            payload.get("modeling_mode", "3d_solid"),
        )
    if action == "regenerate":
        return regenerate_script(
            payload.get("prompt", ""),
            payload.get("context", ""),
            payload.get("parameters", ""),
            payload.get("modeling_mode", "3d_solid"),
        )
    raise ValueError("Unsupported queued action: {}".format(action))


def process_task(task_id: int) -> None:
    db = SessionLocal()
    started = time.time()
    try:
        task = db.get(GenerationTask, task_id)
        if task is None:
            return
        if task.status == "canceled":
            return
        if task.status not in {"queued", "failed"}:
            return
        workspace = db.get(Workspace, task.workspace_id)
        if workspace is None or workspace.status != "active":
            mark_task_failed(db, task, RuntimeError("Workspace is not active."), 0)
            return
        payload = load_generation_task_payload(task.id)
        if payload is None:
            mark_task_failed(db, task, RuntimeError("Queued task payload is missing."), 0)
            return
        bump_generation_task_attempt(task.id)
        mark_task_running(db, task)
        result = _execute_payload(payload)
        if task.status == "canceled":
            db.commit()
            return
        latency_ms = int((time.time() - started) * 1000)
        mark_task_success(db, task, result, latency_ms)
        record_usage(db, workspace, task, result.get("_usage"))
    except Exception as exc:
        task = db.get(GenerationTask, task_id)
        if task is not None:
            latency_ms = int((time.time() - started) * 1000)
            mark_task_failed(db, task, RuntimeError("{}\n{}".format(exc, traceback.format_exc())), latency_ms)
    finally:
        db.close()


def main():
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        task_id = pop_generation_task(timeout=5)
        if task_id is None:
            continue
        process_task(task_id)


if __name__ == "__main__":
    main()
