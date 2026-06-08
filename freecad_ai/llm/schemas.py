"""Parse and validate LLM JSON payloads."""

import json


REQUIRED_KEYS = ("summary", "parameters", "script", "expected_objects", "notes")


class LLMResponseError(ValueError):
    pass


def _strip_code_fence(text):
    content = text.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


def _extract_json_object(text):
    content = _strip_code_fence(text)
    if content.startswith("{") and content.endswith("}"):
        return content
    start = content.find("{")
    end = content.rfind("}")
    if start >= 0 and end > start:
        return content[start : end + 1]
    return content


def parse_generation_response(text):
    try:
        data = json.loads(_extract_json_object(text))
    except json.JSONDecodeError as exc:
        raise LLMResponseError("LLM did not return valid JSON: {}".format(exc))

    if not isinstance(data, dict):
        raise LLMResponseError("LLM response must be a JSON object.")

    missing = [key for key in REQUIRED_KEYS if key not in data]
    if missing:
        raise LLMResponseError("LLM response is missing keys: {}".format(", ".join(missing)))

    if not isinstance(data["script"], str) or not data["script"].strip():
        raise LLMResponseError("LLM response script must be a non-empty string.")

    if not isinstance(data["expected_objects"], list):
        data["expected_objects"] = []
    if not isinstance(data["notes"], list):
        data["notes"] = []
    if not isinstance(data["parameters"], dict):
        data["parameters"] = {}

    return data

