"""Structured ingestion: the five source files (and reference data) into DataFrames.

This is the primary path (the demo uses it). PDF/image invoices go through
ingest/llm_extract.py instead and land in the same invoice columns.
All timestamps are kept as naive IST, which is what every source here uses.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd

SOURCE_KINDS = ("invoices", "bank", "ledger", "ims", "eway")

ID_COLUMNS = {
    "invoice_id",
    "invoice_no",
    "supplier_gstin",
    "buyer_gstin",
    "supplier_state",
    "place_of_supply",
    "hsn",
    "ewb_no",
    "txn_id",
    "utr",
    "voucher_no",
    "party_gstin",
    "reference",
    "ims_id",
    "gstin",
    "pan",
    "state_code",
    "seller_gstin",
    "phone",
    "bank_account",
    "vehicle_no",
    "plaza_id",
    "route_id",
    "doc_no",
    "from_state",
    "to_state",
    "recipient_gstin",
    "crossing_id",
}


REQUIRED = {
    "invoices": [
        "invoice_no",
        "invoice_date",
        "direction",
        "supplier_gstin",
        "supplier_name",
        "buyer_gstin",
        "buyer_name",
        "supplier_state",
        "place_of_supply",
        "hsn",
        "taxable_value",
        "rate",
        "cgst",
        "sgst",
        "igst",
        "total",
    ],
    "bank": ["txn_id", "txn_date", "direction", "amount", "counterparty", "narration"],
}


def _require(df: pd.DataFrame, kind: str, path: Path) -> None:
    missing = [c for c in REQUIRED[kind] if c not in df.columns]
    if missing:
        raise ValueError(
            f"{path.name} does not look like a {kind} file: missing {', '.join(missing)}"
        )


def detect_kind(name: str, head: str = "") -> str | None:
    """Which source a file is, from its name first and its first bytes second."""
    n = name.lower()
    if n.endswith(".xml") or "<ENVELOPE" in head[:200]:
        return "ledger"
    if "eway" in n or "e-way" in n or '"eway_bills"' in head:
        return "eway"
    if "ims" in n or '"records"' in head:
        return "ims"
    if "hdfc" in n or "bank" in n or "statement" in n or head.startswith("txn_id"):
        return "bank"
    if "invoice" in n or head.startswith("invoice_id") or head.startswith("invoice_no"):
        return "invoices"
    return None


def _typed(
    df: pd.DataFrame, dates: tuple[str, ...] = (), stamps: tuple[str, ...] = ()
) -> pd.DataFrame:
    for col in df.columns:
        if col in ID_COLUMNS:
            df[col] = df[col].astype("string").replace({"": pd.NA})
    for col in dates:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    for col in stamps:
        if col in df.columns:
            ts = pd.to_datetime(df[col], errors="coerce", utc=True)
            df[col] = ts.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    return df


def read_invoices(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={c: "string" for c in ID_COLUMNS}, keep_default_na=False)
    _require(df, "invoices", path)
    for col in ("qty", "unit_price", "taxable_value", "rate", "cgst", "sgst", "igst", "total"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df.columns else 0.0
    for col, default in (("description", ""), ("unit", "nos"), ("ewb_no", pd.NA)):
        if col not in df.columns:
            df[col] = default
    if "invoice_id" not in df.columns:
        df.insert(0, "invoice_id", [f"u{i:04d}" for i in range(1, len(df) + 1)])
    return _typed(df, dates=("invoice_date",))


def read_bank(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={c: "string" for c in ID_COLUMNS}, keep_default_na=False)
    _require(df, "bank", path)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    return _typed(df, dates=("txn_date",))


def read_tally(path: Path) -> pd.DataFrame:
    rows = []
    for v in ET.parse(path).getroot().iter("VOUCHER"):
        entry = v.find("ALLLEDGERENTRIES.LIST")
        raw = float(entry.findtext("AMOUNT", "0")) if entry is not None else 0.0
        debit = entry is not None and entry.findtext("ISDEEMEDPOSITIVE") == "Yes"
        amount = abs(raw)
        d = v.findtext("DATE", "")
        rows.append(
            {
                "voucher_no": v.findtext("VOUCHERNUMBER"),
                "voucher_type": v.findtext("VOUCHERTYPENAME") or v.get("VCHTYPE"),
                "voucher_date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "party_name": v.findtext("PARTYLEDGERNAME"),
                "party_gstin": v.findtext("PARTYGSTIN"),
                "reference": v.findtext("REFERENCE"),
                "amount": amount,
                "debit": amount if debit else 0.0,
                "credit": 0.0 if debit else amount,
                "narration": v.findtext("NARRATION"),
            }
        )
    return _typed(pd.DataFrame(rows), dates=("voucher_date",))


def read_ims(path: Path) -> pd.DataFrame:
    payload = json.loads(path.read_text())
    df = pd.DataFrame(payload["records"])
    return _typed(df, dates=("invoice_date", "filed_on"))


def read_eway(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(path.read_text())
    ewb = _typed(
        pd.DataFrame(payload["eway_bills"]),
        dates=("doc_date",),
        stamps=("generated_at", "valid_until"),
    )
    crossings = _typed(pd.DataFrame(payload["toll_crossings"]), stamps=("crossed_at",))
    return ewb, crossings


def read_sources(paths: Iterable[Path]) -> dict[str, pd.DataFrame]:
    """Load whichever source files are given, keyed by table name."""
    frames: dict[str, pd.DataFrame] = {}
    for path in paths:
        head = path.read_text(errors="ignore")[:400]
        kind = detect_kind(path.name, head)
        if kind == "invoices":
            frames["invoices"] = read_invoices(path)
        elif kind == "bank":
            frames["bank"] = read_bank(path)
        elif kind == "ledger":
            frames["ledger"] = read_tally(path)
        elif kind == "ims":
            frames["ims"] = read_ims(path)
        elif kind == "eway":
            frames["eway_bills"], frames["toll_crossings"] = read_eway(path)
    return frames


def read_reference(folder: Path) -> dict[str, pd.DataFrame]:
    cp = pd.read_csv(
        folder / "counterparties.csv",
        dtype={c: "string" for c in ID_COLUMNS},
        keep_default_na=False,
    )
    for col in ("ewb_count_90d", "turnover_3m_avg", "turnover_month", "returns_missed_6m", "tier"):
        cp[col] = pd.to_numeric(cp[col], errors="coerce")
    up = pd.read_csv(
        folder / "upstream_invoices.csv",
        dtype={c: "string" for c in ID_COLUMNS},
        keep_default_na=False,
    )
    up["value"] = pd.to_numeric(up["value"], errors="coerce")
    hsn = pd.read_csv(folder / "hsn_rates.csv", dtype={"hsn": "string"}, keep_default_na=False)
    hsn["rate"] = pd.to_numeric(hsn["rate"], errors="coerce")
    hsn["effective_to"] = hsn["effective_to"].replace({"": None})
    return {
        "counterparties": _typed(cp, dates=("registered_on",)),
        "upstream_invoices": _typed(up, dates=("invoice_date",)),
        "hsn_rates": _typed(hsn, dates=("effective_from", "effective_to")),
    }


def read_folder(folder: Path) -> dict[str, pd.DataFrame]:
    """A generated dataset folder: sources/ + reference/ (+ truth/ when present)."""
    frames = read_sources(sorted((folder / "sources").iterdir()))
    frames.update(read_reference(folder / "reference"))
    truth = folder / "truth" / "truth_labels.csv"
    if truth.is_file():
        frames["truth_labels"] = pd.read_csv(truth, dtype="string", keep_default_na=False)
    return frames
