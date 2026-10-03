"""IMS Autopilot: a deterministic decision per supplier record; language only for the reason.

Rules, first match wins:
  not matched to your books   → Pending
  tax or amount wrong         → Reject
  physical trail failed       → Reject
  supplier taint ≥ 0.7        → Pending
  otherwise                   → Accept

The reason here is a template built from the evidence. With an LLM configured,
ai/llm.py may rephrase it; the decision never changes.
"""

from __future__ import annotations

import json

import pandas as pd

from halfca import config, fmt
from halfca.engines.common import Flag


def _tax_reason(f: Flag) -> str:
    if f.kind == "tax_rate":
        rec = f.recorded.split(" · ")[0] if f.recorded else "?"
        exp = f.expected.split(" · ")[0] if f.expected else "?"
        if "Abolished" in f.title:
            return f"Charged abolished {rec} slab · expected {exp}"
        return f"Charged {rec} · expected {exp}"
    if f.kind == "tax_head":
        return f.title
    return "Tax does not add up"


def _road_reason(f: Flag, physical: dict) -> str:
    if f.kind == "paper_only":
        return "Goods not evidenced: 0 toll crossings"
    if f.kind == "impossible_journey":
        return (
            f"Impossible journey: {physical['distance_km']:g} km in "
            f"{fmt.duration(physical['trip_minutes'])}"
        )
    if f.kind == "recycled_ewb":
        source = physical.get("ewb_doc_no")
        if source and source != f.ref:
            return f"Recycled e-way bill (trip used by {source})"
        others = (physical.get("recycled_with") or "").replace(",", ", ")
        return f"Recycled e-way bill (trip reused by {others})"
    return "No e-way bill for an inter-state consignment"


def decide(
    ims: pd.DataFrame,
    ims_links: pd.DataFrame,
    booked: set[str],
    flags_by_invoice: dict[str, list[Flag]],
    physical: pd.DataFrame,
    taint_risk: dict[str, float],
    invoices: pd.DataFrame,
) -> pd.DataFrame:
    inv = invoices.set_index("invoice_id", drop=False)
    link = dict(zip(ims_links.ims_id, ims_links.invoice_id, strict=True)) if len(ims_links) else {}
    phys = {r["invoice_id"]: r for r in physical.to_dict("records")} if len(physical) else {}
    rows = []
    for rec in ims.itertuples():
        iid = link.get(rec.ims_id)
        itc = float(rec.cgst + rec.sgst + rec.igst)
        flags = flags_by_invoice.get(iid, []) if iid else []
        tax_flags = [f for f in flags if f.kind in ("tax_rate", "tax_head", "tax_arith")]
        road_flags = [
            f
            for f in flags
            if f.kind in ("missing_ewb", "paper_only", "impossible_journey", "recycled_ewb")
        ]
        risk = taint_risk.get(rec.supplier_gstin, 0.0)
        if iid is None or iid not in booked:
            decision, rule, reason = "Pending", "not_matched", "Not in your books yet"
        elif tax_flags or abs(float(inv.loc[iid].total) - float(rec.total)) > 1:
            decision, rule = "Reject", "tax_wrong"
            reason = (
                _tax_reason(tax_flags[0])
                if tax_flags
                else (
                    f"Supplier filed {fmt.inr(rec.total)}; "
                    f"your invoice says {fmt.inr(inv.loc[iid].total)}"
                )
            )
        elif road_flags:
            decision, rule = "Reject", "road_failed"
            reason = _road_reason(road_flags[0], phys.get(iid, {}))
        elif risk >= config.TAINT_AT_RISK:
            decision, rule = "Pending", "supplier_taint"
            reason = f"Supplier fed by a circular-trading ring (taint {risk:.2f})"
        else:
            decision, rule = "Accept", "clean"
            verified = phys.get(iid, {}).get("verdict") == "verified"
            reason = (
                "Matches your books · goods seen on the road" if verified else "Matches your books"
            )
        rows.append(
            {
                "ims_id": rec.ims_id,
                "invoice_id": iid,
                "supplier_gstin": rec.supplier_gstin,
                "supplier_name": rec.supplier_name,
                "invoice_no": rec.invoice_no,
                "invoice_date": rec.invoice_date,
                "taxable_value": float(rec.taxable_value),
                "igst": float(rec.igst),
                "cgst": float(rec.cgst),
                "sgst": float(rec.sgst),
                "itc": round(itc, 2),
                "decision": decision,
                "rule": rule,
                "reason": reason,
                "taint": round(risk, 3),
                "flag_ids": json.dumps([f.flag_id for f in tax_flags + road_flags]),
            }
        )
    return pd.DataFrame(rows)
