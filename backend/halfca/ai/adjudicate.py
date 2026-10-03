"""Stage-4 match adjudication: the model picks one rule-ranked candidate, or none.

It never sees anything but the invoice and the shortlist, and its answer is only used
if it names one of the shortlisted voucher numbers.
"""

from __future__ import annotations

import json
from typing import Any

from halfca.engines.matching import Adjudicator

from .llm import LLMClient, LLMError

SYSTEM = """You match Indian GST invoices to entries in a Tally accounting ledger.
You get one invoice and up to three candidate ledger vouchers that rules shortlisted.
Pick the voucher that records the same transaction, or "none" if none clearly does.
Accountants often key short aliases or initials for a party name and may leave the
reference blank; amounts and dates must still agree. Do not guess when two candidates
fit equally well. Answer only with JSON:
{"choice": "<a voucher_no from the list, or none>",
 "confidence": <0..1>,
 "reason": "<one short sentence>"}"""


def _invoice_view(inv: dict[str, Any]) -> dict[str, Any]:
    party = inv["supplier_name"] if inv["direction"] == "inward" else inv["buyer_name"]
    return {
        "invoice_no": inv["invoice_no"],
        "date": str(inv["invoice_date"])[:10],
        "direction": "purchase" if inv["direction"] == "inward" else "sale",
        "party": party,
        "total": inv["total"],
    }


def _candidate_view(c: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "voucher_no",
        "voucher_date",
        "party_name",
        "reference",
        "amount",
        "narration",
        "amount_diff",
        "days_apart",
    )
    return {k: c[k] for k in keys}


def llm_adjudicator(client: LLMClient) -> Adjudicator:
    def adjudicate(
        inv: dict[str, Any], cands: list[dict[str, Any]]
    ) -> tuple[str | None, float, str]:
        allowed = {c["voucher_no"] for c in cands}
        user = json.dumps(
            {"invoice": _invoice_view(inv), "candidates": [_candidate_view(c) for c in cands]},
            default=str,
        )
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
        for attempt in range(2):  # one retry on a malformed answer
            try:
                raw = client.chat(messages, json_mode=True, max_tokens=600, cache=attempt == 0)
                data = json.loads(raw)
                choice = str(data.get("choice", "")).strip()
                conf = float(data.get("confidence", 0))
                reason = str(data.get("reason", "")).strip()[:200]
            except (LLMError, ValueError, TypeError):
                continue
            if choice.lower() == "none":
                return None, conf, reason or "No candidate records the same transaction"
            if choice in allowed:
                return choice, max(0.0, min(conf, 1.0)), reason
        return None, 0.0, "Model gave no usable answer; left unmatched"

    return adjudicate
