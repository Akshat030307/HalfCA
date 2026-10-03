"""Read uploaded invoice documents and tie them to the invoice register.

A read PDF that is in the register is linked to it (engines/documents.py compares the two
on every reconciliation). A read PDF that is not in the register, but shows everything an
invoice row needs and names you as buyer or seller, is added to the register.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from halfca import config
from halfca.ai import llm
from halfca.engines.documents import find_row

from .llm_extract import DocRead, read_document

NEEDED = (
    "invoice_no",
    "invoice_date",
    "supplier_gstin",
    "buyer_gstin",
    "taxable_value",
    "rate",
    "total",
)


def read_all(
    paths: list[tuple[Path, str]], say: Callable[[str], None] | None = None
) -> list[DocRead]:
    """Read each (path, shown name), within the per-upload cap and time budget."""
    client = llm.LLMClient() if llm.configured() else None
    started = time.monotonic()
    out: list[DocRead] = []
    for i, (path, name) in enumerate(paths):
        over = i >= config.EXTRACT_MAX_DOCS or time.monotonic() - started > config.EXTRACT_BUDGET_S
        if over and client is not None:
            out.append(DocRead(name, "unread", problems=["Over this upload's AI reading budget"]))
            continue
        if say and client is not None:
            say(f"Reading invoice PDFs with AI · {i + 1} of {len(paths)}")
        out.append(read_document(path, client, name))
    return out


def _row(d: DocRead, n: int, user: str, names: dict[str, str]) -> dict[str, Any]:
    f = d.fields
    inward = f["buyer_gstin"] == user
    qty = f.get("qty")
    return {
        "invoice_id": f"doc{n:03d}",
        "invoice_no": f["invoice_no"],
        "invoice_date": pd.Timestamp(f["invoice_date"]),
        "direction": "inward" if inward else "outward",
        "supplier_gstin": f["supplier_gstin"],
        "supplier_name": f.get("supplier_name") or names.get(f["supplier_gstin"], ""),
        "supplier_state": f["supplier_gstin"][:2],
        "buyer_gstin": f["buyer_gstin"],
        "buyer_name": f.get("buyer_name") or names.get(f["buyer_gstin"], ""),
        "place_of_supply": f.get("place_of_supply") or f["buyer_gstin"][:2],
        "hsn": f.get("hsn") or "",
        "description": f.get("description") or "",
        "qty": qty,
        "unit": f.get("unit") or "",
        "unit_price": f.get("unit_price") or (round(f["taxable_value"] / qty, 2) if qty else None),
        "taxable_value": f["taxable_value"],
        "rate": f["rate"],
        "cgst": f.get("cgst", 0.0),
        "sgst": f.get("sgst", 0.0),
        "igst": f.get("igst", 0.0),
        "total": f["total"],
        "ewb_no": f.get("ewb_no"),
    }


def add_missing(
    docs: list[DocRead], invoices: pd.DataFrame, user: str, names: dict[str, str]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(register with any new invoices appended, documents table)."""
    rows, new = [], []
    for d in docs:
        row = d.as_row()
        row["added"] = False
        if d.status == "read" and find_row(d.fields, invoices) is None:
            missing = [k for k in NEEDED if d.fields.get(k) in (None, "")]
            ours = user in (d.fields.get("buyer_gstin"), d.fields.get("supplier_gstin"))
            if missing or not ours:
                why = (
                    f"not in the register and the PDF lacks {', '.join(missing)}"
                    if missing
                    else "not in the register and not addressed to you"
                )
                d.status = "needs_review"
                d.problems.insert(0, why[0].upper() + why[1:])
                row = {**d.as_row(), "added": False}
            else:
                new.append(_row(d, len(new) + 1, user, names))
                row["added"] = True
        rows.append(row)
    if new:
        invoices = pd.concat([invoices, pd.DataFrame(new)], ignore_index=True)
    cols = [
        "file",
        "status",
        "invoice_no",
        "supplier_gstin",
        "fields",
        "problems",
        "model",
        "added",
    ]
    return invoices, pd.DataFrame(rows, columns=cols)
