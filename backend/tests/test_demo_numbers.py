"""The demo table in CLAUDE.md, found by the engines (seed 2609, period 2026-09).

Never "fix" a failure here by editing an expected value: fix the generator or the engine.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from halfca.pipeline import Reconciliation


def lakh(x: float) -> float:
    return round(x / 1e5, 1)


def flags_for(r: Reconciliation, kind: str) -> pd.DataFrame:
    f = r.tables["flags"]
    return f[f.kind == kind]


def inv_row(r: Reconciliation, no: str) -> pd.Series:
    inv = r.tables["invoices"]
    rows = inv[inv.invoice_no == no]
    assert len(rows) == 1, no
    return rows.iloc[0]


def test_headline_counts(demo: Reconciliation) -> None:
    s = demo.summary
    assert s["reconciled"] == 552
    assert (s["matched"], s["discrepancies"], s["duplicates"], s["unmatched"]) == (489, 38, 7, 18)
    assert round(s["clean_match_pct"] * 100, 1) == 88.6


def test_funnel(demo: Reconciliation) -> None:
    f = demo.tables["funnel"]
    assert list(f.records_in) + [int(f.left.iloc[-1])] == [552, 61, 23, 20, 18]
    assert list(f.paired) == [491, 38, 3, 2]
    assert not f.skipped.any()


def test_discrepancy_types(demo: Reconciliation) -> None:
    t = demo.summary["discrepancy_types"]
    assert (t["amount"], t["tax_rate"], t["invoice_id"], t["date"], t["tax_head"]) == (
        11,
        9,
        8,
        6,
        4,
    )
    assert demo.summary["tax_errors"] == {"inward": 6, "outward": 7}


def test_physical_trail(demo: Reconciliation) -> None:
    p = demo.summary["physical"]
    assert p["failed"] == 5 and p["failed_inside_matched"] == 5
    phys = demo.tables["physical"].set_index("invoice_no")
    assert phys.loc["MB/0877"].verdict == "paper_only"
    assert phys.loc["MB/0877"].window_hours == 72
    kn = phys.loc["KN/1502"]
    assert kn.verdict == "impossible_journey"
    assert (kn.distance_km, round(kn.speed_kmh), round(kn.trip_minutes)) == (480, 158, 182)
    for no in ("JP/1187", "JP/1188", "JP/1192"):
        assert phys.loc[no].verdict == "recycled_ewb"
    ld = phys.loc["LD/2291"]
    assert (ld.verdict, ld.tolls_crossed, round(ld.trip_minutes)) == ("verified", 3, 340)
    assert [c["plaza_name"] for c in json.loads(ld.crossings)] == ["Shambhu", "Bastara", "Panipat"]
    pp = phys.loc["PP/26/0912"]
    assert (pp.verdict, pp.tolls_crossed) == ("verified", 2)
    for no in ("MB/0877", "KN/1502", "JP/1187"):
        assert inv_row(demo, no).status == "matched"  # passes every paper check


def test_ring_and_taint(demo: Reconciliation) -> None:
    (ring,) = demo.summary["rings"]
    start = ring.index("Zenith Traders")  # cycles have no fixed start; compare the rotation
    assert ring[start:] + ring[:start] == [
        "Zenith Traders",
        "Arka Impex",
        "Nexo Metals",
        "Vrindam Trading",
        "Kairo Enterprises",
    ]
    nodes = demo.tables["taint_nodes"].set_index("name")
    assert round(nodes.loc["Kaveri Metals"].risk, 2) == 0.82
    assert nodes.loc["Kaveri Metals"].gstin == "06AAHCK3367Q1ZW"
    assert demo.summary["at_risk_suppliers"] == ["Kaveri Metals"]
    edges = demo.tables["taint_edges"]
    nexo = nodes.loc["Nexo Metals"].gstin
    assert ((edges.seller == nexo) & (edges.buyer == "06AAHCK3367Q1ZW")).any()
    signals = {
        n: json.loads(nodes.loc[n].signals)
        for n in ("Zenith Traders", "Nexo Metals", "Kairo Enterprises")
    }
    assert "Registered 41 days ago" in signals["Zenith Traders"]
    assert "Zero e-way bills on goods trade" in signals["Nexo Metals"]
    assert "Turnover +900%" in signals["Kairo Enterprises"]


def test_ims_autopilot(demo: Reconciliation) -> None:
    assert demo.summary["ims"] == {"records": 212, "accept": 197, "reject": 11, "pending": 4}
    ims = demo.tables["ims"]
    rejects = ims[ims.decision == "Reject"]
    assert (rejects.rule == "road_failed").sum() == 5 and (rejects.rule == "tax_wrong").sum() == 6
    pending = ims[ims.decision == "Pending"]
    assert set(pending.supplier_name) == {"Kaveri Metals"} and len(pending) == 4
    reason = ims.set_index("invoice_no").reason
    assert reason["MB/0877"] == "Goods not evidenced: 0 toll crossings"
    assert reason["KN/1502"] == "Impossible journey: 480 km in 3h 02m"
    assert reason["DF/0450"] == "Charged abolished 12% slab · expected 18%"
    assert reason["JP/1188"] == "Recycled e-way bill (trip used by JP/1187)"
    assert "circular-trading ring" in reason["KM/26/3341"]


@pytest.mark.parametrize(
    ("key", "lakh_value"),
    [
        ("itc_claimed", 18.6),
        ("itc_rejected", 1.1),
        ("itc_at_risk", 4.2),
        ("itc_eligible", 13.3),
        ("output_tax_filed", 25.4),
        ("net_payable_filed", 6.8),
        ("net_payable_reconciled", 12.1),
        ("exposure", 5.3),
    ],
)
def test_liability(demo: Reconciliation, key: str, lakh_value: float) -> None:
    assert lakh(demo.summary["liability"][key]) == lakh_value


def test_benford(demo: Reconciliation) -> None:
    b = demo.tables["benford"].set_index("name")
    assert (b.loc["Kaveri Metals"].n, round(b.loc["Kaveri Metals"].mad, 3)) == (64, 0.051)
    assert b.loc["Kaveri Metals"].nonconforming
    assert not b.loc["Sharma Steel"].nonconforming
    assert list(flags_for(demo, "benford").counterparty) == ["Kaveri Metals"]


def test_hero_flags(demo: Reconciliation) -> None:
    f = demo.tables["flags"].set_index("flag_id")
    rate = f.loc[f"tax_rate:{inv_row(demo, 'DF/0450').invoice_id}"]
    assert (rate.recorded, rate.expected) == ("12% · ₹7,020", "18% · ₹10,530")
    assert rate.title == "Abolished slab still charged"
    head = f.loc[f"tax_head:{inv_row(demo, 'AR/S/2219').invoice_id}"]
    assert head.title == "IGST on an intra-state supply"
    assert (head.recorded, head.expected) == ("IGST 18% · ₹21,600", "CGST + SGST 9% + 9%")
    dup = f.loc[f"near_duplicate:{inv_row(demo, 'INV/418').invoice_id}"]
    assert dup.title == "Same invoice, renumbered" and "INV-0418" in dup.expected
    assert inv_row(demo, "INV/418").duplicate_of == inv_row(demo, "INV-0418").invoice_id


def test_no_false_alarms(demo: Reconciliation) -> None:
    gaps = demo.summary["gaps"]
    assert gaps.get("payment_only", 0) == 0 and gaps.get("ims_only", 0) == 0
    assert gaps.get("not_in_ims") == 3
    assert "threshold_hugging" not in demo.summary["anomalies"]
