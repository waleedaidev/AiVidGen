"""Thin OpenRouter (OpenAI-compatible) chat wrapper. Default model is DeepSeek V4 Flash (cheap).

If no OPENROUTER_API_KEY is set, raises NoApiKeyError so callers fall back to rule-based paths.
"""

import json
import re

import httpx

from app.config import get_settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class NoApiKeyError(Exception):
    pass


def chat_completion(
    messages: list[dict], model: str | None = None, json_mode: bool = False, temperature: float = 0.7
) -> str:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise NoApiKeyError("OPENROUTER_API_KEY not set")

    body = {"model": model or settings.openrouter_chat_model, "messages": messages, "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = httpx.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json=body,
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"] or ""


def _parse_json(content: str) -> dict:
    content = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(content[start : end + 1])


def chat_completion_json(messages: list[dict], model: str | None = None, temperature: float = 0.7) -> dict:
    return _parse_json(chat_completion(messages, model=model, json_mode=True, temperature=temperature))
