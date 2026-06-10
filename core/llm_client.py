# -*- coding: utf-8 -*-
"""Centralized LLM client for Google AI Studio (Gemini).

This module intentionally keeps a simple `.invoke(prompt).content` interface so
existing callers do not need provider-specific logic.
"""

import os
from typing import Any, Dict, Iterable, List

import requests
from dotenv import load_dotenv

_llm = None
_llm_model = None

load_dotenv()


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
