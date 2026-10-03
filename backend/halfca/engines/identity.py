"""Identity checks at ingestion: every GSTIN on an invoice must be well-formed with a
valid check digit (state · PAN · entity · Z · checksum)."""

from __future__ import annotations

import pandas as pd

from halfca.ingest.gstin import validate

from .common import Flag, chain, evidence


def validate_gstins(invoices: pd.DataFrame) -> tuple[list[Flag], dict[str, int]]:
    flags: list[Flag] = []
    seen: dict[str, bool] = {}
    for r in invoices.itertuples():
        for role, gstin, name in (
            ("supplier", r.supplier_gstin, r.supplier_name),
            ("buyer", r.buyer_gstin, r.buyer_name),
        ):
            g = str(gstin or "")
            if g not in seen:
                seen[g] = validate(g).valid
            if seen[g]:
                continue
            check = validate(g)
            flags.append(
                Flag(
                    "invalid_gstin",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    g or None,
                    f"Invalid {role} GSTIN",
                    recorded=g or "(blank)",
                    expected="15 characters with a valid check digit",
                    impact=0.0,
                    severity="medium",
                    evidence=evidence(
                        f"The {role} GSTIN on {r.invoice_no} fails validation: {check.reason}.",
                        {"gstin": g},
                        {},
                        [chain("invoice", r.invoice_id, f"Invoice {r.invoice_no}", gstin=g)],
                    ),
                )
            )
    valid = sum(seen.values())
    return flags, {"checked": len(seen), "valid": valid, "invalid": len(seen) - valid}
