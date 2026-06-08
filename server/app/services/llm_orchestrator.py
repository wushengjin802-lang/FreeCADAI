"""Cloud LLM orchestration for FreeCAD Python generation."""

from freecad_ai.llm.client import OpenAICompatibleClient
from freecad_ai.llm.prompts import (
    build_generation_messages,
    build_regeneration_with_parameters_messages,
    build_repair_messages,
)
from freecad_ai.llm.schemas import parse_generation_response
from freecad_ai.validator import validate_script

from server.app.core.config import settings


def _client():
    return OpenAICompatibleClient(
        settings.llm_base_url,
        settings.llm_api_key,
        settings.llm_model,
    )


def _parse_and_validate(raw):
    payload = parse_generation_response(raw)
    validate_script(payload["script"])
    return payload


def generate_script(prompt, context, modeling_mode):
    messages = build_generation_messages(prompt, context, modeling_mode)
    raw = _client().chat(messages, temperature=settings.llm_temperature)
    return _parse_and_validate(raw)


def repair_script(prompt, context, failed_script, error_text, modeling_mode):
    messages = build_repair_messages(prompt, context, failed_script, error_text, modeling_mode)
    raw = _client().chat(messages, temperature=settings.llm_temperature)
    return _parse_and_validate(raw)


def regenerate_script(prompt, context, parameters_text, modeling_mode):
    messages = build_regeneration_with_parameters_messages(
        prompt,
        context,
        parameters_text,
        modeling_mode,
    )
    raw = _client().chat(messages, temperature=settings.llm_temperature)
    return _parse_and_validate(raw)
