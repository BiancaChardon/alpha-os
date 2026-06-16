from __future__ import annotations

import json
import re

from anthropic import Anthropic

from config import settings


def get_client() -> Anthropic | None:
    if not settings.anthropic_api_key:
        return None
    return Anthropic(api_key=settings.anthropic_api_key)


def call_claude(model: str, system: str, user_content: str, max_tokens: int = 4096) -> str | None:
    client = get_client()
    if not client:
        return None
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text
    except Exception:
        return None


def extract_json(text: str) -> dict | list | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None
