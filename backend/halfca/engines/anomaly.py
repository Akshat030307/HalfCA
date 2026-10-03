"""Anomaly screens: Benford first digits, threshold hugging, Isolation Forest outliers."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from halfca import config, fmt
from halfca.ingest.normalise import normalise_invoice_no

from .common import Flag, counterparty, evidence

BENFORD = [math.log10(1 + 1 / d) for d in range(1, 10)]


def first_digit(value: float) -> int:
    return int(f"{abs(value):.6e}"[0])


def benford(
    upstream: pd.DataFrame, invoices: pd.DataFrame, dup_of: dict[str, str], names: dict[str, str]
) -> tuple[pd.DataFrame, list[Flag]]:
    """First-digit MAD per supplier with ≥ 50 invoices (upstream sales + sales to the user)."""
    inward = invoices[(invoices.direction == "inward") & ~invoices.invoice_id.isin(dup_of)]
    values = pd.concat(
        [
            upstream[["seller_gstin", "value"]],
            inward.rename(columns={"supplier_gstin": "seller_gstin", "total": "value"})[
                ["seller_gstin", "value"]
            ],
        ]
    )
    rows, flags = [], []
    for gstin, grp in values.groupby("seller_gstin"):
        n = len(grp)
        if n < config.BENFORD_MIN_N:
            continue
        c = Counter(first_digit(v) for v in grp.value if v)
        observed = [c.get(d, 0) / n for d in range(1, 10)]
        mad = sum(abs(o - e) for o, e in zip(observed, BENFORD, strict=True)) / 9
        nonconforming = mad > config.BENFORD_MAD_THRESHOLD
        rows.append(
            {
                "gstin": gstin,
                "name": names.get(gstin, gstin),
                "n": n,
                "mad": round(mad, 4),
                "nonconforming": nonconforming,
                "observed": json.dumps([round(o, 4) for o in observed]),
                "expected": json.dumps([round(e, 4) for e in BENFORD]),
            }
        )
        if nonconforming:
            worst = max(range(9), key=lambda i: abs(observed[i] - BENFORD[i]))
            flags.append(
                Flag(
                    "benford",
                    None,
                    gstin,
                    names.get(gstin, gstin),
                    gstin,
                    "Invoice amounts do not follow Benford's law",
                    recorded=f"MAD {mad:.3f} over {n} invoices",
                    expected=f"MAD ≤ {config.BENFORD_MAD_THRESHOLD}",
                    impact=0.0,
                    severity="medium",
                    evidence=evidence(
                        f"First digits of {n} invoice amounts deviate from Benford's law "
                        f"(MAD {mad:.3f}, "
                        f"nonconforming above {config.BENFORD_MAD_THRESHOLD}). Biggest gap: digit "
                        f"{worst + 1} at {observed[worst]:.0%} vs {BENFORD[worst]:.0%} expected.",
                        {"mad": round(mad, 4), "n": n},
                        {"mad_max": config.BENFORD_MAD_THRESHOLD},
                        [],
                        ["Made-up amounts tend to avoid 1s and cluster on mid digits."],
                    ),
                )
            )
    cols = ["gstin", "name", "n", "mad", "nonconforming", "observed", "expected"]
    return pd.DataFrame(rows, columns=cols), flags


def threshold_hugging(invoices: pd.DataFrame, dup_of: dict[str, str]) -> list[Flag]:
    """A supplier billing just under the e-way bill threshold, again and again."""
    flags = []
    inward = invoices[(invoices.direction == "inward") & ~invoices.invoice_id.isin(dup_of)]
    for gstin, grp in inward.groupby("supplier_gstin"):
        n = len(grp)
        hits = grp[grp.total.between(config.HUG_LOW, config.HUG_HIGH)]
        if n >= 6 and len(hits) >= 3 and len(hits) / n >= config.HUG_SHARE:
            name = grp.supplier_name.iloc[0]
            flags.append(
                Flag(
                    "threshold_hugging",
                    None,
                    gstin,
                    name,
                    gstin,
                    "Bills just under ₹50,000",
                    recorded=f"{len(hits)} of {n} invoices between {fmt.inr(config.HUG_LOW)} and "
                    f"{fmt.inr(config.HUG_HIGH)}",
                    expected=f"< {config.HUG_SHARE:.0%} in that band",
                    impact=float(hits.total.sum()),
                    evidence=evidence(
                        f"{len(hits) / n:.0%} of {name}'s invoices sit just under the ₹50,000 "
                        "e-way bill threshold, a pattern used to split consignments "
                        "and avoid e-way bills.",
                        {"share": round(len(hits) / n, 3)},
                        {"max_share": config.HUG_SHARE},
                        [],
                        [
                            ", ".join(
                                f"{r.invoice_no} {fmt.inr(r.total)}" for r in hits.itertuples()
                            )
                        ],
                    ),
                )
            )
    return flags


def _tail_number(no: str) -> float:
    digits = "".join(ch if ch.isdigit() else " " for ch in normalise_invoice_no(no)).split()
    return float(digits[-1]) if digits else np.nan


def outliers(
    invoices: pd.DataFrame,
    pay_links: pd.DataFrame,
    bank: pd.DataFrame,
    dup_of: dict[str, str],
    as_of: date,
) -> tuple[pd.DataFrame, list[Flag]]:
    """Isolation Forest over per-invoice features; the most isolated ~2% are flagged."""
    df = invoices[~invoices.invoice_id.isin(dup_of)].copy()
    if len(df) < 20:
        return pd.DataFrame(columns=["invoice_id", "score"]), []
    df["party"] = [counterparty(r)[0] for _, r in df.iterrows()]
    log_amt = np.log(df.total.clip(lower=1))
    grp = log_amt.groupby(df.party)
    df["amount_z"] = (
        (log_amt - grp.transform("mean")) / grp.transform("std").replace(0, np.nan)
    ).fillna(0)
    df["weekday"] = df.invoice_date.dt.weekday
    df["tail"] = df.invoice_no.map(_tail_number)
    df = df.sort_values(["party", "invoice_date"])
    df["number_gap"] = df.groupby("party")["tail"].diff().abs().fillna(0).clip(upper=500)
    df["roundness"] = ((df.total % 1000) == 0).astype(float) + ((df.total % 10000) == 0).astype(
        float
    )
    paid = (
        pay_links.merge(bank[["txn_id", "txn_date"]], on="txn_id")
        .groupby("invoice_id")
        .txn_date.min()
        if len(pay_links)
        else pd.Series(dtype="datetime64[ns]")
    )
    df["days_to_pay"] = [
        ((paid[i] if i in paid.index else pd.Timestamp(as_of)) - d).days
        for i, d in zip(df.invoice_id, df.invoice_date, strict=True)
    ]
    df["rate"] = df.rate
    features = ["amount_z", "weekday", "number_gap", "roundness", "days_to_pay", "rate"]
    X = df[features].to_numpy(dtype=float)
    model = IsolationForest(
        n_estimators=200, contamination=config.ISOFOREST_CONTAMINATION, random_state=0
    )
    model.fit(X)
    df["score"] = -model.score_samples(X)
    df["outlier"] = model.predict(X) == -1
    means, stds = X.mean(axis=0), X.std(axis=0) + 1e-9
    flags = []
    for r in df[df.outlier].sort_values("score", ascending=False).itertuples():
        z = (np.array([getattr(r, f) for f in features], dtype=float) - means) / stds
        top = [features[i] for i in np.argsort(-np.abs(z))[:2]]
        gstin, name = counterparty(r._asdict())
        flags.append(
            Flag(
                "outlier",
                r.invoice_id,
                r.invoice_no,
                name,
                gstin,
                "Unusual invoice",
                recorded=", ".join(f"{t.replace('_', ' ')} {getattr(r, t):.1f}" for t in top),
                expected="Typical for this party",
                impact=0.0,
                severity="low",
                evidence=evidence(
                    f"Isolation Forest ranks {r.invoice_no} among the most unusual "
                    f"{config.ISOFOREST_CONTAMINATION:.0%} of invoices "
                    f"(score {r.score:.2f}); stands out on {' and '.join(top)}.",
                    {t: float(getattr(r, t)) for t in top},
                    {},
                    [],
                ),
            )
        )
    return df[["invoice_id", "score", "outlier"]].reset_index(drop=True), flags
