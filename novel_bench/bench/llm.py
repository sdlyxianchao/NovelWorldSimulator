# -*- coding: utf-8 -*-
"""Minimal OpenAI-compatible chat client (stdlib only).

The benchmark has to work with whatever judge endpoint the user has: DeepSeek,
Qwen, GLM, an OpenRouter relay, a local vLLM.  All of them speak
``/chat/completions``, so a 90-line urllib client is both enough and the most
portable option -- no SDK version to pin, no dependency to install.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .config import JudgeProfile, get


class LLMError(RuntimeError):
    pass


# DeepSeek's flash / v4 / reasoner families think by default. Thinking is billed as
# output and eats `max_tokens`, which for a judge call means paying 2-4x for the same
# verdict. These names accept `thinking: {"type": "disabled"}`; other providers
# (Claude, Qwen, GLM, local vLLM) do not, so the switch is name-gated, never global.
_THINK_SWITCH = ("deepseek-flash", "deepseek-v4", "deepseek-reasoner", "deepseek-r1")


def _wants_no_think(model: str) -> bool:
    mode = get("NB_JUDGE_THINKING", "auto").strip().lower()
    if mode == "off":
        return True
    if mode == "on":
        return False
    return any(pat in (model or "").lower() for pat in _THINK_SWITCH)


def _post(url: str, key: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {key}"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def chat(profile: JudgeProfile, system: str, user: str, *,
         max_tokens: int | None = None, temperature: float | None = None,
         retries: int = 3) -> str:
    if not profile.ready:
        raise LLMError(f"judge profile {profile.name!r} is incomplete")
    url = profile.base_url.rstrip("/") + "/chat/completions"
    payload: dict[str, Any] = {
        "model": profile.model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": profile.temperature if temperature is None else temperature,
        "max_tokens": profile.max_tokens if max_tokens is None else max_tokens,
    }
    if _wants_no_think(profile.model):
        payload["thinking"] = {"type": "disabled"}
    last: Exception | None = None
    for attempt in range(retries):
        try:
            data = _post(url, profile.api_key, payload, profile.timeout)
            return data["choices"][0]["message"]["content"] or ""
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError,
                json.JSONDecodeError, TimeoutError, OSError) as e:
            last = e
            # A 4xx that is not 429 will not get better by retrying.
            if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429:
                raise LLMError(f"HTTP {e.code}: {e.reason}") from e
            time.sleep(min(20, 2 ** attempt * 2))
    raise LLMError(f"judge call failed after {retries} attempts: {last}")


def parse_json(text: str) -> dict:
    """Extract the first JSON object from a model reply.

    Judges wrap JSON in fences or add a sentence before it often enough that a
    strict ``json.loads`` is not usable in practice.
    """
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start:end + 1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Last resort: strip trailing commas, which some models emit.
        cleaned = re.sub(r",(\s*[}\]])", r"\1", text)
        return json.loads(cleaned)
