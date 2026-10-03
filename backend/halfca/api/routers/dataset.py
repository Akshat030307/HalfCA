from __future__ import annotations

from fastapi import APIRouter, HTTPException

from halfca import config, store
from halfca.data.write import source_names
from halfca.models import DatasetInfo, SourceFile

router = APIRouter()

# Which raw table carries each uploaded file's records.
_SOURCE_TABLE = {
    "invoices": "raw_invoices",
    "bank": "raw_bank",
    "ledger": "raw_ledger",
    "ims": "raw_ims",
    "eway": "raw_eway_bills",
}


@router.get("/dataset", response_model=DatasetInfo)
def dataset() -> DatasetInfo:
    if not config.DB_PATH.is_file():
        raise HTTPException(status_code=503, detail="Demo data has not been generated yet")
    meta = store.meta()
    with store.connect() as con:
        names = [r[0] for r in con.execute("SHOW TABLES").fetchall() if r[0].startswith("raw_")]
        counts = {
            n.removeprefix("raw_"): con.execute(f'SELECT count(*) FROM "{n}"').fetchone()[0]
            for n in names
        }
    files = source_names(str(meta["period"]))
    return DatasetInfo(
        scenario=str(meta["scenario"]),
        seed=int(meta["seed"]),  # type: ignore[arg-type]
        period=str(meta["period"]),
        as_of=str(meta["as_of"]),
        user_gstin=str(meta["user_gstin"]),
        user_name=str(meta["user_name"]),
        sources=[
            SourceFile(kind=k, filename=files[k], records=counts.get(t.removeprefix("raw_"), 0))
            for k, t in _SOURCE_TABLE.items()
        ],
        counts=counts,
    )
