"""
LLM Provider abstraction.

The agent loop only calls `provider.generate(messages, stop_sequences=[...])`
and gets back an `LLMResponse`; it doesn't care which provider is behind it.

STAGE 0 (current): one OpenAI-compatible /chat/completions call,
naive key rotation on 429/5xx. No provider fallback yet.

Never hardcode API keys — they are read from an environment variable (Section VI.3).
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import List, Optional

import requests


@dataclass
class LLMResponse:
    """Normalized result of one LLM call."""

    text: str
    input_tokens: int
    output_tokens: int
    request_time_ms: float
    retries: int = 0


class LLMProvider:
    """Talks to any OpenAI-compatible API (OpenRouter / Groq / ...).

    Several keys can be stored comma-separated in one env var:
        OPENROUTER_API_KEY=key1,key2,key3
    """

    def __init__(self, model_name: str, base_url: str, api_key_env: str):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        raw_keys = os.environ.get(api_key_env, "")
        self.api_keys: List[str] = [k.strip() for k in raw_keys.split(",") if k.strip()]
        if not self.api_keys:
            raise ValueError(
                f"No API key found in environment variable {api_key_env}. "
                f"Check your .env file."
            )
        self._key_index = 0

    def _current_key(self) -> str:
        return self.api_keys[self._key_index]

    def _rotate_key(self) -> None:
        self._key_index = (self._key_index + 1) % len(self.api_keys)

    def generate(
        self,
        messages: List[dict],
        stop_sequences: Optional[List[str]] = None,
        max_tokens: int = 1024,
        max_retries: int = 3,
    ) -> LLMResponse:
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0,
        }
        if stop_sequences:
            payload["stop"] = stop_sequences

        retries = 0
        start = time.perf_counter()
        while True:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._current_key()}"},
                json=payload,
                timeout=120,
            )
            # Rate limited or server error: switch key, wait a bit, try again.
            if response.status_code == 429 or response.status_code >= 500:
                if retries < max_retries:
                    retries += 1
                    self._rotate_key()
                    time.sleep(2 * retries)
                    continue
            if not response.ok:
                # Include the body: providers explain the real cause there (e.g. unknown model).
                raise RuntimeError(
                    f"HTTP {response.status_code} from {response.url}: {response.text[:500]}"
                )
            break

        data = response.json()
        usage = data.get("usage") or {}
        return LLMResponse(
            text=data["choices"][0]["message"]["content"] or "",
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            request_time_ms=(time.perf_counter() - start) * 1000,
            retries=retries,
        )
