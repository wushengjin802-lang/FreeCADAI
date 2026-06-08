"""JSONL history storage for generated modeling tasks."""

import json
import os
from datetime import datetime

from freecad_ai.storage.config import _config_dir


def history_path():
    return os.path.join(_config_dir(), "history.jsonl")


def append_history(entry):
    payload = dict(entry)
    payload.setdefault("created_at", datetime.now().isoformat(timespec="seconds"))
    with open(history_path(), "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return payload


def load_recent_history(limit=20):
    path = history_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()[-limit:]
    items = []
    for line in lines:
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items

