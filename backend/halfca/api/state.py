"""The current dataset, held in memory and reloaded when the database file changes.

Uploads and resets replace data/halfca.duckdb atomically (store.save); the next
request notices the new inode/mtime and reloads. No connection stays open between
requests, so a swap never fights a lock.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import cached_property
from typing import Any

import pandas as pd
from fastapi import HTTPException

from halfca import config, store
from halfca.engines.common import KINDS


@dataclass
class Dataset:
    meta: dict[str, Any]
    raw: dict[str, pd.DataFrame]
    res: dict[str, pd.DataFrame]
    stamp: tuple[int, int]
    loaded_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def dataset_id(self) -> str:
        return str(self.meta.get("dataset_id") or f"{self.stamp[0]}-{self.stamp[1]}")

    @cached_property
    def summary(self) -> dict[str, Any]:
        s = self.res["summary"]
        return {k: json.loads(v) for k, v in zip(s.key, s.value, strict=True)}

    @cached_property
    def flags(self) -> pd.DataFrame:
        return self.res["flags"]

    @cached_property
    def invoices(self) -> pd.DataFrame:
        return self.raw["invoices"].set_index("invoice_id", drop=False)

    @cached_property
    def status(self) -> pd.DataFrame:
        return self.res["invoices"].set_index("invoice_id", drop=False)

    @cached_property
    def names(self) -> dict[str, str]:
        cp = self.raw["counterparties"]
        out = dict(zip(cp.gstin, cp.name, strict=True))
        inv = self.raw["invoices"]
        out.update(dict(zip(inv.supplier_gstin, inv.supplier_name, strict=True)))
        out.update(dict(zip(inv.buyer_gstin, inv.buyer_name, strict=True)))
        return out

    def flags_for(self, invoice_id: str | None = None, ref: str | None = None) -> pd.DataFrame:
        f = self.flags
        if invoice_id is not None:
            return f[f.invoice_id == invoice_id]
        return f[f.ref == ref]

    def find_invoice(self, key: str) -> pd.Series:
        """By invoice_id, or by invoice number when that is unique."""
        if key in self.invoices.index:
            return self.invoices.loc[key]
        rows = self.invoices[self.invoices.invoice_no == key]
        if len(rows) == 1:
            return rows.iloc[0]
        raise HTTPException(404, f"No single invoice matches {key!r}")


_lock = threading.Lock()
_current: Dataset | None = None


def _stamp() -> tuple[int, int] | None:
    try:
        st = config.DB_PATH.stat()
    except FileNotFoundError:
        return None
    return st.st_ino, st.st_mtime_ns


def current() -> Dataset:
    global _current
    stamp = _stamp()
    if stamp is None:
        raise HTTPException(503, "No dataset yet. Run `make data` or upload files.")
    with _lock:
        if _current is None or _current.stamp != stamp:
            tables_raw = store.load_prefixed("raw_")
            tables_res = store.load_prefixed("res_")
            if "summary" not in tables_res:
                raise HTTPException(503, "The dataset has not been reconciled yet.")
            _current = Dataset(store.meta(), tables_raw, tables_res, stamp)
        return _current


def kind_label(kind: str) -> str:
    return KINDS.get(kind, (kind, kind))[1]


# ── small mutable state that is not part of a reconciliation (IMS approvals) ──

_state_lock = threading.Lock()


def _state_path():  # noqa: ANN202 (resolved per call so tests can move DATA_DIR)
    return config.DATA_DIR / "state.json"


def _read_state() -> dict[str, Any]:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def ims_approvals(dataset_id: str) -> tuple[set[str], str | None]:
    s = _read_state().get("ims", {})
    if s.get("dataset_id") != dataset_id:
        return set(), None
    return set(s.get("approved", [])), s.get("approved_at")


def save_ims_approvals(dataset_id: str, approved: set[str]) -> str:
    at = datetime.now(UTC).isoformat()
    with _state_lock:
        data = _read_state()
        data["ims"] = {"dataset_id": dataset_id, "approved": sorted(approved), "approved_at": at}
        path = _state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(path)
    return at
