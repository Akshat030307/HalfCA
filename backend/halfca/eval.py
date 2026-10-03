"""Precision and recall per discrepancy type (D01–D16) on random-mode months.

    make eval                       10 months (seeds 1..10), no model: stage 4 skipped
    make eval SEEDS="7 11"          chosen seeds
    uv run python -m halfca.eval --llm   with the configured model for stage 4 (costs tokens)

Each month is generated with truth labels, written in its native formats, read back
through the same loaders as an upload and reconciled by the pipeline. Engines never see
the labels; this script compares their findings with them, per invoice.

  D01–D14  an invoice is "found" when it carries the flag kind(s) for that type
  D09      unbooked or unpaid invoices by invoice; a payment with no invoice is matched to
           a payment-only flag by party name (the bank shows a name, not a GSTIN)
  D15      invoices from a supplier whose taint reaches the at-risk line
  D16      invoices between ₹45,000 and ₹49,999 from a supplier flagged for hugging

These numbers are measured on synthetic data, so they say how well the engines find what
the generator planted, not how they would do on real books.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from halfca import config, store
from halfca.data import build
from halfca.ingest.normalise import name_similarity

CODES: dict[str, tuple[str, list[str]]] = {
    "D01": ("Amount mismatch", ["amount"]),
    "D02": ("Date mismatch", ["date"]),
    "D03": ("Invoice ID typo / reformat", ["invoice_id"]),
    "D04": ("Wrong tax rate", ["tax_rate"]),
    "D05": ("Wrong tax head", ["tax_head"]),
    "D06": ("Tax arithmetic error", ["tax_arith"]),
    "D07": ("Exact duplicate", ["duplicate"]),
    "D08": ("Near-duplicate", ["near_duplicate"]),
    "D09": ("Invoice without payment / payment without invoice", ["unmatched", "unpaid_aged"]),
    "D10": ("In books, not on IMS", ["not_in_ims"]),
    "D11": ("Missing e-way bill", ["missing_ewb"]),
    "D12": ("Paper-only supply", ["paper_only"]),
    "D13": ("Impossible journey", ["impossible_journey"]),
    "D14": ("Recycled e-way bill", ["recycled_ewb"]),
    "D15": ("Supplier fed by a circular-trading ring", []),
    "D16": ("Threshold hugging", []),
}
ORPHAN_NAME_MIN = 80.0  # name similarity for a payment-only flag to count as the orphan


@dataclass
class Score:
    code: str
    name: str
    truth: int = 0
    found: int = 0
    tp: int = 0
    extra: dict[str, int] = field(default_factory=dict)  # false positives by finding

    @property
    def fp(self) -> int:
        return self.found - self.tp

    @property
    def fn(self) -> int:
        return self.truth - self.tp

    @property
    def precision(self) -> float | None:
        return self.tp / self.found if self.found else None

    @property
    def recall(self) -> float | None:
        return self.tp / self.truth if self.truth else None

    def add(self, other: Score) -> None:
        self.truth += other.truth
        self.found += other.found
        self.tp += other.tp
        for k, n in other.extra.items():
            self.extra[k] = self.extra.get(k, 0) + n


def _predicted(
    code: str, flags: pd.DataFrame, invoices: pd.DataFrame, raw_inv: pd.DataFrame
) -> set[str]:
    if code == "D15":
        at_risk = invoices[
            (invoices.direction == "inward") & (invoices.taint >= config.TAINT_AT_RISK)
        ]
        return set(at_risk.invoice_id)
    if code == "D16":
        huggers = set(flags[flags.kind == "threshold_hugging"].ref)
        inv = raw_inv[raw_inv.supplier_gstin.isin(huggers) & (raw_inv.direction == "inward")]
        return set(inv[inv.total.between(config.HUG_LOW, config.HUG_HIGH)].invoice_id)
    kinds = CODES[code][1]
    return set(flags[flags.kind.isin(kinds)].invoice_id.dropna())


def _extra(code: str, ids: set[str], flags: pd.DataFrame) -> dict[str, int]:
    """False positives grouped by the finding that produced them."""
    if not ids:
        return {}
    if code in ("D15", "D16"):
        what = "At-risk supplier's invoice" if code == "D15" else "Hugger's other ₹45–50k invoice"
        return {what: len(ids)}
    kinds = CODES[code][1]
    f = flags[flags.invoice_id.isin(ids) & flags.kind.isin(kinds)].drop_duplicates("invoice_id")
    return {str(k): int(n) for k, n in f.label.value_counts().items()}


def score_month(folder: Path) -> dict[str, Score]:
    """Score one generated month (its truth labels against its reconciliation)."""
    db = folder / "halfca.duckdb"
    flags = store.table("res_flags", db)
    invoices = store.table("res_invoices", db)
    raw_inv = store.table("raw_invoices", db)
    names = dict(
        zip(
            store.table("raw_counterparties", db).gstin,
            store.table("raw_counterparties", db)["name"],
            strict=True,
        )
    )
    truth = pd.read_csv(folder / "truth" / "truth_labels.csv", dtype=str)

    scores: dict[str, Score] = {}
    for code, (name, _) in CODES.items():
        t = truth[truth.code == code]
        s = Score(code, name)
        if code == "D09":
            on_invoice = set(t[t.invoice_id.str.startswith("i")].invoice_id)
            orphans = t[~t.invoice_id.str.startswith("i")]
            pred = _predicted(code, flags, invoices, raw_inv)
            paid_only = flags[flags.kind == "payment_only"]
            unclaimed = list(paid_only.counterparty)
            orphan_hits = 0
            for g in orphans.party_gstin:
                party = names.get(g, "")
                best = max(unclaimed, key=lambda n: name_similarity(n, party), default=None)
                if best is not None and name_similarity(best, party) >= ORPHAN_NAME_MIN:
                    unclaimed.remove(best)
                    orphan_hits += 1
            s.truth = len(on_invoice) + len(orphans)
            s.found = len(pred) + len(paid_only)
            s.tp = len(pred & on_invoice) + orphan_hits
            s.extra = _extra(code, pred - on_invoice, flags)
            if len(unclaimed):
                s.extra["Payment without invoice"] = len(unclaimed)
        else:
            labelled = set(t.invoice_id)
            pred = _predicted(code, flags, invoices, raw_inv)
            s.truth, s.found, s.tp = len(labelled), len(pred), len(pred & labelled)
            s.extra = _extra(code, pred - labelled, flags)
        scores[code] = s
    return scores


def run(seeds: list[int], llm: bool = False, out_dir: Path | None = None) -> dict[str, Any]:
    out_dir = out_dir or config.DATA_DIR / "eval"
    total = {code: Score(code, name) for code, (name, _) in CODES.items()}
    per_seed = {}
    for seed in seeds:
        folder = out_dir / f"seed-{seed}"
        build.run("random", seed=seed, out=folder, adjudicator=build.DEFAULT if llm else None)
        month = score_month(folder)
        per_seed[seed] = {c: asdict(s) for c, s in month.items()}
        for c, s in month.items():
            total[c].add(s)
    overall = Score("ALL", "All types")
    for s in total.values():
        overall.add(s)
    return {
        "seeds": seeds,
        "stage4": "configured model" if llm else "skipped (no model)",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "scores": total,
        "overall": overall,
        "per_seed": per_seed,
    }


def _pct(v: float | None) -> str:
    """100% only when it is exact; 886 of 887 reads 99.9%, not 100%."""
    if v is None:
        return "—"
    return "100%" if v == 1 else f"{min(v * 100, 99.9):.1f}%"


def table(result: dict[str, Any]) -> str:
    rows = [
        "| Code | Discrepancy | Planted | Flagged | Correct | Precision | Recall |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for s in [*result["scores"].values(), result["overall"]]:
        code = f"**{s.code}**" if s.code == "ALL" else s.code
        rows.append(
            f"| {code} | {s.name} | {s.truth} | {s.found} | {s.tp} | "
            f"{_pct(s.precision)} | {_pct(s.recall)} |"
        )
    return "\n".join(rows)


def console(result: dict[str, Any]) -> str:
    head = (
        f"{'code':5} {'discrepancy':52} {'planted':>7} {'flagged':>7} {'right':>6} "
        f"{'prec':>6} {'recall':>6}"
    )
    lines = [head, "-" * len(head)]
    for s in [*result["scores"].values(), result["overall"]]:
        lines.append(
            f"{s.code:5} {s.name[:52]:52} {s.truth:7} {s.found:7} {s.tp:6} "
            f"{_pct(s.precision):>6} {_pct(s.recall):>6}"
        )
    return "\n".join(lines)


WHY = {
    "Unpaid past terms": (
        "clean invoices still unpaid more than {terms} days after their date on the as-of day. "
        "The generator pays clean invoices 0–45 days late, so these are real gaps under the "
        "{terms}-day rule that it simply did not label"
    ),
    "Unmatched": "invoices left without a books entry because stage 4 was skipped",
    "Payment without invoice": "bank lines with no invoice that were not planted as D09",
}


def _extras(result: dict[str, Any]) -> str:
    lines = []
    for s in result["scores"].values():
        if not s.extra:
            continue
        parts = [
            f"{n} × {k.lower()}"
            + (f" ({WHY[k].format(terms=config.PAYMENT_TERMS_DAYS)})" if k in WHY else "")
            for k, n in sorted(s.extra.items(), key=lambda kv: -kv[1])
        ]
        lines.append(f"- **{s.code}** extra flags: " + "; ".join(parts) + ".")
    if not lines:
        return ""
    return "Where the extra flags come from:\n\n" + "\n".join(lines) + "\n"


def write_doc(result: dict[str, Any], path: Path) -> None:
    seeds = result["seeds"]
    path.write_text(
        f"""# Half CA: detection accuracy on synthetic data

