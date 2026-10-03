"""Copilot: a server-sent event stream of tool calls, answer words and evidence chips."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from halfca.ai import copilot
from halfca.models import CopilotIn, CopilotInfo

router = APIRouter()


def _sse(events: Iterator[copilot.Event]) -> Iterator[str]:
    for ev in events:
        yield f"event: {ev.type}\ndata: {json.dumps(ev.data, ensure_ascii=False)}\n\n"


@router.post("/copilot")
def ask(body: CopilotIn) -> StreamingResponse:
    """Events: tool → tool_done (per call) → token (per word) → evidence → done."""
    history = [h.model_dump() for h in body.history]
    return StreamingResponse(
        _sse(copilot.answer(body.message, history)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/copilot", response_model=CopilotInfo)
def info() -> dict[str, Any]:
    """The tools, the model (or none) and suggested questions."""
    return copilot.info()
