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
    """request hash → response, in one JSON file. Writes merge with what is on disk, so
    the API and a `make data` run in another process do not drop each other's entries."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data: dict[str, Any] | None = None
        self.mtime: int | None = None

    def _disk(self) -> dict[str, Any]:
        try:
            self.mtime = self.path.stat().st_mtime_ns
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _load(self) -> dict[str, Any]:
        try:
            changed = self.path.stat().st_mtime_ns != self.mtime
        except OSError:
            changed = False
        if self.data is None or changed:
            self.data = {**(self.data or {}), **self._disk()}
        return self.data

    def get(self, key: str) -> Any:
        with self.lock:
            return self._load().get(key)

    def put(self, key: str, value: Any) -> None:
        with self.lock:
            data = {**self._load(), **self._disk(), key: value}
            self.data = data
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=0))
            tmp.replace(self.path)
            self.mtime = self.path.stat().st_mtime_ns


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

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        json_mode: bool = False,
        max_tokens: int = 1024,
        cache: bool = True,
        max_wait: float = 20.0,
        **extra: Any,
    ) -> dict[str, Any]:
        """One completion; returns {"content": str, "tool_calls": [...]}.

        Rate limits are waited out while the provider asks for at most `max_wait` seconds;
        longer than that raises LLMError so callers can fall back instead of hanging."""
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
            **extra,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = tool_choice or "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        if "gpt-oss" in str(self.model):
            body.setdefault("reasoning_effort", "low")
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        if cache and (hit := _cache.get(key)) is not None:
            return hit if isinstance(hit, dict) else {"content": str(hit), "tool_calls": []}
        for attempt in range(4):
            try:
                res = self.http.post("/chat/completions", json=body)
            except httpx.HTTPError as e:
                raise LLMError(f"{type(e).__name__}: {e}") from e
            if res.status_code == 429 and attempt < 3:
                wait = float(res.headers.get("retry-after", 2**attempt))
                if wait > max_wait:
                    raise LLMError(f"rate limited for {wait:.0f}s")
                time.sleep(wait)
                continue
            if res.status_code == 400 and "reasoning_effort" in body and "reasoning" in res.text:
                body.pop("reasoning_effort")  # provider/model without the knob
                continue
            if res.status_code >= 400:
                raise LLMError(f"{res.status_code}: {res.text[:200]}")
            msg = res.json()["choices"][0]["message"]
            out = {
                "content": msg.get("content") or "",
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"].get("arguments") or "{}",
                        },
                    }
                    for tc in msg.get("tool_calls") or []
                ],
            }
            if cache:
                _cache.put(key, out if out["tool_calls"] else out["content"])
            return out
        raise LLMError("rate limited")

    def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        json_mode: bool = False,
        max_tokens: int = 1024,
        cache: bool = True,
        **extra: Any,
    ) -> str:
        """One completion; returns the message text."""
        out = self.complete(
            messages, json_mode=json_mode, max_tokens=max_tokens, cache=cache, **extra
        )
        return str(out["content"])


def default_adjudicator() -> Adjudicator | None:
    """Stage-4 adjudicator for the configured provider, or None (stage skipped)."""
    if not configured():
        return None
    from halfca.ai.adjudicate import llm_adjudicator

    return llm_adjudicator(LLMClient())