Measured {result["generated_at"][:10]} with `make eval`: {len(seeds)} random-mode months
(seeds {", ".join(map(str, seeds))}), each about 550 invoices with discrepancies planted at
the catalogue rates in `CLAUDE.md`. Stage-4 matching: {result["stage4"]}.

**These numbers are measured on synthetic data.** They say how well the engines find what
the generator planted, not how they would do on real books. The generator and the engines
were written from the same spec, so planted cases are clear-cut; real books are messier
(errors overlap, names and references are dirtier), so expect lower numbers there.

{table(result)}

{_extras(result)}
How it is scored (per invoice, `backend/halfca/eval.py`):

- *Planted*: invoices the generator labelled with that code. *Flagged*: invoices the engines
  flagged for it. *Correct*: both. Precision = correct ÷ flagged; recall = correct ÷ planted.
- D09 counts unbooked and unpaid invoices by invoice, and matches a payment with no
  invoice to a payment-only finding by party name.
- D15 counts invoices from suppliers whose credit taint reaches {config.TAINT_AT_RISK:g};
  D16 counts the ₹45,000–₹49,999 invoices of a supplier flagged for threshold hugging.
- Every month is written in its native formats and read back through the upload loaders,
  so the run covers ingestion as well as the engines.
"""
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seeds", type=int, nargs="*", help="seeds to run (default 1..10)")
    ap.add_argument("--seed", type=int, help="a single seed")
    ap.add_argument("--llm", action="store_true", help="use the configured model for stage 4")
    ap.add_argument("--doc", type=Path, default=config.REPO_DIR / "docs" / "EVAL.md")
    args = ap.parse_args()
    seeds = [args.seed] if args.seed is not None else (args.seeds or list(range(1, 11)))
    result = run(seeds, llm=args.llm)
    print()
    print(console(result))
    out = config.DATA_DIR / "eval" / "eval.json"
    out.write_text(
        json.dumps(
            {
                **{k: v for k, v in result.items() if k not in ("scores", "overall")},
                "scores": {c: asdict(s) for c, s in result["scores"].items()},
                "overall": asdict(result["overall"]),
            },
            indent=1,
        )
    )
    write_doc(result, args.doc)
    print(f"\n→ {out}\n→ {args.doc}  (measured on synthetic data)")


if __name__ == "__main__":
    main()
