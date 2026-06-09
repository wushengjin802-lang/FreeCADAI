"""Redis-backed asynchronous generation queue."""

from __future__ import annotations

import json
import time
from typing import Any

from server.app.core.redis import get_redis_client


QUEUE_KEY = "freecadai:generation:queue"
TASK_PAYLOAD_KEY = "freecadai:generation:task:{}"


def enqueue_generation_task(task_id: int, payload: dict[str, Any]) -> None:
    client = get_redis_client()
    key = TASK_PAYLOAD_KEY.format(task_id)
    fields = {
        "payload": json.dumps(payload, ensure_ascii=False),
        "attempts": str(int(payload.get("attempts") or 0)),
        "queued_at": str(time.time()),
    }
    for field, value in fields.items():
        client.hset(key, field, value)
    client.lpush(QUEUE_KEY, str(task_id))


def load_generation_task_payload(task_id: int) -> dict[str, Any] | None:
    text = get_redis_client().hget(TASK_PAYLOAD_KEY.format(task_id), "payload")
    if not text:
        return None
    return json.loads(text)


def bump_generation_task_attempt(task_id: int) -> int:
    return int(get_redis_client().hincrby(TASK_PAYLOAD_KEY.format(task_id), "attempts", 1))


def retry_generation_task(task_id: int) -> None:
    get_redis_client().lpush(QUEUE_KEY, str(task_id))


def pop_generation_task(timeout: int = 5) -> int | None:
    item = get_redis_client().brpop(QUEUE_KEY, timeout=timeout)
    if not item:
        return None
    _, task_id = item
    return int(task_id)
