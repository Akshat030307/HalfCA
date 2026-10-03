"""What every engine emits: flags with evidence.

A flag is one finding about one record. Its evidence says what was recorded, what was
expected and which source records prove it, so the UI can show it, the copilot can cite
it and the PDF can print it.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd

# kind -> (category, label shown in the UI)
KINDS: dict[str, tuple[str, str]] = {
    "amount": ("discrepancy", "Amount"),
    "date": ("discrepancy", "Date"),
    "invoice_id": ("discrepancy", "Invoice ID"),
    "tax_rate": ("discrepancy", "Tax rate"),
    "tax_head": ("discrepancy", "Tax head"),
    "tax_arith": ("discrepancy", "Tax maths"),
    "duplicate": ("duplicate", "Duplicate"),
    "near_duplicate": ("duplicate", "Near-duplicate"),
    "unmatched": ("unmatched", "Unmatched"),
    "unpaid_aged": ("gap", "Unpaid past terms"),
    "payment_only": ("gap", "Payment without invoice"),
    "not_in_ims": ("gap", "Not on IMS"),
    "ims_only": ("gap", "On IMS, not in books"),
    "missing_ewb": ("physical", "Missing e-way bill"),
    "paper_only": ("physical", "Paper-only supply"),
    "impossible_journey": ("physical", "Impossible journey"),
    "recycled_ewb": ("physical", "Recycled e-way bill"),
    "ring_taint": ("credit", "Ring taint"),
    "benford": ("anomaly", "Benford"),
    "threshold_hugging": ("anomaly", "Threshold hugging"),
    "outlier": ("anomaly", "Unusual invoice"),
    "transition_review": ("review", "GST 2.0 transition"),
    "invalid_gstin": ("review", "Invalid GSTIN"),
}
DISCREPANCY_KINDS = [k for k, (c, _) in KINDS.items() if c == "discrepancy"]
PHYSICAL_KINDS = [k for k, (c, _) in KINDS.items() if c == "physical"]


@dataclass
class Flag:
    kind: str
    invoice_id: str | None
    ref: str  # human reference: invoice no, txn id, GSTIN
    counterparty: str
    gstin: str | None
    title: str
    recorded: str | None
    expected: str | None
    impact: float  # ₹ at stake
    evidence: dict[str, Any] = field(default_factory=dict)
    severity: str = "medium"  # low | medium | high

    @property
    def category(self) -> str:
        return KINDS[self.kind][0]

    @property
    def flag_id(self) -> str:
        return f"{self.kind}:{self.invoice_id or self.ref}"


def chain(source: str, id_: str, label: str, **fields: Any) -> dict[str, Any]:
    """One link in an evidence chain: a source record and the fields that matter."""
    return {"source": source, "id": id_, "label": label, "fields": _plain(fields)}


def evidence(
    summary: str,
    recorded: dict | None = None,
    expected: dict | None = None,
    links: list[dict] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "recorded": _plain(recorded or {}),
        "expected": _plain(expected or {}),
        "chain": links or [],
        "notes": notes or [],
    }


def _plain(obj: Any) -> Any:
    """JSON-safe values (timestamps → ISO strings, numpy → python)."""
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_plain(v) for v in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if hasattr(obj, "item") and not isinstance(obj, str):
        try:
            return obj.item()
        except (ValueError, AttributeError):
            return obj
    if obj is pd.NA:
        return None
    return obj


def flags_frame(flags: list[Flag]) -> pd.DataFrame:
    rows = []
    for f in flags:
        d = asdict(f)
        d["flag_id"] = f.flag_id
        d["category"] = f.category
        d["label"] = KINDS[f.kind][1]
        d["evidence"] = json.dumps(_plain(f.evidence), ensure_ascii=False)
        rows.append(d)
    cols = [
        "flag_id",
        "kind",
        "category",
        "label",
        "invoice_id",
        "ref",
        "counterparty",
        "gstin",
        "title",
        "recorded",
        "expected",
        "impact",
        "severity",
        "evidence",
    ]
    return pd.DataFrame(rows, columns=cols)


def counterparty(row: Any) -> tuple[str, str]:
    """(gstin, name) of the other party on an invoice row."""
    if row["direction"] == "inward":
        return row["supplier_gstin"], row["supplier_name"]
    return row["buyer_gstin"], row["buyer_name"]


def tax_of(row: Any) -> float:
    return float(row["cgst"]) + float(row["sgst"]) + float(row["igst"])
