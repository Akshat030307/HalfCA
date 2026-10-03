from __future__ import annotations

from datetime import date

import pandas as pd

from halfca.ai.ims_autopilot import decide
from halfca.data.network import digit_counts_benford
from halfca.engines import anomaly, liability
from halfca.engines.common import Flag
from halfca.engines.tax import verify

from .factories import frame, hsn_rates, ims_record, invoice


# ── Benford ──
def _upstream(gstin: str, counts: list[int]) -> list[dict]:
    rows = []
    for d, c in enumerate(counts, start=1):
        rows += [{"seller_gstin": gstin, "buyer_gstin": "X", "value": (d + 0.5) * 10**5}] * c
    return rows


def test_benford_conforming_vs_not() -> None:
    up = frame(
        _upstream("GOOD", digit_counts_benford(72))
        + _upstream("BAD", [11, 7, 6, 7, 9, 9, 9, 3, 3])
        + _upstream("SMALL", [5] * 9)
    )
    empty = frame([invoice("a", "A/1", "2026-09-01")]).iloc[0:0]
    table, flags = anomaly.benford(up, empty, {}, {"BAD": "Kaveri"})
    t = table.set_index("gstin")
    assert not t.loc["GOOD"].nonconforming and t.loc["BAD"].nonconforming
    assert round(t.loc["BAD"].mad, 3) == 0.051
    assert "SMALL" not in t.index  # 45 invoices: below the 50-invoice screening threshold
    assert [f.counterparty for f in flags] == ["Kaveri"]


def test_threshold_hugging() -> None:
    def rows(party: str, totals: list[float]) -> list[dict]:
        return [
            invoice(f"{party}{i}", f"{party}/{i}", "2026-09-05", party=party, taxable=t / 1.18)
            for i, t in enumerate(totals)
        ]

    hug = rows("08H", [46_000, 47_500, 49_000, 49_900, 12_000, 80_000])
    normal = rows("08N", [46_000, 12_000, 80_000, 30_000, 25_000, 70_000])
    flags = anomaly.threshold_hugging(frame(hug + normal), {})
    assert [f.ref for f in flags] == ["08H"]


# ── Liability ──
def test_liability_under_and_over_charges() -> None:
    over = invoice(
        "o1",
        "AR/S/1",
        "2026-09-05",
        direction="outward",
        party="07AABCX0000A1Z1",
        hsn="2523",
        rate=28,
        taxable=10_000,
    )  # 28% where 18% is due: still owed
    under = invoice(
        "o2",
        "AR/S/2",
        "2026-09-05",
        direction="outward",
        party="07AABCX0000A1Z1",
        hsn="7307",
        rate=12,
        taxable=10_000,
    )  # 12% where 18% is due: ₹600 short
    invs = frame([over, under])
    exp = verify(invs, hsn_rates()).expected
    dec = frame(
        [
            {"decision": "Accept", "igst": 1_000.0, "cgst": 0.0, "sgst": 0.0},
            {"decision": "Reject", "igst": 300.0, "cgst": 0.0, "sgst": 0.0},
            {"decision": "Pending", "igst": 200.0, "cgst": 0.0, "sgst": 0.0},
        ]
    )
    s = liability.compute(invs, dec, exp, {}).summary
    assert s["output_tax_filed"] == 2_800 + 1_200
    assert s["under_reported_output"] == 600
    assert s["output_tax_reconciled"] == 2_800 + 1_800
    assert (s["itc_claimed"], s["itc_eligible"]) == (1_500, 1_000)
    assert s["exposure"] == 300 + 200 + 600


# ── IMS Autopilot: first matching rule wins ──
def test_autopilot_rules() -> None:
    a = invoice("a", "A/1", "2026-09-01")  # clean
    b = invoice("b", "B/1", "2026-09-01")  # wrong tax and failed road: tax wins
    c = invoice("c", "C/1", "2026-09-01")  # failed road
    d = invoice("d", "D/1", "2026-09-01", party="06KAV")  # tainted supplier
    e = invoice("e", "E/1", "2026-09-01")  # never booked
    invs = frame([a, b, c, d, e])
    ims = frame([ims_record(f"m{x['invoice_id']}", x) for x in [a, b, c, d, e]])
    links = frame([{"ims_id": f"m{x}", "invoice_id": x} for x in "abcde"])

    def flag(kind: str, iid: str, title: str = "t") -> Flag:
        return Flag(kind, iid, iid, "p", None, title, "12% · ₹1", "18% · ₹2", 0.0)

    flags = {
        "b": [flag("paper_only", "b"), flag("tax_rate", "b", "Abolished slab still charged")],
        "c": [flag("paper_only", "c")],
    }
    out = decide(ims, links, {"a", "b", "c", "d"}, flags, pd.DataFrame(), {"06KAV": 0.82}, invs)
    got = dict(zip(out.invoice_id, zip(out.decision, out.rule, strict=True), strict=True))
    assert got == {
        "a": ("Accept", "clean"),
        "b": ("Reject", "tax_wrong"),
        "c": ("Reject", "road_failed"),
        "d": ("Pending", "supplier_taint"),
        "e": ("Pending", "not_matched"),
    }
    assert out.set_index("invoice_id").reason["b"] == "Charged abolished 12% slab · expected 18%"


def test_outliers_flag_a_small_share() -> None:
    rows = [
        invoice(f"i{i}", f"S/{i}", f"2026-09-{1 + i % 28:02d}", taxable=10_000 + 37 * i)
        for i in range(120)
    ]
    rows.append(invoice("weird", "S/9999", "2026-09-06", taxable=4_000_000))
    table, flags = anomaly.outliers(
        frame(rows),
        frame([], ["txn_id", "invoice_id", "method"]),
        frame([], ["txn_id", "txn_date"]),
        {},
        date(2026, 10, 10),
    )
    assert 1 <= len(flags) <= 6
    assert "weird" in {f.invoice_id for f in flags}
