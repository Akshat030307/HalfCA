"""Field differences on matched pairs, duplicate invoices, and missing links (gaps)."""

from __future__ import annotations

from datetime import date

import pandas as pd
from rapidfuzz.distance import Levenshtein

from halfca import config, fmt

from .common import Flag, chain, counterparty, evidence


def _inv_link(r: pd.Series) -> dict:
    return chain(
        "invoice",
        r.invoice_id,
        f"Invoice {r.invoice_no}",
        invoice_no=r.invoice_no,
        date=r.invoice_date,
        total=r.total,
        party=counterparty(r)[1],
    )


def _ledger_link(v: pd.Series) -> dict:
    return chain(
        "ledger",
        v.voucher_no,
        f"Tally {v.voucher_type} {v.voucher_no}",
        reference=v.reference,
        date=v.voucher_date,
        amount=v.amount,
        party=v.party_name,
        party_gstin=v.party_gstin,
    )


# ── duplicates ───────────────────────────────────────────────────────────────


def find_duplicates(invoices: pd.DataFrame) -> tuple[list[Flag], dict[str, str]]:
    """Exact: same party + number + amount. Near: same party + amount, number within edit
    distance 2, dated within 5 days. The later copy is flagged; returns copy → original."""
    flags: list[Flag] = []
    dup_of: dict[str, str] = {}
    df = invoices.assign(
        _party=[counterparty(r)[0] for _, r in invoices.iterrows()], _amt=invoices.total.round(0)
    )
    for _, grp in df.groupby(["direction", "_party", "_amt"], sort=True):
        if len(grp) < 2:
            continue
        rows = grp.sort_values(["invoice_date", "invoice_id"]).reset_index(drop=True)
        for j in range(1, len(rows)):
            b = rows.iloc[j]
            if b.invoice_id in dup_of:
                continue
            for i in range(j):
                a = rows.iloc[i]
                if a.invoice_id in dup_of:
                    continue
                days = abs((b.invoice_date - a.invoice_date).days)
                dist = Levenshtein.distance(a.invoice_no, b.invoice_no)
                exact = a.invoice_no == b.invoice_no
                if not exact and not (
                    dist <= config.NEARDUP_EDIT_MAX and days <= config.NEARDUP_DATE_DAYS
                ):
                    continue
                dup_of[b.invoice_id] = a.invoice_id
                _, name = counterparty(b)
                kind = "duplicate" if exact else "near_duplicate"
                why = (
                    f"Same number {b.invoice_no}, same amount {fmt.inr(b.total)}"
                    if exact
                    else f"Same supplier, same amount, invoice number edit distance {dist}, "
                    f"{days} day{'s' if days != 1 else ''} apart"
                )
                flags.append(
                    Flag(
                        kind=kind,
                        invoice_id=b.invoice_id,
                        ref=b.invoice_no,
                        counterparty=name,
                        gstin=counterparty(b)[0],
                        title="Same invoice entered twice" if exact else "Same invoice, renumbered",
                        recorded=f"{b.invoice_no} · {fmt.day(b.invoice_date)} · {fmt.inr(b.total)}",
                        expected=f"One bill: {a.invoice_no} · {fmt.day(a.invoice_date)}",
                        impact=float(b.total),
                        severity="high",
                        evidence=evidence(
                            why,
                            {"invoice_no": b.invoice_no, "date": b.invoice_date},
                            {"original": a.invoice_no, "original_date": a.invoice_date},
                            [_inv_link(a), _inv_link(b)],
                            [f"Edit distance {dist}; {days} days apart."],
                        ),
                    )
                )
                break
    return flags, dup_of


# ── field diffs on matched pairs ─────────────────────────────────────────────


