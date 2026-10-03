"""Warm the LLM cache in the background so the demo's AI moments are instant.

When the API starts with a model configured, read the demo pack's invoice PDFs and ask
the copilot's suggested questions once. Calls are cached by request hash, so this spends
tokens only the first time (about four minutes on Groq's free tier); afterwards each of
those calls is a cache hit. Set HALFCA_WARM=0 to skip.
"""

from __future__ import annotations

import os
import threading
import time
import traceback

from halfca import tools
from halfca.ai import copilot, llm

PATIENCE_S = 90.0  # the warm-up can wait out rate limits; a live user cannot


def warm() -> None:
    from halfca.data.demo_pack import FOLDER, demo_pack_zip
    from halfca.ingest.llm_extract import read_document

    started = time.monotonic()
    try:
        tools._ds()
        client = llm.LLMClient()
        pdfs = sorted((demo_pack_zip().parent / FOLDER / "invoices").glob("*.pdf"))
        read = sum(read_document(p, client).status == "read" for p in pdfs)
        answered = 0
        for q in copilot.SUGGESTIONS:
            for ev in copilot.answer(q, pace=False, patience=PATIENCE_S):
                answered += ev.type == "done" and ev.data["mode"] == "llm"
        print(
            f"[warm] {read}/{len(pdfs)} PDFs read, {answered}/{len(copilot.SUGGESTIONS)} "
            f"copilot answers by {llm.model_name()} in {time.monotonic() - started:.0f}s",
            flush=True,
        )
    except Exception:  # never take the API down for a warm-up
        traceback.print_exc()


def start() -> threading.Thread | None:
    if os.environ.get("HALFCA_WARM", "1") == "0" or not llm.configured():
        return None
    t = threading.Thread(target=warm, name="llm-warm", daemon=True)
    t.start()
    return t
