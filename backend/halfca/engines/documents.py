"""Invoice PDFs against the invoice register.

Each document read by ingest/llm_extract.py is tied to its register row by supplier
GSTIN and invoice number (exact first, then normalised). A value the PDF shows that the
register records differently becomes a `document` discrepancy, with both records in the
evidence chain. Pure: frames in, flags and counts out.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from typing import Any

import pandas as pd

from halfca import config, fmt
from halfca.ingest.normalise import normalise_invoice_no

from .common import Flag, chain, counterparty, evidence

# (field, label, how to compare and show)
COMPARE = [
    ("total", "Total", "money"),
    ("taxable_value", "Taxable value", "money"),
    ("igst", "IGST", "money"),
    ("cgst", "CGST", "money"),
    ("sgst", "SGST", "money"),
    ("invoice_date", "Date", "date"),
    ("hsn", "HSN", "text"),
    ("ewb_no", "E-way bill", "text"),
]


def find_row(fields: dict[str, Any], invoices: pd.DataFrame) -> pd.Series | None:
    """The register row a document belongs to, or None (also when it is ambiguous)."""
    gstin, no = fields.get("supplier_gstin"), fields.get("invoice_no")
    if not gstin or not no:
        return None
    same = invoices[invoices.supplier_gstin == gstin]
    exact = same[same.invoice_no.str.upper() == str(no).upper()]
    if len(exact) == 1:
        return exact.iloc[0]
    norm = same[same.invoice_no.map(normalise_invoice_no) == normalise_invoice_no(str(no))]
    return norm.iloc[0] if len(norm) == 1 else None


def _show(kind: str, v: Any) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "blank"
    if kind == "money":
        return fmt.inr(float(v))
    if kind == "date":
        return fmt.day_long(pd.Timestamp(v))
    return str(v)


def _differs(kind: str, reg: Any, doc: Any) -> bool:
    if kind == "money":
        return abs(float(reg if pd.notna(reg) else 0) - float(doc)) > config.DIFF_AMOUNT_TOL
    if kind == "date":
        return pd.isna(reg) or pd.Timestamp(reg).date() != date.fromisoformat(str(doc))
    squash = lambda s: "".join(str(s).split()).upper()  # noqa: E731
    return squash(reg if pd.notna(reg) else "") != squash(doc)


def compare(
    documents: pd.DataFrame | None, invoices: pd.DataFrame
) -> tuple[list[Flag], dict[str, Any]]:
    """Flags for documents that disagree with the register, and per-file outcomes."""
    flags: list[Flag] = []
    counts: Counter[str] = Counter()
    by_file: dict[str, dict[str, Any]] = {}
    models: set[str] = set()
    if documents is None or not len(documents):
        return flags, {"counts": {}, "by_file": {}, "model": None}
    for d in documents.itertuples():
        counts["documents"] += 1
        problems = json.loads(d.problems or "[]")
        if d.status != "read":
            counts[d.status] += 1
            by_file[d.file] = {"outcome": d.status, "detail": problems[0] if problems else None}
            continue
        counts["read"] += 1
        if d.model:
            models.add(str(d.model))
        fields = json.loads(d.fields)
        row = find_row(fields, invoices)
        if row is None:
            counts["not_in_register"] += 1
            by_file[d.file] = {"outcome": "not_in_register", "detail": None}
            continue
        diffs = [
            (k, label, kind, row[k], fields[k])
            for k, label, kind in COMPARE
            if k in fields and k in row.index and _differs(kind, row[k], fields[k])
        ]
        added = bool(getattr(d, "added", False))
        if not diffs:
            counts["added" if added else "agree"] += 1
            by_file[d.file] = {
                "outcome": "added" if added else "agrees",
                "detail": problems[0] if problems else None,
                "invoice_id": row.invoice_id,
            }
            continue
        counts["differ"] += 1
        k0, label0, kind0, reg0, doc0 = diffs[0]
        money = [
            abs(float(r if pd.notna(r) else 0) - float(v))
            for _, _, k, r, v in diffs
            if k == "money"
        ]
        gstin, name = counterparty(row)
        rec = {lab: _show(kind, r) for _, lab, kind, r, _ in diffs}
        exp = {lab: _show(kind, v) for _, lab, kind, _, v in diffs}
        detail = "; ".join(
            f"{lab.lower()} {exp[lab]} on the PDF vs {rec[lab]} in the register" for lab in rec
        )
        by_file[d.file] = {"outcome": "differs", "detail": detail, "invoice_id": row.invoice_id}
        flags.append(
            Flag(
                kind="document",
                invoice_id=row.invoice_id,
                ref=row.invoice_no,
                counterparty=name,
                gstin=gstin,
                title="Invoice PDF disagrees with the books",
                recorded=f"Register: {label0} {_show(kind0, reg0)}",
                expected=f"PDF: {label0} {_show(kind0, doc0)}",
                impact=max(money) if money else 0.0,
                severity="medium",
                evidence=evidence(
                    f"{d.file} shows {detail}.",
                    rec,
                    exp,
                    [
                        chain(
                            "document",
                            d.file,
                            f"Invoice PDF {d.file}",
                            read_by=d.model,
                            **{
                                k: fields[k]
                                for k in ("invoice_no", "invoice_date", "total")
                                if k in fields
                            },
                        ),
                        chain(
                            "invoice",
                            row.invoice_id,
                            f"Invoice {row.invoice_no}",
                            date=row.invoice_date,
                            total=float(row.total),
                        ),
                    ],
                    [
                        "Every value taken from the PDF was checked against the PDF's own "
                        "text; the model never works out a figure.",
                    ],
                ),
            )
        )
    model = ", ".join(sorted(models)) or None
    return flags, {"counts": dict(counts), "by_file": by_file, "model": model}
