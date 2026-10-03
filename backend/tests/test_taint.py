"""Credit taint on a toy network: ring A→B→C→A feeds supplier K, which sells to the user U."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from halfca.engines.taint import analyse

from .factories import frame, invoice

U = "07AAKFA4821M1ZA"


def firm(gstin: str, name: str, **kw: object) -> dict:
    base = {
        "gstin": gstin,
        "pan": f"P{gstin}",
        "name": name,
        "city": "Delhi",
        "state_code": gstin[:2],
        "role": "upstream",
        "registered_on": pd.Timestamp("2015-01-01"),
        "address": f"addr {gstin}",
        "phone": f"ph {gstin}",
        "bank_account": f"bk {gstin}",
        "status": "Active",
        "ewb_count_90d": 40,
        "turnover_3m_avg": 1e6,
        "turnover_month": 1e6,
        "returns_missed_6m": 0,
        "tier": 1,
        "tags": "",
    }
    base.update(kw)
    return base


def up(seller: str, buyer: str, n: int = 2) -> list[dict]:
    return [
        {
            "seller_gstin": seller,
            "buyer_gstin": buyer,
            "invoice_no": f"{seller}-{i}",
            "invoice_date": pd.Timestamp("2026-08-01"),
            "month": "2026-08",
            "hsn": "7208",
            "value": 100_000.0,
        }
        for i in range(n)
    ]


@pytest.fixture()
def network():
    cp = frame(
        [
            firm(U, "You", role="self"),
            firm("06K", "Kaveri"),
            firm("06A", "Alpha", registered_on=pd.Timestamp("2026-08-30")),
            firm("06B", "Beta", ewb_count_90d=0),
            firm("06C", "Gamma", turnover_month=1e7),
            firm("06S", "Clean Supplier"),
            firm(
                "06N",
                "Newish",
                registered_on=pd.Timestamp("2026-09-01"),
                returns_missed_6m=1,
                address="shared",
            ),
            firm("06M", "Mate", address="shared"),
            firm("06X", "Far1"),
            firm("06Y", "Far2"),
            firm("06Z", "Far3"),
            firm("06W", "Far4"),
        ]
    )
    upstream = frame(
        up("06A", "06B")
        + up("06B", "06C")
        + up("06C", "06A")
        + up("06C", "06K")
        + up("06N", "06S")
        + up("06M", "06S")
        # A ring far upstream (more than 3 hops from the user) is not ours to worry about.
        + up("06X", "06Y")
        + up("06Y", "06X")
        + up("06Y", "06W")
        + up("06W", "06Z")
        + up("06Z", "06N")
    )
    invs = frame(
        [
            invoice("k1", "K/1", "2026-09-01", party="06K", party_name="Kaveri", taxable=100_000),
            invoice("s1", "S/1", "2026-09-02", party="06S", party_name="Clean Supplier"),
        ]
    )
    return analyse(cp, upstream, invs, U, date(2026, 10, 10), {})


def test_ring_found_and_far_ring_ignored(network) -> None:
    assert [sorted(c) for c in network.cycles] == [["06A", "06B", "06C"]]


def test_propagation(network) -> None:
    r = network.risk
    assert r["06A"] == r["06B"] == r["06C"] == pytest.approx(0.91)
    assert r["06K"] == pytest.approx(0.819)
    assert round(r["06K"], 2) == 0.82
    assert network.at_risk == {"06K"}


def test_signals_and_caps(network) -> None:
    nodes = network.nodes.set_index("gstin")
    # Newish: new registration 0.3 + filing gaps 0.2 + shared address 0.2 = 0.7 own risk.
    assert nodes.loc["06N"].own_risk == pytest.approx(0.7)
    # The clean supplier inherits 0.9 × 0.7 = 0.63, below the at-risk line.
    assert nodes.loc["06S"].risk == pytest.approx(0.63)
    assert "Registered 41 days ago" in nodes.loc["06A"].signals
    assert "Zero e-way bills" in nodes.loc["06B"].signals
    assert "Turnover +900%" in nodes.loc["06C"].signals


def test_flag_explains_the_path(network) -> None:
    (f,) = network.flags
    assert f.kind == "ring_taint" and f.ref == "06K"
    assert f.recorded == "Taint 0.82"
    assert [link["id"] for link in f.evidence["chain"][:2]] == ["06C", "06K"]
    assert "2 hops downstream" in f.evidence["summary"]
