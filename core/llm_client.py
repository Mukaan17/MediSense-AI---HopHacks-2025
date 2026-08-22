# -*- coding: utf-8 -*-
"""Centralized LLM clients.

Two providers:
- Anthropic Claude (primary when ANTHROPIC_API_KEY is set): true async token
  streaming for the live HUD and a deep final-report call.
- Google AI Studio Gemini (fallback / default): synchronous
  `.invoke(prompt).content` contract kept for all existing callers.
"""

import os
from typing import Any, AsyncIterator, Dict, Iterable, List

import requests
from dotenv import load_dotenv

_llm = None
_llm_model = None
_llm_temperature = None

load_dotenv()

# --------------- Anthropic (Claude) ---------------

DEFAULT_LIVE_MODEL = "claude-haiku-4-5"
DEFAULT_FINAL_MODEL = "claude-sonnet-4-6"

_anthropic_async = None


def anthropic_available() -> bool:
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def _get_anthropic_async():
    """Cached AsyncAnthropic client. Raises if the SDK or key is missing."""
    global _anthropic_async
    if _anthropic_async is None:
        if not anthropic_available():
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import AsyncAnthropic
        _anthropic_async = AsyncAnthropic()
    return _anthropic_async


async def stream_claude_tokens(prompt: str, model: str = None, system: str = "",
                               max_tokens: int = 512) -> AsyncIterator[str]:
    """Async generator yielding text deltas as they arrive (true streaming)."""
    client = _get_anthropic_async()
    kwargs: Dict[str, Any] = {
        "model": model or DEFAULT_LIVE_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text


async def invoke_claude_full(prompt: str, model: str = None, system: str = "",
                             max_tokens: int = 4096) -> str:
    """Full response for report generation. Streams under the hood so large
    outputs don't hit HTTP timeouts."""
    client = _get_anthropic_async()
    kwargs: Dict[str, Any] = {
        "model": model or DEFAULT_FINAL_MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    async with client.messages.stream(**kwargs) as stream:
        message = await stream.get_final_message()
    parts = [block.text for block in message.content if getattr(block, "type", "") == "text"]
    return "\n".join(parts).strip()

# --------------- Gemini ---------------


class _InvokeResponse:
    def __init__(self, content: str):
        self.content = content


class _GeminiInvokeClient:
    def __init__(self, api_key: str, model: str, temperature: float):
        self.api_key = api_key
        self.model = model
        self.temperature = float(temperature)
        self.timeout_s = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
        self.max_output_tokens = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096"))

    def _to_text(self, prompt: Any) -> str:
        if isinstance(prompt, str):
            return prompt
        if isinstance(prompt, (list, tuple)):
            parts: List[str] = []
            for item in prompt:
                if isinstance(item, dict):
                    role = str(item.get("role", "user"))
                    content = str(item.get("content", ""))
                    parts.append(f"{role}: {content}")
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        if isinstance(prompt, dict):
            role = str(prompt.get("role", "user"))
            content = str(prompt.get("content", prompt))
            return f"{role}: {content}"
        return str(prompt)

    def invoke(self, prompt: Any) -> _InvokeResponse:
        text = self._to_text(prompt).strip()
        if not text:
            return _InvokeResponse("")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
        payload: Dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_output_tokens,
            },
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout_s)
        except Exception as e:
            raise RuntimeError(f"Gemini request failed: {e}") from e

        if resp.status_code >= 400:
            detail = ""
            try:
                body = resp.json()
                detail = str((body.get("error") or {}).get("message") or body)
            except Exception:
                detail = resp.text[:500]
            raise RuntimeError(f"Gemini API error ({resp.status_code}): {detail}")

        try:
            body = resp.json()
        except Exception as e:
            raise RuntimeError(f"Gemini returned non-JSON response: {e}") from e

        candidates = body.get("candidates") or []
        if not candidates:
            return _InvokeResponse("")
        first = candidates[0] or {}
        content = first.get("content") or {}
        parts = content.get("parts") or []
        chunks: List[str] = []
        for p in parts:
            t = (p or {}).get("text")
            if t:
                chunks.append(str(t))

        return _InvokeResponse("\n".join(chunks).strip())


def get_llm(model: str = None, temperature: float = None):
    """Return a cached Gemini client with `.invoke(...).content` contract."""
    global _llm, _llm_model
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set. Please set your Google AI Studio API key.")

    requested_model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    temp = float(temperature if temperature is not None else os.getenv("LLM_TEMPERATURE", "0.1"))

    if _llm is None or _llm_model != requested_model:
        _llm = _GeminiInvokeClient(api_key=api_key, model=requested_model, temperature=temp)
        _llm_model = requested_model
        print(f"[LLM] Initialized Gemini model: {_llm_model}")

    return _llm


def stream_gemini_chat(messages: Iterable[Dict[str, Any]], model: str = None, temperature: float = 0.6):
    """Compatibility streaming helper.

    Google streaming endpoint integration can be added later; for now this yields
    one chunk from `invoke` so callers can still iterate safely.
    """
    llm = get_llm(model=model, temperature=temperature)
    text = llm.invoke(list(messages)).content
    if text:
        yield text
