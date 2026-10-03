"""FastAPI app. Every route lives under /api."""

from __future__ import annotations

from fastapi import FastAPI

from halfca import __version__, config

app = FastAPI(
    title="Half CA", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
)


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "version": __version__,
        "data_ready": config.DB_PATH.is_file(),
        "llm": config.LLM_PROVIDER or None,
    }
