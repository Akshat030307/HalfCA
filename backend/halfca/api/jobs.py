"""Background jobs: upload, demo dataset, reset, reconcile. One at a time.

Each job walks the five steps the Upload screen shows and reports real progress:
  extract → gstin → normalise → road → match
The frontend polls GET /api/jobs/{id}.
"""

from __future__ import annotations

import json
import shutil
import threading
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException

from halfca import config, store
from halfca.data import build
from halfca.ingest.csv_loader import read_reference, read_sources
from halfca.ingest.uploads import UploadError, collect

STEPS = [
    ("extract", "Reading the files"),
    ("gstin", "Validating GSTINs (state · PAN · check digit)"),
    ("normalise", "Normalising invoice numbers"),
    ("road", "Linking e-way bills to toll crossings"),
    ("match", "Matching across four threads"),
]
SOURCE_TABLES = {
    "invoices": ["invoices"],
    "bank": ["bank"],
    "ledger": ["ledger"],
    "ims": ["ims"],
    "eway": ["eway_bills", "toll_crossings"],
}
REFERENCE_TABLES = ["counterparties", "upstream_invoices", "hsn_rates"]
KEEP_UPLOADS = 5


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Job:
    kind: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "running"
    steps: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"key": k, "label": label, "state": "pending", "detail": None} for k, label in STEPS
        ]
    )
    files: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    kpis: dict[str, Any] | None = None
    started_at: str = field(default_factory=_now)
    finished_at: str | None = None

    def step(
        self, key: str, state: str, detail: str | None = None, label: str | None = None
    ) -> None:
        for s in self.steps:
            if s["key"] == key:
                s["state"] = state
                if detail is not None:
                    s["detail"] = detail
                if label is not None:
                    s["label"] = label

    def progress(self, key: str, state: str, detail: str | None) -> None:
        self.step(key, state, detail)

    def as_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "steps": self.steps,
            "files": self.files,
            "error": self.error,
            "kpis": self.kpis,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


class Runner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self._active: str | None = None
        self.latest: str | None = None

    def get(self, job_id: str) -> Job:
        if job_id == "latest" and self.latest:
            job_id = self.latest
        if job_id not in self._jobs:
            raise HTTPException(404, "No such job")
        return self._jobs[job_id]

    def submit(self, kind: str, work: Callable[[Job], None]) -> Job:
        with self._lock:
            if self._active and self._jobs[self._active].status == "running":
                raise HTTPException(409, "Another reconciliation is running; try again shortly")
            job = Job(kind)
            self._jobs[job.job_id] = job
            self._active = self.latest = job.job_id
            for old in list(self._jobs)[:-20]:
                self._jobs.pop(old, None)

        def target() -> None:
            try:
                work(job)
                job.status = "done"
            except UploadError as e:
                job.status, job.error = "error", str(e)
            except Exception as e:  # surface, never crash the server
                traceback.print_exc()
                job.status, job.error = "error", f"{type(e).__name__}: {e}"
            finally:
                for s in job.steps:
                    if s["state"] == "running":
                        s["state"] = "error" if job.status == "error" else "done"
                    elif s["state"] == "pending" and job.status == "done":
                        s["state"] = "skipped"
                job.finished_at = _now()

        threading.Thread(target=target, name=f"job-{job.job_id}", daemon=True).start()
        return job


runner = Runner()


def _kpis(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "reconciled",
        "matched",
        "discrepancies",
        "duplicates",
        "unmatched",
        "exposure",
        "clean_match_pct",
    )
    return {k: summary[k] for k in keys}


# ── job bodies ───────────────────────────────────────────────────────────────


def ingest_files(job: Job, paths: list[Path], workdir: Path, scenario: str) -> None:
    """Real ingestion: sort the files, parse them, fill gaps from the current dataset,
    then reconcile and swap the database."""
    job.step("extract", "running")
    found = collect(paths, workdir)
    try:
        frames = read_sources(found.sources.values())
    except (KeyError, ValueError) as e:
        raise UploadError(f"Could not read the files: {e}") from e

    base: dict[str, pd.DataFrame] = {}
    meta: dict[str, Any] = {}
    if config.DB_PATH.is_file():
        base = store.load_prefixed("raw_")
        meta = store.meta()
    for kind, tables in SOURCE_TABLES.items():
        f = found.sources.get(kind)
        if f is not None:
            n = len(frames[tables[0]])
            job.files.append({"name": f.name, "kind": kind, "records": n, "note": None})
            continue
        if all(t in base for t in tables):
            for t in tables:
                frames[t] = base[t]
            job.files.append(
                {
                    "name": f"({kind})",
                    "kind": kind,
                    "records": len(base[tables[0]]),
                    "note": "Not uploaded; kept from the current dataset",
                }
            )
        else:
            raise UploadError(f"No {kind} file was uploaded and there is none to fall back on")
    for t in REFERENCE_TABLES:
        if t in base:
            frames[t] = base[t]
    if any(t not in frames for t in REFERENCE_TABLES):
        frames.update(read_reference(config.DATA_DIR / "reference"))
    for d in found.documents:
        job.files.append(
            {
                "name": d.name,
                "kind": "document",
                "records": None,
                "note": "Invoice document; the invoice register carries its data",
            }
        )
    for name in found.ignored:
        job.files.append(
            {
                "name": name,
                "kind": None,
                "records": None,
                "note": found.notes.get(name, "Ignored: not a recognised source"),
            }
        )

    n_inv = len(frames["invoices"])
    docs = f" and {len(found.documents)} invoice documents" if found.documents else ""
    job.step(
        "extract",
        "done",
        f"{len(found.sources)} of 5 sources uploaded{docs}",
        label=f"Reading {n_inv} invoices{docs}",
    )
    if not meta:
        raise UploadError("Generate the demo dataset first (it provides the reference data)")
    meta = {
        **meta,
        "scenario": scenario,
        "uploaded_files": sorted(p.name for p in paths),
        "uploaded_at": _now(),
    }
    summary = build.reconcile_and_save(frames, meta, config.DB_PATH, progress=job.progress)
    job.step(
        "gstin",
        "done",
        label=f"Validating {summary['gstins']['checked']} GSTINs (state · PAN · check digit)",
    )
    job.kpis = _kpis(summary)


def upload_dir() -> Path:
    root = config.DATA_DIR / "uploads"
    root.mkdir(parents=True, exist_ok=True)
    for old in sorted(root.iterdir())[:-KEEP_UPLOADS]:
        shutil.rmtree(old, ignore_errors=True)
    return root


def demo_job(job: Job) -> None:
    """The one-click demo: ingest the demo's own source files through the real path."""
    src = config.DATA_DIR / "sources"
    if not src.is_dir():
        raise UploadError("The demo files are missing; run a reset first")
    work = upload_dir() / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-demo-{job.job_id}"
    work.mkdir(parents=True)
    ingest_files(job, sorted(src.iterdir()), work, scenario="demo")


def reset_job(job: Job) -> None:
    """Regenerate the demo month from scratch (seed 2609)."""
    job.step("extract", "running", "Generating the demo month")
    build.run("demo", progress=job.progress)
    s = store.table("res_summary")
    summary = {k: json.loads(v) for k, v in zip(s.key, s.value, strict=True)}
    job.step(
        "extract",
        "done",
        "Demo month generated",
        label=f"Generating {summary['reconciled']} invoices",
    )
    job.kpis = _kpis(summary)


def reconcile_job(job: Job) -> None:
    job.step("extract", "done", "Using the stored dataset", label="Reading the stored dataset")
    summary = build.rereconcile(progress=job.progress)
    job.kpis = _kpis(summary)
