"""IMS Autopilot and Liability."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter

from halfca import config, fmt
from halfca.models import ApproveIn, ApproveOut, ImsOut, LiabilityOut

from ..state import current, ims_approvals, save_ims_approvals
from ..views import plain

router = APIRouter()

ORDER = {"Reject": 0, "Pending": 1, "Accept": 2}


def gstr2b_date(period: str) -> str:
    y, m = (int(x) for x in period.split("-"))
    y2, m2 = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(y2, m2, config.GSTR2B_DAY).isoformat()


@router.get("/ims", response_model=ImsOut)
def ims() -> dict[str, Any]:
    ds = current()
    approved, at = ims_approvals(ds.dataset_id)
    df = ds.res["ims"].copy()
    df["_o"] = df.decision.map(ORDER)
    df = df.sort_values(["_o", "itc"], ascending=[True, False])
    records = [
        {
            "ims_id": r.ims_id,
            "invoice_id": plain(r.invoice_id),
            "supplier_gstin": r.supplier_gstin,
            "supplier_name": r.supplier_name,
            "invoice_no": r.invoice_no,
            "invoice_date": plain(r.invoice_date),
            "taxable_value": float(r.taxable_value),
            "itc": float(r.itc),
            "decision": r.decision,
            "rule": r.rule,
            "reason": r.reason,
            "taint": float(r.taint),
            "approved": r.ims_id in approved,
        }
        for r in df.itertuples()
    ]
    counts = df.decision.value_counts().to_dict()
    return {
        "records": records,
        "counts": {
            "records": len(df),
            "accept": counts.get("Accept", 0),
            "reject": counts.get("Reject", 0),
            "pending": counts.get("Pending", 0),
            "approved": len(approved),
        },
        "gstr2b_date": gstr2b_date(str(ds.meta["period"])),
        "approved_at": at,
    }


@router.post("/ims/approve", response_model=ApproveOut)
def approve(body: ApproveIn | None = None) -> dict[str, Any]:
    """Mark Autopilot's Accepts as actioned (in the demo, nothing is sent to the GST portal)."""
    ds = current()
    df = ds.res["ims"]
    accepts = set(df[df.decision == "Accept"].ims_id)
    chosen = accepts if not body or body.ims_ids is None else accepts & set(body.ims_ids)
    approved, _ = ims_approvals(ds.dataset_id)
    approved |= chosen
    at = save_ims_approvals(ds.dataset_id, approved)
    counts = df.decision.value_counts().to_dict()
    rej, pend = counts.get("Reject", 0), counts.get("Pending", 0)
    return {
        "approved": len(approved),
        "rejected": rej,
        "pending": pend,
        "approved_at": at,
        "message": f"{len(approved)} accepted on IMS · {rej} rejected · {pend} kept pending",
    }


@router.get("/liability", response_model=LiabilityOut)
def liability() -> dict[str, Any]:
    ds = current()
    b = ds.res["benford"]
    direct = set(ds.raw["invoices"].query("direction == 'inward'").supplier_gstin)
    bad = b[b.nonconforming & b.gstin.isin(direct)].sort_values("mad", ascending=False)
    return {
        "summary": ds.summary["liability"],
        "waterfall": ds.res["liability_waterfall"].to_dict("records"),
        "heads": ds.res["liability_heads"].to_dict("records"),
        "benford_focus": bad.gstin.iloc[0] if len(bad) else None,
    }


def exposure_line(ds_summary: dict[str, Any]) -> str:
    """'Exposure caught before filing ₹5.3 lakh' style line for templates."""
    return f"Exposure caught before filing {fmt.lakh(ds_summary['exposure'])}"