def field_diffs(
    invoices: pd.DataFrame,
    ledger: pd.DataFrame,
    pairs: pd.DataFrame,
    pay_links: pd.DataFrame,
    bank: pd.DataFrame,
    dup_of: dict[str, str],
) -> list[Flag]:
    flags: list[Flag] = []
    inv = invoices.set_index("invoice_id", drop=False)
    led = ledger.set_index("voucher_no", drop=False)
    for p in pairs.itertuples():
        if p.invoice_id in dup_of:
            continue
        r, v = inv.loc[p.invoice_id], led.loc[p.voucher_no]
        gstin, name = counterparty(r)
        links = [_inv_link(r), _ledger_link(v)]
        diff = round(float(v.amount) - float(r.total), 2)
        if abs(diff) > config.DIFF_AMOUNT_TOL:
            flags.append(
                Flag(
                    "amount",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Books disagree with the invoice",
                    recorded=f"Books {fmt.inr(v.amount)}",
                    expected=f"Invoice {fmt.inr(r.total)}",
                    impact=abs(diff),
                    evidence=evidence(
                        f"Tally {v.voucher_no} records {fmt.inr(v.amount)} against an "
                        f"invoice of {fmt.inr(r.total)} ({fmt.inr(diff)}).",
                        {"books_amount": v.amount},
                        {"invoice_total": r.total},
                        links,
                    ),
                )
            )
        days = (pd.Timestamp(v.voucher_date) - pd.Timestamp(r.invoice_date)).days
        if abs(days) > config.DIFF_DATE_DAYS:
            flags.append(
                Flag(
                    "date",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Booked on a different date",
                    recorded=f"Books {fmt.day(v.voucher_date)}",
                    expected=f"Invoice {fmt.day(r.invoice_date)}",
                    impact=0.0,
                    severity="low",
                    evidence=evidence(
                        f"Booked {abs(days)} days {'after' if days > 0 else 'before'} the "
                        f"invoice date (tolerance {config.DIFF_DATE_DAYS} days).",
                        {"books_date": v.voucher_date},
                        {"invoice_date": r.invoice_date},
                        links,
                    ),
                )
            )
        if p.stage == 2 and v.reference and v.reference != r.invoice_no:
            flags.append(
                Flag(
                    "invoice_id",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Invoice number typed differently",
                    recorded=f"Books '{v.reference}'",
                    expected=f"Invoice '{r.invoice_no}'",
                    impact=0.0,
                    severity="low",
                    evidence=evidence(
                        f"'{v.reference}' and '{r.invoice_no}' are the same number once "
                        "separators, case, leading zeros and FY suffixes are ignored.",
                        {"books_reference": v.reference},
                        {"invoice_no": r.invoice_no},
                        links,
                    ),
                )
            )

    # Payment amount vs invoice (short or excess payment).
    if len(pay_links):
        paid = pay_links.merge(bank[["txn_id", "amount", "txn_date", "narration"]], on="txn_id")
        for iid, grp in paid.groupby("invoice_id"):
            if iid in dup_of:
                continue
            r = inv.loc[iid]
            total_paid = float(grp.amount.sum())
            diff = round(total_paid - float(r.total), 2)
            if abs(diff) <= config.DIFF_AMOUNT_TOL:
                continue
            gstin, name = counterparty(r)
            links = [_inv_link(r)] + [
                chain(
                    "bank",
                    t.txn_id,
                    f"Bank {t.txn_id}",
                    date=t.txn_date,
                    amount=t.amount,
                    narration=t.narration,
                )
                for t in grp.itertuples()
            ]
            flags.append(
                Flag(
                    "amount",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Short payment" if diff < 0 else "Paid more than billed",
                    recorded=f"Paid {fmt.inr(total_paid)}",
                    expected=f"Invoice {fmt.inr(r.total)}",
                    impact=abs(diff),
                    evidence=evidence(
                        f"Bank shows {fmt.inr(total_paid)} against an invoice of "
                        f"{fmt.inr(r.total)} ({fmt.inr(diff)}).",
                        {"paid": total_paid},
                        {"invoice_total": r.total},
                        links,
                    ),
                )
            )
    return flags


# ── unmatched and gaps ───────────────────────────────────────────────────────


def unmatched_flags(unmatched: pd.DataFrame, pay_links: pd.DataFrame) -> list[Flag]:
    flags = []
    paid = set(pay_links.invoice_id) if len(pay_links) else set()
    for r in unmatched.itertuples():
        gstin, name = counterparty(r._asdict())
        note = (
            "Money moved for it, but it was never booked."
            if r.invoice_id in paid
            else "No books entry and no payment."
        )
        flags.append(
            Flag(
                "unmatched",
                r.invoice_id,
                r.invoice_no,
                name,
                gstin,
                "No books entry",
                recorded=f"Invoice {fmt.inr(r.total)}",
                expected="A Tally voucher",
                impact=float(r.total),
                evidence=evidence(
                    f"No Purchase/Sales voucher pairs with {r.invoice_no} after all four "
                    f"matching stages. {note}",
                    {"invoice_total": r.total},
                    {},
                    [
                        chain(
                            "invoice",
                            r.invoice_id,
                            f"Invoice {r.invoice_no}",
                            invoice_no=r.invoice_no,
                            date=r.invoice_date,
                            total=r.total,
                        )
                    ],
                ),
            )
        )
    return flags


