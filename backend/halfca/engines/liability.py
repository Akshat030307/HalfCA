"""Tax liability: output tax − eligible ITC, as filed vs reconciled, by tax head.

  eligible ITC = claimed − rejected − at risk
  exposure     = rejected + at risk + under-reported output tax
As filed = every IMS record deemed accepted and output tax exactly as invoiced.
Reconciled = IMS Autopilot's decisions and output tax corrected upwards where an
invoice under-charged (over-collected tax is still owed, so it is never reduced).
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

HEADS = ("igst", "cgst", "sgst")


@dataclass
class Liability:
    summary: dict[str, float]
    heads: (
        pd.DataFrame
    )  # head, output_filed, output_reconciled, itc_claimed, itc_eligible, net_filed, net_reconciled
    waterfall: list[dict[str, float | str]]


def _split(total: float, head: str) -> dict[str, float]:
    if head == "igst":
        return {"igst": total, "cgst": 0.0, "sgst": 0.0}
    return {"igst": 0.0, "cgst": total / 2, "sgst": total / 2}


def compute(
    invoices: pd.DataFrame,
    ims_decisions: pd.DataFrame,
    tax_expected: pd.DataFrame,
    dup_of: dict[str, str],
) -> Liability:
    out = invoices[(invoices.direction == "outward")]
    filed = {h: float(out[h].sum()) for h in HEADS}

    exp = tax_expected.set_index("invoice_id")
    reconciled = dict.fromkeys(HEADS, 0.0)
    under = 0.0
    for r in out.itertuples():
        if r.invoice_id in dup_of:
            continue
        e = exp.loc[r.invoice_id]
        recorded = float(r.cgst + r.sgst + r.igst)
        owed = max(recorded, float(e.expected_tax))
        under += max(0.0, float(e.expected_tax) - recorded)
        for h, v in _split(owed, str(e.expected_head)).items():
            reconciled[h] += v

    d = ims_decisions
    claimed = {h: float(d[h].sum()) for h in HEADS}
    rejected = {h: float(d.loc[d.decision == "Reject", h].sum()) for h in HEADS}
    at_risk = {h: float(d.loc[d.decision == "Pending", h].sum()) for h in HEADS}
    eligible = {h: claimed[h] - rejected[h] - at_risk[h] for h in HEADS}

    heads = pd.DataFrame(
        [
            {
                "head": h.upper(),
                "output_filed": round(filed[h], 2),
                "output_reconciled": round(reconciled[h], 2),
                "itc_claimed": round(claimed[h], 2),
                "itc_eligible": round(eligible[h], 2),
                "net_filed": round(filed[h] - claimed[h], 2),
                "net_reconciled": round(reconciled[h] - eligible[h], 2),
            }
            for h in HEADS
        ]
    )
    s = {
        "output_tax_filed": sum(filed.values()),
        "output_tax_reconciled": sum(reconciled.values()),
        "under_reported_output": under,
        "itc_claimed": sum(claimed.values()),
        "itc_rejected": sum(rejected.values()),
        "itc_at_risk": sum(at_risk.values()),
        "itc_eligible": sum(eligible.values()),
    }
    s["net_payable_filed"] = s["output_tax_filed"] - s["itc_claimed"]
    s["net_payable_reconciled"] = s["output_tax_reconciled"] - s["itc_eligible"]
    s["exposure"] = s["itc_rejected"] + s["itc_at_risk"] + s["under_reported_output"]
    s = {k: round(v, 2) for k, v in s.items()}
    waterfall = [
        {"step": "Claimed", "value": s["itc_claimed"], "kind": "total"},
        {"step": "Rejected", "value": -s["itc_rejected"], "kind": "delta"},
        {"step": "At risk", "value": -s["itc_at_risk"], "kind": "delta"},
        {"step": "Eligible", "value": s["itc_eligible"], "kind": "total"},
    ]
    return Liability(s, heads, waterfall)
