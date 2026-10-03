"""LLM layer (provider-agnostic). Nothing here ever produces a number.

The model only (a) picks among stage-4 match candidates the rules found, (b) rephrases
reasons and copilot answers from tool outputs, (c) reads invoice PDFs/images.
With no provider configured every entry point returns None and callers fall back to
templates or skip the step.

Providers speak the OpenAI chat-completions protocol (Groq, OpenAI, OpenRouter, a local
Ollama). Calls are cached on disk by request hash, so a re-run is stable and free.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from halfca import config
from halfca.engines.matching import Adjudicator

PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-5-mini"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "model": "openai/gpt-oss-120b"},
    "ollama": {"base_url": "http://localhost:11434/v1", "model": "qwen3:8b"},
}


class LLMError(RuntimeError):
    pass


def configured() -> bool:
    return bool(
        config.LLM_PROVIDER in PROVIDERS and (config.LLM_API_KEY or config.LLM_PROVIDER == "ollama")
    )


def model_name() -> str | None:
    if not configured():
        return None
    return config.LLM_MODEL or PROVIDERS[config.LLM_PROVIDER]["model"]


class _Cache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self.data is None:
            try:
                self.data = json.loads(self.path.read_text())
            except (OSError, ValueError):
                self.data = {}
        return self.data

    def get(self, key: str) -> Any:
        with self.lock:
            return self._load().get(key)

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            data = self._load()
            data[key] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0))
            tmp.replace(self.path)


_cache = _Cache(config.DATA_DIR / "llm_cache.json")


class LLMClient:
    def __init__(self) -> None:
        if not configured():
            raise LLMError("no LLM provider configured")
        p = PROVIDERS[config.LLM_PROVIDER]
        self.base_url = config.LLM_BASE_URL or p["base_url"]
        self.model = model_name()
        self.http = httpx.Client(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {config.LLM_API_KEY}"},
            timeout=httpx.Timeout(60.0, connect=10.0),
        )

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        max_tokens: int = 1024,
        cache: bool = True,
        **extra: Any,
    ) -> str:
        """One completion; returns the message text. Retries rate limits politely."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            **extra,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if "gpt-oss" in str(self.model):
            body.setdefault("reasoning_effort", "low")
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if cache and (hit := _cache.get(key)) is not None:
            return str(hit)
        for attempt in range(4):
            res = self.http.post("/chat/completions", json=body)
            if res.status_code == 429 and attempt < 3:
                wait = float(res.headers.get("retry-after", 2**attempt))
                time.sleep(min(wait, 20))
                continue
            if res.status_code == 400 and "reasoning_effort" in body and "reasoning" in res.text:
                body.pop("reasoning_effort")  # provider/model without the knob
                continue
            if res.status_code >= 400:
                raise LLMError(f"{res.status_code}: {res.text[:200]}")
            text = res.json()["choices"][0]["message"].get("content") or ""
            if cache:
                _cache.put(key, text)
            return text
        raise LLMError("rate limited")


def default_adjudicator() -> Adjudicator | None:
    """Stage-4 adjudicator for the configured provider, or None (stage skipped)."""
    if not configured():
        return None
    from halfca.ai.adjudicate import llm_adjudicator

    return llm_adjudicator(LLMClient())