def gaps(
    invoices: pd.DataFrame,
    bank: pd.DataFrame,
    ims: pd.DataFrame,
    pairs: pd.DataFrame,
    pay_links: pd.DataFrame,
    ims_links: pd.DataFrame,
    dup_of: dict[str, str],
    as_of: date,
) -> list[Flag]:
    flags: list[Flag] = []
    booked = set(pairs.invoice_id)
    paid = set(pay_links.invoice_id) if len(pay_links) else set()
    on_ims = set(ims_links.invoice_id) if len(ims_links) else set()
    as_of_ts = pd.Timestamp(as_of)

    for r in invoices.itertuples():
        if r.invoice_id in dup_of:
            continue
        row = r._asdict()
        gstin, name = counterparty(row)
        age = (as_of_ts - r.invoice_date).days
        if r.invoice_id not in paid and age > config.PAYMENT_TERMS_DAYS:
            who = "You have not paid" if r.direction == "inward" else "The customer has not paid"
            flags.append(
                Flag(
                    "unpaid_aged",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Unpaid past terms",
                    recorded=f"{age} days, no payment",
                    expected=f"Paid within {config.PAYMENT_TERMS_DAYS} days",
                    impact=float(r.total),
                    severity="low",
                    evidence=evidence(
                        f"{who} {r.invoice_no} ({fmt.inr(r.total)}) {age} days after the "
                        "invoice date.",
                        {"age_days": age},
                        {},
                        [],
                    ),
                )
            )
        if r.direction == "inward" and r.invoice_id in booked and r.invoice_id not in on_ims:
            itc = float(r.cgst + r.sgst + r.igst)
            flags.append(
                Flag(
                    "not_in_ims",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Supplier has not filed it",
                    recorded="In your books",
                    expected="On IMS / GSTR-2B",
                    impact=itc,
                    evidence=evidence(
                        f"{name} has not reported {r.invoice_no} on IMS, so its ITC of "
                        f"{fmt.inr(itc)} cannot reach GSTR-2B. Chase the supplier.",
                        {},
                        {},
                        [],
                    ),
                )
            )

    linked_txns = set(pay_links.txn_id) if len(pay_links) else set()
    for t in bank.itertuples():
        if t.txn_id not in linked_txns:
            flags.append(
                Flag(
                    "payment_only",
                    None,
                    t.txn_id,
                    t.counterparty,
                    None,
                    "Money moved with no invoice",
                    recorded=("Paid " if t.direction == "debit" else "Received ")
                    + fmt.inr(t.amount),
                    expected="An invoice behind it",
                    impact=float(t.amount),
                    evidence=evidence(
                        f"Bank line {t.txn_id} on {fmt.day(t.txn_date)} ({t.narration}) "
                        "does not match any invoice.",
                        {},
                        {},
                        [
                            chain(
                                "bank",
                                t.txn_id,
                                f"Bank {t.txn_id}",
                                date=t.txn_date,
                                amount=t.amount,
                                narration=t.narration,
                            )
                        ],
                    ),
                )
            )

    linked_ims = set(ims_links.ims_id) if len(ims_links) else set()
    ims_to_inv = (
        dict(zip(ims_links.ims_id, ims_links.invoice_id, strict=True)) if len(ims_links) else {}
    )
    for rec in ims.itertuples():
        in_books = rec.ims_id in linked_ims and ims_to_inv[rec.ims_id] in booked
        if not in_books:
            itc = float(rec.cgst + rec.sgst + rec.igst)
            flags.append(
                Flag(
                    "ims_only",
                    None,
                    rec.ims_id,
                    rec.supplier_name,
                    rec.supplier_gstin,
                    "On IMS, not in your books",
                    recorded=f"IMS {rec.invoice_no}",
                    expected="A booked invoice",
                    impact=itc,
                    evidence=evidence(
                        f"{rec.supplier_name} filed {rec.invoice_no} ({fmt.inr(rec.total)}) "
                        "but it is not in your books. Left unactioned it is deemed accepted.",
                        {},
                        {},
                        [],
                    ),
                )
            )
    return flags
