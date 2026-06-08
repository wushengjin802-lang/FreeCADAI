"""Persistent local configuration for the FreeCADAI prototype."""

import json
import os

try:
    import FreeCAD as App
except ImportError:
    App = None


DEFAULT_CONFIG = {
    "base_url": "https://api.openai.com/v1",
    "api_key": "",
    "model": "gpt-4.1-mini",
    "temperature": 0.1,
}


def _config_dir():
    if App is not None:
        root = App.getUserAppDataDir()
    else:
        root = os.path.expanduser("~")
    path = os.path.join(root, "FreeCADAI")
    os.makedirs(path, exist_ok=True)
    return path


def config_path():
    return os.path.join(_config_dir(), "config.json")


def load_config():
    data = dict(DEFAULT_CONFIG)
    path = config_path()
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            saved = json.load(handle)
        if isinstance(saved, dict):
            data.update(saved)
    return data


def save_config(config):
    data = dict(DEFAULT_CONFIG)
    data.update(config)
    with open(config_path(), "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
    return data
