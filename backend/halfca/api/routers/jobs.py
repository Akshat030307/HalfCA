"""Upload, demo dataset, reset and reconcile: each starts a background job to poll."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from halfca.data.demo_pack import demo_pack_zip
from halfca.ingest.uploads import safe_name
from halfca.models import JobOut

from .. import jobs
from ..state import current

router = APIRouter()

MAX_FILES = 400


@router.post("/upload", response_model=JobOut, status_code=202)
async def upload(files: list[UploadFile] = File(...)) -> dict[str, Any]:  # noqa: B008
    """Drop a folder, a zip or loose files. Missing sources are kept from the current
    dataset, so a single edited CSV is enough to see its effect."""
    if not files:
        raise HTTPException(400, "No files were sent")
    if len(files) > MAX_FILES:
        raise HTTPException(400, f"Too many files ({len(files)}); zip them first")
    work = jobs.upload_dir() / f"{datetime.now(UTC):%Y%m%d-%H%M%S}-upload"
    work.mkdir(parents=True, exist_ok=True)
    paths, used = [], set()
    for i, f in enumerate(files):
        name = safe_name(f.filename or "file")
        if name in used:  # e.g. two folders each with a README
            name = f"{i:03d}-{name}"
        used.add(name)
        target = work / name
        target.write_bytes(await f.read())
        paths.append(target)
    job = jobs.runner.submit("upload", lambda j: jobs.ingest_files(j, paths, work, "upload"))
    return job.as_dict()


@router.post("/upload/demo", response_model=JobOut, status_code=202)
def upload_demo() -> dict[str, Any]:
    """The one-click demo: the demo's own files through the real ingestion path."""
    return jobs.runner.submit("demo", jobs.demo_job).as_dict()


@router.post("/reset", response_model=JobOut, status_code=202)
def reset() -> dict[str, Any]:
    """Regenerate the demo month (seed 2609) and make it the current dataset."""
    return jobs.runner.submit("reset", jobs.reset_job).as_dict()


@router.post("/reconcile", response_model=JobOut, status_code=202)
def reconcile(period: str | None = Query(None, pattern=r"^\d{4}-\d{2}$")) -> dict[str, Any]:
    """Re-run every engine on the stored dataset."""
    ds = current()
    if period and period != ds.meta.get("period"):
        raise HTTPException(404, f"The stored dataset is for {ds.meta.get('period')}, not {period}")
    return jobs.runner.submit("reconcile", jobs.reconcile_job).as_dict()


@router.get("/jobs/{job_id}", response_model=JobOut)
def job(job_id: str) -> dict[str, Any]:
    return jobs.runner.get(job_id).as_dict()


@router.get("/demo-pack.zip")
def demo_pack() -> FileResponse:
    """The demo month as a folder you can download, look at, edit and upload back."""
    path = demo_pack_zip()
    return FileResponse(path, media_type="application/zip", filename=path.name)
