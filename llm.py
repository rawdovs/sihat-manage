"""Groq LLM bilan ishlash: so'rov yuborish, retry va JSON action ajratish."""
import asyncio
import json
import logging
import re
from typing import Optional

from openai import AsyncOpenAI

import config
from prompts import SYSTEM_PROMPT

log = logging.getLogger(__name__)
_JSON_RE = re.compile(r"\{[^{}]*\"action\"[^{}]*\}", re.DOTALL)

_client = AsyncOpenAI(
    api_key=config.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1",
)


async def ask(messages: list[dict], extra_system: str = "") -> str:
    """messages: [{"role": "user"/"assistant", "content": "..."}]"""
    system = SYSTEM_PROMPT + (("\n\nKONTEKST:\n" + extra_system) if extra_system else "")
    full = [{"role": "system", "content": system}] + messages

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = await _client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=full,
                max_tokens=config.MAX_TOKENS,
                temperature=0.7,
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:
            last_err = e
            err_s = str(e)
            if any(k in err_s for k in ("429", "rate_limit", "quota", "overloaded")):
                wait = 5 * (2 ** attempt)
                log.warning("Groq rate limit — %ds kutilmoqda (urinish %d/3)", wait, attempt + 1)
                await asyncio.sleep(wait)
                continue
            raise
    assert last_err
    raise last_err


async def ask_text(prompt: str, extra_system: str = "") -> str:
    return await ask([{"role": "user", "content": prompt}], extra_system)


def extract_action(text: str) -> tuple[str, Optional[dict]]:
    cleaned = text.replace("```json", "").replace("```", "")
    matches = list(_JSON_RE.finditer(cleaned))
    if not matches:
        return text.strip(), None
    last = matches[-1]
    try:
        action = json.loads(last.group(0))
    except json.JSONDecodeError:
        return text.strip(), None
    visible = (cleaned[: last.start()] + cleaned[last.end():]).strip()
    return visible, action
