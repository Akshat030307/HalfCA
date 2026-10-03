from __future__ import annotations

from fastapi import APIRouter

from halfca.data.write import source_names
from halfca.models import DatasetInfo

from ..state import Dataset, current

router = APIRouter()

# Which raw table carries each uploaded file's records.
_SOURCE_TABLE = {
    "invoices": "invoices",
    "bank": "bank",
    "ledger": "ledger",
    "ims": "ims",
    "eway": "eway_bills",
}


def dataset_info(ds: Dataset) -> dict:
    meta = ds.meta
    files = source_names(str(meta["period"]))
    counts = {k: len(v) for k, v in ds.raw.items()}
    seed = meta.get("seed")
    return {
        "dataset_id": ds.dataset_id,
        "scenario": str(meta.get("scenario")),
        "seed": int(seed) if seed is not None else None,
        "period": str(meta["period"]),
        "as_of": str(meta["as_of"]),
        "user_gstin": str(meta["user_gstin"]),
        "user_name": str(meta["user_name"]),
        "sources": [
            {"kind": k, "filename": files[k], "records": counts.get(t, 0)}
            for k, t in _SOURCE_TABLE.items()
        ],
        "counts": counts,
        "uploaded_files": list(meta.get("uploaded_files") or []),
        "documents": ds.summary.get("documents", {}).get("counts", {}),
    }


@router.get("/dataset", response_model=DatasetInfo)
def dataset() -> dict:
    return dataset_info(current())
