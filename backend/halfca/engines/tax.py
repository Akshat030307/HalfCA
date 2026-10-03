"""Tax verifier: rate by HSN and date of supply, tax head by states, arithmetic."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from halfca import config, fmt
from halfca.data.model import money

from .common import Flag, chain, counterparty, evidence

ABOLISHED = (12.0, 28.0)


def head_label(head: str) -> str:
    return "CGST + SGST" if head == "cgst_sgst" else "IGST"


@dataclass
class TaxResult:
    flags: list[Flag]
    expected: pd.DataFrame  # invoice_id, expected_rate, expected_head, expected_tax/cgst/sgst/igst


def _rate_lookup(hsn_rates: pd.DataFrame, hsn: str, on: pd.Timestamp) -> float | None:
    rows = hsn_rates[hsn_rates.hsn == hsn]
    for r in rows.itertuples():
        start = pd.Timestamp(r.effective_from)
        end = pd.Timestamp(r.effective_to) if pd.notna(r.effective_to) else None
        if start <= on and (end is None or on <= end):
            return float(r.rate)
    return None


def verify(invoices: pd.DataFrame, hsn_rates: pd.DataFrame) -> TaxResult:
    flags: list[Flag] = []
    expected_rows = []
    gst2 = pd.Timestamp(config.GST2_EFFECTIVE)
    for r in invoices.itertuples():
        row = r._asdict()
        gstin, name = counterparty(row)
        recorded_tax = money(r.cgst + r.sgst + r.igst)
        recorded_head = "igst" if r.igst > 0 else "cgst_sgst"
        exp_rate = _rate_lookup(hsn_rates, r.hsn, r.invoice_date)
        exp_head = "cgst_sgst" if r.supplier_state == r.place_of_supply else "igst"
        rate_for_tax = exp_rate if exp_rate is not None else r.rate
        exp_tax = money(r.taxable_value * rate_for_tax / 100)
        half = money(exp_tax / 2)
        expected_rows.append(
            {
                "invoice_id": r.invoice_id,
                "expected_rate": exp_rate,
                "expected_head": exp_head,
                "expected_tax": exp_tax,
                "expected_igst": exp_tax if exp_head == "igst" else 0.0,
                "expected_cgst": half if exp_head == "cgst_sgst" else 0.0,
                "expected_sgst": money(exp_tax - half) if exp_head == "cgst_sgst" else 0.0,
                "recorded_tax": recorded_tax,
                "recorded_head": recorded_head,
            }
        )
        link = chain(
            "invoice",
            r.invoice_id,
            f"Invoice {r.invoice_no}",
            hsn=r.hsn,
            description=r.description,
            date=r.invoice_date,
            taxable=r.taxable_value,
            rate=r.rate,
            cgst=r.cgst,
            sgst=r.sgst,
            igst=r.igst,
        )
        is_itc = r.direction == "inward"

        if exp_rate is not None and abs(r.rate - exp_rate) > 1e-6:
            notes = [
                f"Rate checked against HSN {r.hsn} on the date of supply "
                f"({fmt.day_long(r.invoice_date)})."
            ]
            if r.rate in ABOLISHED and r.invoice_date >= gst2:
                notes.insert(0, f"The {r.rate:g}% slab was abolished by GST 2.0 on 22 Sep 2025.")
            flags.append(
                Flag(
                    "tax_rate",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Abolished slab still charged"
                    if r.rate in ABOLISHED and r.invoice_date >= gst2
                    else "Wrong GST rate",
                    recorded=f"{fmt.pct(r.rate)} · {fmt.inr(recorded_tax)}",
                    expected=f"{fmt.pct(exp_rate)} · {fmt.inr(exp_tax)}",
                    impact=recorded_tax if is_itc else abs(exp_tax - recorded_tax),
                    severity="high",
                    evidence=evidence(
                        f"HSN {r.hsn} ({r.description}) is {fmt.pct(exp_rate)} on "
                        f"{fmt.day_long(r.invoice_date)}; the invoice charges {fmt.pct(r.rate)}.",
                        {"rate": r.rate, "tax": recorded_tax},
                        {"rate": exp_rate, "tax": exp_tax},
                        [link],
                        notes,
                    ),
                )
            )
        if recorded_tax > 0 and recorded_head != exp_head:
            where = (
                "Delhi → Delhi"
                if r.supplier_state == r.place_of_supply == "07"
                else (f"state {r.supplier_state} → state {r.place_of_supply}")
            )
            title = (
                "IGST on an intra-state supply"
                if exp_head == "cgst_sgst"
                else "CGST + SGST on an inter-state supply"
            )
            exp_text = (
                f"CGST + SGST {fmt.pct(rate_for_tax / 2)} + {fmt.pct(rate_for_tax / 2)}"
                if exp_head == "cgst_sgst"
                else f"IGST {fmt.pct(rate_for_tax)}"
            )
            rec_text = (
                f"IGST {fmt.pct(r.rate)} · {fmt.inr(r.igst)}"
                if recorded_head == "igst"
                else f"CGST + SGST · {fmt.inr(r.cgst + r.sgst)}"
            )
            flags.append(
                Flag(
                    "tax_head",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    title,
                    recorded=rec_text,
                    expected=exp_text,
                    impact=recorded_tax,
                    severity="high",
                    evidence=evidence(
                        f"Supplier state {r.supplier_state} and place of supply "
                        f"{r.place_of_supply} "
                        f"({where}) mean {head_label(exp_head)}.",
                        {"head": recorded_head, "tax": recorded_tax},
                        {"head": exp_head},
                        [link],
                        [
                            "Tax paid under the wrong head is not adjusted automatically; "
                            "it must be paid under the right head and the wrong one claimed back."
                        ],
                    ),
                )
            )
        arith = money(r.taxable_value * r.rate / 100)
        if abs(arith - recorded_tax) > config.TAX_ARITH_TOL:
            flags.append(
                Flag(
                    "tax_arith",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Tax does not add up",
                    recorded=f"Tax {fmt.inr(recorded_tax)}",
                    expected=f"{fmt.inr(r.taxable_value)} × {fmt.pct(r.rate)} = {fmt.inr(arith)}",
                    impact=abs(arith - recorded_tax),
                    severity="medium",
                    evidence=evidence(
                        "Recomputed tax differs from the tax on the invoice.",
                        {"tax": recorded_tax},
                        {"tax": arith},
                        [link],
                    ),
                )
            )
        days_from_switch = abs((r.invoice_date - gst2).days)
        if days_from_switch <= config.TRANSITION_WINDOW_DAYS:
            flags.append(
                Flag(
                    "transition_review",
                    r.invoice_id,
                    r.invoice_no,
                    name,
                    gstin,
                    "Near the GST 2.0 switch-over",
                    recorded=fmt.day_long(r.invoice_date),
                    expected="Review by hand",
                    impact=0.0,
                    severity="low",
                    evidence=evidence(
                        f"Supplied {days_from_switch} days from 22 Sep 2025; which "
                        "rate applies depends on time of supply. Flagged for review, "
                        "never auto-decided.",
                        {},
                        {},
                        [link],
                    ),
                )
            )
    return TaxResult(flags, pd.DataFrame(expected_rows))
