"""Matching cascade: pair every invoice with its books entry (Tally Purchase/Sales voucher).

Cheapest rules first:
  1. exact       party GSTIN + invoice number
  2. normalised  normalised invoice number + amount within ₹1
  3. fuzzy       amount ±2% + date ±7 days + name similarity ≥ 85, best unique candidate
  4. AI          an adjudicator picks one of the top-3 rule-ranked candidates, or none

Payments (bank lines) and IMS records are linked to invoices afterwards.
Pure functions: DataFrames in, results out.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from rapidfuzz import fuzz, utils

from halfca import config
from halfca.ingest.normalise import name_similarity, normalise_invoice_no

BOOK_TYPE = {"inward": "Purchase", "outward": "Sales"}

# (invoice, candidates) -> (voucher_no or None, confidence 0-1, one-line reason)
Adjudicator = Callable[[dict[str, Any], list[dict[str, Any]]], tuple[str | None, float, str]]

STAGES = [
    (1, "Exact", "GSTIN + invoice number"),
    (2, "Normalised", "Invoice number normalised · amount ±₹1"),
    (3, "Fuzzy", "Amount ±2% · date ±7 days · name ≥ 85"),
    (4, "AI adjudication", "Model picks from the top-3 rule candidates"),
]


@dataclass
class MatchResult:
    pairs: pd.DataFrame  # invoice_id, voucher_no, stage, confidence, method, reason
    funnel: pd.DataFrame  # stage, label, method, records_in, paired, left, skipped
    unmatched: pd.DataFrame  # invoices with no books partner, by ₹ impact
    stage4_skipped: bool


def _party(inv: dict[str, Any]) -> tuple[str | None, str]:
    if inv["direction"] == "inward":
        return inv["supplier_gstin"], inv["supplier_name"]
    return inv["buyer_gstin"], inv["buyer_name"]


def _gstin_ok(inv: dict[str, Any], v: dict[str, Any]) -> bool:
    """Ledger GSTIN, when present, must not contradict the invoice."""
    g, _ = _party(inv)
    return not v["party_gstin"] or v["party_gstin"] == g


def _days(a: Any, b: Any) -> int:
    return abs((pd.Timestamp(a) - pd.Timestamp(b)).days)


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    out = df.to_dict("records")
    for r in out:
        for k, v in r.items():
            if v is pd.NA or (isinstance(v, float) and pd.isna(v)):
                r[k] = None
    return out


def candidates_for(
    inv: dict[str, Any], vouchers: list[dict[str, Any]], k: int
) -> list[dict[str, Any]]:
    """Stage-4 shortlist: loose rule ranking (amount ±10%, date ±15 days)."""
    out = []
    _, name = _party(inv)
    for v in vouchers:
        if v["voucher_type"] != BOOK_TYPE[inv["direction"]] or not _gstin_ok(inv, v):
            continue
        amt = abs(v["amount"] - inv["total"]) / max(inv["total"], 1)
        days = _days(v["voucher_date"], inv["invoice_date"])
        if amt > 0.10 or days > 15:
            continue
        sim = name_similarity(v["party_name"], name)
        score = 0.5 * (1 - amt / 0.10) + 0.3 * (1 - days / 15) + 0.2 * sim / 100
        out.append(
            {
                "voucher_no": v["voucher_no"],
                "voucher_date": str(pd.Timestamp(v["voucher_date"]).date()),
                "party_name": v["party_name"],
                "reference": v["reference"],
                "amount": v["amount"],
                "narration": v["narration"],
                "amount_diff": round(v["amount"] - inv["total"], 2),
                "days_apart": days,
                "name_similarity": round(sim, 1),
                "score": round(score, 3),
            }
        )
    return sorted(out, key=lambda c: -c["score"])[:k]


def match(
    invoices: pd.DataFrame, ledger: pd.DataFrame, adjudicator: Adjudicator | None = None
) -> MatchResult:
    inv_list = sorted(
        _records(invoices), key=lambda r: (pd.Timestamp(r["invoice_date"]), r["invoice_id"])
    )
    books = ledger[ledger.voucher_type.isin(BOOK_TYPE.values())]
    vouchers = sorted(
        _records(books), key=lambda r: (pd.Timestamp(r["voucher_date"]), r["voucher_no"])
    )
    free = {v["voucher_no"]: v for v in vouchers}
    open_inv = {i["invoice_id"]: i for i in inv_list}
    pairs: list[dict[str, Any]] = []
    funnel: list[dict[str, Any]] = []

    def pair(
        inv: dict[str, Any], v: dict[str, Any], stage: int, conf: float, method: str, reason: str
    ) -> None:
        pairs.append(
            {
                "invoice_id": inv["invoice_id"],
                "voucher_no": v["voucher_no"],
                "stage": stage,
                "confidence": round(conf, 3),
                "method": method,
                "reason": reason,
            }
        )
        free.pop(v["voucher_no"], None)
        open_inv.pop(inv["invoice_id"], None)

    def record(stage: int, before: int, skipped: bool = False) -> None:
        label, method = STAGES[stage - 1][1], STAGES[stage - 1][2]
        funnel.append(
            {
                "stage": stage,
                "label": label,
                "method": method,
                "records_in": before,
                "paired": before - len(open_inv),
                "left": len(open_inv),
                "skipped": skipped,
            }
        )

    # 1 · exact key
    before = len(open_inv)
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for v in vouchers:
        if v["party_gstin"] and v["reference"]:
            by_key[(v["voucher_type"], v["party_gstin"], v["reference"])].append(v)
    for inv in list(open_inv.values()):
        g, _ = _party(inv)
        queue = by_key.get((BOOK_TYPE[inv["direction"]], g, inv["invoice_no"]), [])
        while queue and queue[0]["voucher_no"] not in free:
            queue.pop(0)
        if queue:
            pair(inv, queue.pop(0), 1, 1.0, "exact", "GSTIN and invoice number match exactly")
    record(1, before)

    # 2 · normalised number + amount
    before = len(open_inv)
    by_norm: dict[tuple, list[dict]] = defaultdict(list)
    for v in free.values():
        if v["reference"]:
            by_norm[(v["voucher_type"], normalise_invoice_no(v["reference"]))].append(v)
    for inv in list(open_inv.values()):
        cands = [
            v
            for v in by_norm.get(
                (BOOK_TYPE[inv["direction"]], normalise_invoice_no(inv["invoice_no"])), []
            )
            if v["voucher_no"] in free
            and abs(v["amount"] - inv["total"]) <= config.STAGE2_AMOUNT_TOL
            and _gstin_ok(inv, v)
        ]
        if cands:
            v = min(cands, key=lambda c: _days(c["voucher_date"], inv["invoice_date"]))
            same = v["reference"] == inv["invoice_no"]
            pair(
                inv,
                v,
                2,
                0.98,
                "normalised",
                "Same number and amount; ledger has no GSTIN"
                if same
                else f"Ledger reference '{v['reference']}' normalises to the same number",
            )
    record(2, before)

    # 3 · fuzzy: amount, date, name; best unique candidate
    before = len(open_inv)
    proposals: dict[str, tuple[dict, dict, float]] = {}
    for inv in open_inv.values():
        _, name = _party(inv)
        scored = []
        for v in free.values():
            if v["voucher_type"] != BOOK_TYPE[inv["direction"]] or not _gstin_ok(inv, v):
                continue
            amt = abs(v["amount"] - inv["total"]) / max(inv["total"], 1)
            days = _days(v["voucher_date"], inv["invoice_date"])
            sim = name_similarity(v["party_name"], name)
            if (
                amt <= config.STAGE3_AMOUNT_PCT
                and days <= config.STAGE3_DATE_DAYS
                and sim >= config.STAGE3_NAME_MIN
            ):
                scored.append((sim - amt * 100 - days, v, sim))
        scored.sort(key=lambda s: -s[0])
        if scored and (len(scored) == 1 or scored[0][0] > scored[1][0]):
            proposals[inv["invoice_id"]] = (inv, scored[0][1], scored[0][2])
    claimed = defaultdict(list)
    for iid, (_, v, _) in proposals.items():
        claimed[v["voucher_no"]].append(iid)
    for inv, v, sim in proposals.values():
        if len(claimed[v["voucher_no"]]) == 1:
            pair(
                inv,
                v,
                3,
                sim / 100,
                "fuzzy",
                f"Same amount and date; ledger party '{v['party_name']}' ({sim:.0f}% name match)",
            )
    record(3, before)

    # 4 · AI adjudication over the top-3 rule candidates
    before = len(open_inv)
    skipped = adjudicator is None
    if adjudicator is not None:
        for inv in sorted(open_inv.values(), key=lambda r: -r["total"]):
            cands = candidates_for(inv, list(free.values()), config.STAGE4_TOP_K)
            if not cands:
                continue
            choice, conf, reason = adjudicator(inv, cands)
            if choice and choice in free and choice in {c["voucher_no"] for c in cands}:
                pair(inv, free[choice], 4, conf, "ai", reason)
    record(4, before, skipped=skipped)

    unmatched = invoices[invoices.invoice_id.isin(open_inv)].sort_values("total", ascending=False)
    return MatchResult(
        pairs=pd.DataFrame(
            pairs, columns=["invoice_id", "voucher_no", "stage", "confidence", "method", "reason"]
        ),
        funnel=pd.DataFrame(funnel),
        unmatched=unmatched.reset_index(drop=True),
        stage4_skipped=skipped,
    )


# ── payments and IMS ─────────────────────────────────────────────────────────


def _bank_name_sim(a: str, b: str) -> float:
    """Bank narrations truncate names, so partial matches count."""
    return max(
        name_similarity(a, b),
        float(fuzz.partial_ratio(a or "", b or "", processor=utils.default_process)),
    )


def narration_ref(narration: str) -> str:
    """'NEFT DR-PATEL PIPES-PP/26/0912' → 'PP/26/0912' (mode-name-reference)."""
    parts = (narration or "").split("-", 2)
    return parts[2].strip() if len(parts) == 3 else ""


def link_payments(invoices: pd.DataFrame, bank: pd.DataFrame, dup_ids: set[str]) -> pd.DataFrame:
    """Each bank line → at most one invoice. Reference first, then exact amount + name."""
    inv = _records(invoices)
    by_raw: dict[tuple, list[dict]] = defaultdict(list)
    by_norm: dict[tuple, list[dict]] = defaultdict(list)
    for r in inv:
        by_raw[(r["direction"], r["invoice_no"])].append(r)
        by_norm[(r["direction"], normalise_invoice_no(r["invoice_no"]))].append(r)
    links = []
    for t in _records(bank):
        direction = "inward" if t["direction"] == "debit" else "outward"
        ref = narration_ref(t["narration"])
        cands = by_raw.get((direction, ref), []) if ref else []
        method = "reference"
        if not cands and ref:
            cands = by_norm.get((direction, normalise_invoice_no(ref)), [])
        if cands:
            cands = sorted(
                cands,
                key=lambda r: (
                    r["invoice_id"] in dup_ids,
                    -_bank_name_sim(t["counterparty"], _party(r)[1]),
                ),
            )
            links.append(
                {"txn_id": t["txn_id"], "invoice_id": cands[0]["invoice_id"], "method": method}
            )
            continue
        # No usable reference: exact amount, plausible date, same party, and only one such invoice.
        paid = pd.Timestamp(t["txn_date"])
        hits = [
            r
            for r in inv
            if r["direction"] == direction
            and abs(r["total"] - t["amount"]) <= 1
            and -2 <= (paid - pd.Timestamp(r["invoice_date"])).days <= 90
            and _bank_name_sim(t["counterparty"], _party(r)[1]) >= 80
            and r["invoice_id"] not in dup_ids
        ]
        if len(hits) == 1:
            links.append(
                {
                    "txn_id": t["txn_id"],
                    "invoice_id": hits[0]["invoice_id"],
                    "method": "amount+name",
                }
            )
    return pd.DataFrame(links, columns=["txn_id", "invoice_id", "method"])


def link_ims(invoices: pd.DataFrame, ims: pd.DataFrame, dup_ids: set[str]) -> pd.DataFrame:
    """Each IMS record → the inward invoice it describes (originals before duplicate copies)."""
    inward = [r for r in _records(invoices) if r["direction"] == "inward"]
    inward.sort(
        key=lambda r: (r["invoice_id"] in dup_ids, pd.Timestamp(r["invoice_date"]), r["invoice_id"])
    )
    by_raw: dict[tuple, list[dict]] = defaultdict(list)
    by_norm: dict[tuple, list[dict]] = defaultdict(list)
    for r in inward:
        by_raw[(r["supplier_gstin"], r["invoice_no"])].append(r)
        by_norm[(r["supplier_gstin"], normalise_invoice_no(r["invoice_no"]))].append(r)
    used: set[str] = set()
    links = []
    for rec in _records(ims):
        hit = None
        for r in by_raw.get((rec["supplier_gstin"], rec["invoice_no"]), []):
            if r["invoice_id"] not in used:
                hit, method = r, "exact"
                break
        if hit is None:
            for r in by_norm.get(
                (rec["supplier_gstin"], normalise_invoice_no(rec["invoice_no"])), []
            ):
                if r["invoice_id"] not in used and abs(r["total"] - rec["total"]) <= 1:
                    hit, method = r, "normalised"
                    break
        if hit is not None:
            used.add(hit["invoice_id"])
            links.append(
                {"ims_id": rec["ims_id"], "invoice_id": hit["invoice_id"], "method": method}
            )
    return pd.DataFrame(links, columns=["ims_id", "invoice_id", "method"])
