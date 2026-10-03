"""FastAPI app. Every route lives under /api."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from halfca import __version__, config
from halfca.ai import llm, warm
from halfca.api.routers import copilot, credit, dataset, goods, ims, jobs, overview


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    warm.start()  # background: cache the demo's PDF reads and copilot answers
    yield


app = FastAPI(
    title="Half CA",
    version=__version__,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "version": __version__,
        "data_ready": config.DB_PATH.is_file(),
        "llm": config.LLM_PROVIDER or None,
        "llm_model": llm.model_name(),
    }


for module in (dataset, overview, goods, credit, ims, jobs, copilot):
    app.include_router(module.router, prefix="/api")
