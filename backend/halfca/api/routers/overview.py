"""Summary, matching funnel, discrepancies and the four threads of one invoice."""

from __future__ import annotations

from fastapi import APIRouter, Query

from halfca.engines.common import DISCREPANCY_KINDS, KINDS
from halfca.models import DiscrepancyList, Funnel, InvoiceDetail, Summary

from ..state import current, ims_approvals
from ..views import flags_out, llm_info, plain, record
from .dataset import dataset_info

router = APIRouter()

DONUT = [
    ("matched", "Matched"),
    ("discrepant", "Discrepant"),
    ("duplicate", "Duplicate"),
    ("unmatched", "Unmatched"),
]


def thread_examples(ds) -> dict[str, str | None]:  # noqa: ANN001
    """Two invoices for the Overview's four-threads card, chosen by rule: the biggest one
    that clears all four threads (showcase suppliers first), and the biggest one that
    clears the paperwork but fails the road (paper-only first)."""
    inv = ds.res["invoices"]
    tags = ds.raw["counterparties"].set_index("gstin").tags.fillna("")
    showcase = {g for g, t in tags.items() if "showcase" in str(t)}
    clean = inv[
        (inv.status == "matched")
        & (inv.payments > 0)
        & (inv.ims_decision == "Accept")
        & (inv.physical == "verified")
    ]
    pick = clean[clean.counterparty_gstin.isin(showcase)]
    pick = pick if len(pick) else clean
    failed = inv[
        (inv.status == "matched")
        & inv.physical.isin(["paper_only", "impossible_journey", "recycled_ewb", "missing_ewb"])
    ]
    failed = failed.assign(_o=(failed.physical != "paper_only").astype(int))
    failed = failed.sort_values(["_o", "total"], ascending=[True, False])
    return {
        "all_clear": pick.sort_values("total", ascending=False).invoice_id.iloc[0]
        if len(pick)
        else None,
        "road_fail": failed.invoice_id.iloc[0] if len(failed) else None,
    }


@router.get("/summary", response_model=Summary)
def summary() -> dict:
    ds = current()
    s = ds.summary
    status = ds.res["invoices"].status.value_counts().to_dict()
    types = [
        {"kind": k, "label": KINDS[k][1], "count": int(s["discrepancy_types"].get(k, 0))}
        for k in ("amount", "tax_rate", "invoice_id", "date", "tax_head", "tax_arith", "document")
        if k not in ("tax_arith", "document") or s["discrepancy_types"].get(k, 0)
    ]
    types.append({"kind": "duplicate", "label": "Duplicates", "count": int(s["duplicates"])})
    approved, _ = ims_approvals(ds.dataset_id)
    return {
        "dataset": dataset_info(ds),
        "kpis": {
            k: s[k]
            for k in (
                "reconciled",
                "matched",
                "discrepancies",
                "duplicates",
                "unmatched",
                "exposure",
                "clean_match_pct",
            )
        },
        "donut": [{"key": k, "label": label, "value": int(status.get(k, 0))} for k, label in DONUT],
        "discrepancy_types": types,
        "tax_errors": s["tax_errors"],
        "physical": s["physical"],
        "ims": {**s["ims"], "approved": len(approved)},
        "liability": s["liability"],
        "rings": s["rings"],
        "at_risk_suppliers": s["at_risk_suppliers"],
        "gaps": s["gaps"],
        "anomalies": s["anomalies"],
        "gstins": s.get("gstins", {}),
        "llm": llm_info(ds),
        "examples": thread_examples(ds),
    }


@router.get("/funnel", response_model=Funnel)
def funnel() -> dict:
    ds = current()
    paid = set(ds.res["payment_links"].invoice_id) if len(ds.res["payment_links"]) else set()
    unmatched = []
    for r in ds.res["unmatched"].itertuples():
        unmatched.append(
            {
                "invoice_id": r.invoice_id,
                "invoice_no": r.invoice_no,
                "invoice_date": plain(r.invoice_date),
                "direction": r.direction,
                "counterparty": r.supplier_name if r.direction == "inward" else r.buyer_name,
                "total": float(r.total),
                "paid": r.invoice_id in paid,
            }
        )
    return {
        "stages": [record(r) for _, r in ds.res["funnel"].iterrows()],
        "unmatched": unmatched,
        "llm": llm_info(ds),
    }


@router.get("/discrepancies", response_model=DiscrepancyList)
def discrepancies(
    type: str | None = Query(None, description="a flag kind, e.g. tax_rate, or 'all'"),  # noqa: A002
    category: str | None = Query(None, description="discrepancy, duplicate, gap, physical, …"),
) -> dict:
    """Default: discrepancies and duplicates on reconciled invoices (the 38 + 7)."""
    ds = current()
    f = ds.flags
    status = ds.status.status
    if type and type != "all":
        f = f[f.kind == type]
    elif category:
        f = f[f.category == category]
    elif type != "all":
        on_paired = f.invoice_id.map(lambda i: status.get(i) in ("discrepant", "duplicate"))
        f = f[f.kind.isin(DISCREPANCY_KINDS + ["duplicate", "near_duplicate"]) & on_paired]
    f = f.sort_values("impact", ascending=False)
    counts = f.kind.value_counts().to_dict()
    return {
        "counts": [
            {"kind": k, "label": KINDS.get(k, (k, k))[1], "count": int(n)}
            for k, n in counts.items()
        ],
        "items": flags_out(f),
    }


@router.get("/invoices/{key:path}", response_model=InvoiceDetail)
def invoice_detail(key: str) -> dict:
    """All four threads of one invoice: the invoice, books, bank, IMS and the road.
    `key` is an invoice_id or a unique invoice number (slashes allowed: /invoices/MB/0877)."""
    ds = current()
    inv = ds.find_invoice(key)
    iid = inv.invoice_id
    st = ds.status.loc[iid]
    match = ds.res["matches"]
    m = match[match.invoice_id == iid]
    voucher = None
    if len(m):
        led = ds.raw["ledger"]
        v = led[led.voucher_no == m.iloc[0].voucher_no]
        voucher = record(v.iloc[0]) if len(v) else None
    links = ds.res["payment_links"]
    txns = links[links.invoice_id == iid].txn_id if len(links) else []
    bank = ds.raw["bank"]
    payments = [record(r) for _, r in bank[bank.txn_id.isin(list(txns))].iterrows()]
    ims = None
    il = ds.res["ims_links"]
    hit = il[il.invoice_id == iid] if len(il) else il
    if len(hit):
        dec = ds.res["ims"].set_index("ims_id").loc[hit.iloc[0].ims_id]
        ims = record(dec)
    phys = ds.res["physical"]
    p = phys[phys.invoice_id == iid] if len(phys) else phys
    return {
        "invoice": record(inv),
        "status": st.status,
        "stage": plain(st.stage),
        "match_reason": m.iloc[0].reason if len(m) else None,
        "voucher": voucher,
        "payments": payments,
        "ims": ims,
        "physical": record(p.iloc[0]) if len(p) else None,
        "flags": flags_out(ds.flags_for(invoice_id=iid)),
    }
