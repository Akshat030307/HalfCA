"""Tiny record builders for hand-made engine fixtures."""

from __future__ import annotations

from typing import Any

import pandas as pd

from halfca.data.model import money

ME = "07AAKFA4821M1ZA"
SUPPLIER = "08AABFP1234K1Z5"  # Rajasthan
DELHI_SUPPLIER = "07AABFD1234K1Z1"


def invoice(
    iid: str,
    no: str,
    date: str,
    *,
    direction: str = "inward",
    party: str = SUPPLIER,
    party_name: str = "Patel Pipes",
    taxable: float = 10_000,
    rate: float = 18,
    head: str | None = None,
    hsn: str = "7307",
    ewb_no: str | None = None,
    tax: float | None = None,
) -> dict[str, Any]:
    supplier, buyer = (party, ME) if direction == "inward" else (ME, party)
    s_state, b_state = supplier[:2], buyer[:2]
    head = head or ("cgst_sgst" if s_state == b_state else "igst")
    t = money(taxable * rate / 100) if tax is None else tax
    cgst = money(t / 2) if head == "cgst_sgst" else 0.0
    return {
        "invoice_id": iid,
        "invoice_no": no,
        "invoice_date": pd.Timestamp(date),
        "direction": direction,
        "supplier_gstin": supplier,
        "supplier_name": party_name if direction == "inward" else "Arora",
        "supplier_state": s_state,
        "buyer_gstin": buyer,
        "buyer_name": "Arora" if direction == "inward" else party_name,
        "place_of_supply": b_state,
        "hsn": hsn,
        "description": "fittings",
        "qty": 1,
        "unit": "pcs",
        "unit_price": taxable,
        "taxable_value": taxable,
        "rate": rate,
        "cgst": cgst,
        "sgst": money(t - cgst) if head == "cgst_sgst" else 0.0,
        "igst": t if head == "igst" else 0.0,
        "total": money(taxable + t),
        "ewb_no": ewb_no,
    }


def voucher(
    no: str,
    date: str,
    party: str,
    amount: float,
    *,
    kind: str = "Purchase",
    gstin: str | None = SUPPLIER,
    ref: str | None = None,
) -> dict[str, Any]:
    return {
        "voucher_no": no,
        "voucher_type": kind,
        "voucher_date": pd.Timestamp(date),
        "party_name": party,
        "party_gstin": gstin,
        "reference": ref,
        "amount": amount,
        "debit": 0.0,
        "credit": amount,
        "narration": f"Being goods vide {ref}",
    }


def txn(
    tid: str, date: str, amount: float, name: str, ref: str = "", *, direction: str = "debit"
) -> dict[str, Any]:
    return {
        "txn_id": tid,
        "txn_date": pd.Timestamp(date),
        "direction": direction,
        "amount": amount,
        "counterparty": name.upper(),
        "narration": f"NEFT DR-{name.upper()}" + (f"-{ref}" if ref else ""),
        "utr": None,
        "mode": "NEFT",
    }


def ims_record(ims_id: str, inv: dict[str, Any]) -> dict[str, Any]:
    return {
        "ims_id": ims_id,
        "supplier_gstin": inv["supplier_gstin"],
        "supplier_name": inv["supplier_name"],
        "invoice_no": inv["invoice_no"],
        "invoice_date": inv["invoice_date"],
        "invoice_type": "R",
        "place_of_supply": "07",
        "taxable_value": inv["taxable_value"],
        "rate": inv["rate"],
        "igst": inv["igst"],
        "cgst": inv["cgst"],
        "sgst": inv["sgst"],
        "total": inv["total"],
        "return_period": "092026",
        "filed_on": inv["invoice_date"],
        "status": "No action",
    }


def frame(rows: list[dict[str, Any]], columns: list[str] | None = None) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=columns) if not rows and columns else pd.DataFrame(rows)


def hsn_rates() -> pd.DataFrame:
    from halfca.data.hsn import table_rows

    df = pd.DataFrame(table_rows())
    df["effective_from"] = pd.to_datetime(df.effective_from)
    df["effective_to"] = pd.to_datetime(df.effective_to)
    return df
