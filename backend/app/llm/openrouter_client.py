"""Thin OpenRouter (OpenAI-compatible) chat wrapper.

If no OPENROUTER_API_KEY is set, raise NoApiKeyError so callers (chat_llm, graph nodes) can
fall back to a scripted/rule-based path — the whole app still runs locally with zero keys.
"""

import json

import httpx

from app.config import get_settings

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class NoApiKeyError(Exception):
    pass


def chat_completion(messages: list[dict], model: str | None = None, json_mode: bool = False) -> str:
    settings = get_settings()
    if not settings.openrouter_api_key:
        raise NoApiKeyError("OPENROUTER_API_KEY not set")

    body = {
        "model": model or settings.openrouter_chat_model,
        "messages": messages,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    resp = httpx.post(
        OPENROUTER_URL,
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def chat_completion_json(messages: list[dict], model: str | None = None) -> dict:
    content = chat_completion(messages, model=model, json_mode=True)
    return json.loads(content)
