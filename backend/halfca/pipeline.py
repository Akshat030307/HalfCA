"""Run every engine over the raw tables and produce the result tables (res_*).

  GSTIN checks → duplicates → physical trail → matching cascade → payment/IMS links
  → field diffs → tax → invoice PDFs vs register → gaps → credit taint → anomalies
  → IMS Autopilot → liability

Pure: frames in, frames out. Saving is the caller's job (store.save). An optional
`progress(step, state, detail)` callback reports the steps the Upload screen shows:
gstin → normalise → road → match.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import pandas as pd

from halfca import config
from halfca.ai.ims_autopilot import decide
from halfca.data import routes as geo_mod
from halfca.engines import (
    anomaly,
    documents,
    dupes_gaps,
    identity,
    liability,
    matching,
    physical,
    taint,
    tax,
)
from halfca.engines.common import DISCREPANCY_KINDS, PHYSICAL_KINDS, Flag, counterparty, flags_frame
from halfca.engines.matching import BOOK_TYPE, Adjudicator
from halfca.ingest.normalise import normalise_invoice_no

Progress = Callable[[str, str, str | None], None]


def _quiet(step: str, state: str, detail: str | None) -> None:
    pass


def _retyped_refs(inv: pd.DataFrame, ledger: pd.DataFrame) -> int:
    """Ledger references that only match an invoice once normalised."""
    raw = set(zip(inv.direction.map(BOOK_TYPE), inv.invoice_no, strict=True))
    norm = set(
        zip(inv.direction.map(BOOK_TYPE), inv.invoice_no.map(normalise_invoice_no), strict=True)
    )
    n = 0
    for v in ledger[ledger.reference.notna()].itertuples():
        if (v.voucher_type, v.reference) not in raw and (
            v.voucher_type,
            normalise_invoice_no(v.reference),
        ) in norm:
            n += 1
    return n


@dataclass
class Reconciliation:
    tables: dict[str, pd.DataFrame]  # keyed without the res_ prefix
    summary: dict[str, Any]
    flags: list[Flag]


def _as_of(meta: dict[str, Any]) -> date:
    return datetime.fromisoformat(str(meta["as_of"])).date()


def reconcile(
    frames: dict[str, pd.DataFrame],
    meta: dict[str, Any],
    adjudicator: Adjudicator | None = None,
    progress: Progress | None = None,
) -> Reconciliation:
    say = progress or _quiet
    inv = frames["invoices"]
    ledger, bank, ims = frames["ledger"], frames["bank"], frames["ims"]
    as_of = _as_of(meta)
    user = str(meta["user_gstin"])
    names = dict(zip(frames["counterparties"].gstin, frames["counterparties"].name, strict=True))

    say("gstin", "running", None)
    id_flags, id_stats = identity.validate_gstins(inv)
    say("gstin", "done", f"{id_stats['checked']} GSTINs · {id_stats['invalid']} invalid")

    say("normalise", "running", None)
    retyped = _retyped_refs(inv, ledger)
    say("normalise", "done", f"{len(inv)} numbers · {retyped} retyped in the books")

    say("road", "running", None)
    dup_flags, dup_of = dupes_gaps.find_duplicates(inv)
    dups = set(dup_of)
    phys = physical.check(
        inv, frames["eway_bills"], frames["toll_crossings"], geo_mod.load(), dup_of
    )
    road_failed = sum(1 for v in phys.verdicts.get("verdict", []) if v in PHYSICAL_KINDS)
    say(
        "road",
        "done",
        f"{len(phys.verdicts)} consignments · {len(frames['toll_crossings'])} "
        f"toll crossings · {road_failed} failed",
    )

    say("match", "running", None)
    m = matching.match(inv, ledger, adjudicator)
    pay_links = matching.link_payments(inv, bank, dups)
    ims_links = matching.link_ims(inv, ims, dups)
    diff_flags = dupes_gaps.field_diffs(inv, ledger, m.pairs, pay_links, bank, dup_of)
    tx = tax.verify(inv, frames["hsn_rates"])
    doc_flags, doc_stats = documents.compare(frames.get("documents"), inv)
    unmatched_flags = dupes_gaps.unmatched_flags(m.unmatched, pay_links)
    gap_flags = dupes_gaps.gaps(inv, bank, ims, m.pairs, pay_links, ims_links, dup_of, as_of)
    tnt = taint.analyse(
        frames["counterparties"], frames["upstream_invoices"], inv, user, as_of, dup_of
    )
    benford, benford_flags = anomaly.benford(frames["upstream_invoices"], inv, dup_of, names)
    hug_flags = anomaly.threshold_hugging(inv, dup_of)
    outliers, outlier_flags = anomaly.outliers(inv, pay_links, bank, dup_of, as_of)

    flags: list[Flag] = (
        id_flags
        + dup_flags
        + diff_flags
        + tx.flags
        + doc_flags
        + unmatched_flags
        + gap_flags
        + phys.flags
        + tnt.flags
        + benford_flags
        + hug_flags
        + outlier_flags
    )
    by_invoice: dict[str, list[Flag]] = defaultdict(list)
    for f in flags:
        if f.invoice_id:
            by_invoice[f.invoice_id].append(f)

    booked = set(m.pairs.invoice_id)
    ims_dec = decide(ims, ims_links, booked, by_invoice, phys.verdicts, tnt.risk, inv)
    liab = liability.compute(inv, ims_dec, tx.expected, dup_of)

    # ── per-invoice status ──
    stage = dict(zip(m.pairs.invoice_id, m.pairs.stage, strict=True))
    voucher = dict(zip(m.pairs.invoice_id, m.pairs.voucher_no, strict=True))
    verdict = (
        dict(zip(phys.verdicts.invoice_id, phys.verdicts.verdict, strict=True))
        if len(phys.verdicts)
        else {}
    )
    ims_of = dict(zip(ims_dec.invoice_id, ims_dec.decision, strict=True))
    paid = Counter(pay_links.invoice_id) if len(pay_links) else Counter()
    rows = []
    for r in inv.itertuples():
        kinds = sorted({f.kind for f in by_invoice.get(r.invoice_id, [])})
        if r.invoice_id not in booked:
            status = "unmatched"
        elif r.invoice_id in dup_of:
            status = "duplicate"
        elif any(k in DISCREPANCY_KINDS for k in kinds):
            status = "discrepant"
        else:
            status = "matched"
        gstin, name = counterparty(r._asdict())
        rows.append(
            {
                "invoice_id": r.invoice_id,
                "invoice_no": r.invoice_no,
                "invoice_date": r.invoice_date,
                "direction": r.direction,
                "counterparty_gstin": gstin,
                "counterparty": name,
                "total": r.total,
                "tax": round(r.cgst + r.sgst + r.igst, 2),
                "status": status,
                "stage": stage.get(r.invoice_id),
                "voucher_no": voucher.get(r.invoice_id),
                "payments": paid.get(r.invoice_id, 0),
                "physical": verdict.get(r.invoice_id),
                "ims_decision": ims_of.get(r.invoice_id),
                "taint": round(tnt.risk.get(gstin, 0.0), 3),
                "duplicate_of": dup_of.get(r.invoice_id),
                "flags": json.dumps(kinds),
            }
        )
    invoices_out = pd.DataFrame(rows)

    # ── summary ──
    st = Counter(invoices_out.status)
    discrepant = invoices_out[invoices_out.status == "discrepant"]
    type_counts: Counter[str] = Counter()
    tax_dir: Counter[str] = Counter()
    for r in discrepant.itertuples():
        for k in json.loads(r.flags):
            if k in DISCREPANCY_KINDS:
                type_counts[k] += 1
                if k.startswith("tax_"):
                    tax_dir[r.direction] += 1
    failed = invoices_out[invoices_out.physical.isin(PHYSICAL_KINDS)]
    decisions = Counter(ims_dec.decision)
    summary: dict[str, Any] = {
        "period": meta.get("period"),
        "as_of": str(meta.get("as_of")),
        "reconciled": len(inv),
        "matched": st["matched"],
        "discrepancies": st["discrepant"],
        "duplicates": st["duplicate"],
        "unmatched": st["unmatched"],
        "clean_match_pct": round(st["matched"] / max(len(inv), 1), 4),
        "discrepancy_types": {k: type_counts.get(k, 0) for k in DISCREPANCY_KINDS},
        "tax_errors": {"inward": tax_dir["inward"], "outward": tax_dir["outward"]},
        "funnel": m.funnel.to_dict("records"),
        "stage4_skipped": m.stage4_skipped,
        "physical": {
            "checked": len(phys.verdicts),
            "verified": int((phys.verdicts.verdict == "verified").sum())
            if len(phys.verdicts)
            else 0,
            "failed": len(failed),
            "failed_inside_matched": int((failed.status == "matched").sum()),
            "by_verdict": dict(Counter(phys.verdicts.verdict)) if len(phys.verdicts) else {},
        },
        "ims": {
            "records": len(ims_dec),
            "accept": decisions["Accept"],
            "reject": decisions["Reject"],
            "pending": decisions["Pending"],
        },
        "liability": liab.summary,
        "exposure": liab.summary["exposure"],
        "rings": [[names.get(n, n) for n in c] for c in tnt.cycles],
        "at_risk_suppliers": sorted(names.get(s, s) for s in tnt.at_risk),
        "gaps": dict(Counter(f.kind for f in gap_flags)),
        "anomalies": dict(Counter(f.kind for f in benford_flags + hug_flags + outlier_flags)),
        "llm": config.LLM_PROVIDER or None,
        "gstins": id_stats,
        "retyped_refs": retyped,
        "documents": doc_stats,
    }

    tables = {
        "invoices": invoices_out,
        "matches": m.pairs,
        "funnel": m.funnel,
        "unmatched": m.unmatched[
            [
                "invoice_id",
                "invoice_no",
                "invoice_date",
                "direction",
                "supplier_name",
                "buyer_name",
                "total",
            ]
        ],
        "flags": flags_frame(flags),
        "payment_links": pay_links,
        "ims_links": ims_links,
        "physical": phys.verdicts,
        "taint_nodes": tnt.nodes,
        "taint_edges": tnt.edges,
        "cycles": pd.DataFrame(
            [
                {
                    "cycle_id": i,
                    "members": json.dumps(c),
                    "names": json.dumps([names.get(n, n) for n in c]),
                }
                for i, c in enumerate(tnt.cycles)
            ]
        ),
        "benford": benford,
        "outliers": outliers,
        "tax_expected": tx.expected,
        "ims": ims_dec,
        "liability_heads": liab.heads,
        "liability_waterfall": pd.DataFrame(liab.waterfall),
        "summary": pd.DataFrame(
            [{"key": k, "value": json.dumps(v, default=str)} for k, v in summary.items()]
        ),
    }
    say(
        "match",
        "done",
        f"{len(m.pairs)} paired · {len(m.unmatched)} left · "
        f"{summary['discrepancies']} discrepancies",
    )
    return Reconciliation(tables, summary, flags)
