"""M1: the demo dataset itself carries every number in the CLAUDE.md demo table.

These checks read the generated files and truth labels directly. The engines that must
*find* these numbers on their own are tested in M2 (test_demo_numbers.py).
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import networkx as nx
import pandas as pd
import pytest
from rapidfuzz.distance import Levenshtein

from halfca import config
from halfca.data import build as data_build
from halfca.data import routes
from halfca.data.network import BENFORD, first_digit
from halfca.ingest.csv_loader import read_folder
from halfca.ingest.gstin import is_valid
from halfca.ingest.normalise import name_similarity, normalise_invoice_no


def lakh(x: float) -> float:
    return round(x / 1e5, 1)


@pytest.fixture(scope="module")
def demo(tmp_path_factory: pytest.TempPathFactory) -> dict[str, pd.DataFrame]:
    out = tmp_path_factory.mktemp("demo")
    data_build.run("demo", out=out)
    frames = read_folder(out)
    frames["_dir"] = out  # type: ignore[assignment]
    return frames


@pytest.fixture(scope="module")
def labels(demo: dict[str, pd.DataFrame]) -> dict[str, set[str]]:
    by_code: dict[str, set[str]] = {}
    for r in demo["truth_labels"].itertuples():
        by_code.setdefault(r.code, set()).add(r.invoice_id)
    return by_code


def test_volumes(demo: dict[str, pd.DataFrame]) -> None:
    inv = demo["invoices"]
    assert len(inv) == 552
    assert (inv.direction == "inward").sum() == 228
    assert (inv.direction == "outward").sum() == 324
    assert len(demo["ims"]) == 212
    assert 1_000 <= len(demo["toll_crossings"]) <= 2_000
    assert 1_400 <= len(demo["upstream_invoices"]) <= 2_400
    assert (
        len(demo["counterparties"][demo["counterparties"].role.isin(["supplier", "customer"])])
        == 120
    )


def test_planted_counts(labels: dict[str, set[str]]) -> None:
    n = {k: len(v) for k, v in labels.items()}
    assert (n["D01"], n["D04"], n["D03"], n["D02"], n["D05"]) == (11, 9, 8, 6, 4)  # 38
    assert n["D07"] + n["D08"] == 7  # duplicates
    assert n["D09"] == 18  # unmatched
    assert n["S2"] + n["D03"] == 38 and n["S3"] == 3 and n["S4"] == 2  # funnel stages 2-4
    road = labels["D12"] | labels["D13"] | labels["D14"]
    assert len(road) == 5
    assert n["D15"] == 4


def test_money(demo: dict[str, pd.DataFrame], labels: dict[str, set[str]]) -> None:
    inv = demo["invoices"].set_index("invoice_id")
    ims = demo["ims"]
    tax = ims.igst + ims.cgst + ims.sgst
    claimed = tax.sum()
    ims_ids = (
        inv[(inv.direction == "inward")]
        .reset_index()
        .merge(ims[["supplier_gstin", "invoice_no"]], on=["supplier_gstin", "invoice_no"])
        .invoice_id
    )
    rejects = set(ims_ids) & (
        labels["D04"] | labels["D05"] | labels["D12"] | labels["D13"] | labels["D14"]
    )
    assert len(rejects) == 11
    rejected = inv.loc[sorted(rejects), ["igst", "cgst", "sgst"]].sum().sum()
    at_risk = inv.loc[sorted(labels["D15"]), ["igst", "cgst", "sgst"]].sum().sum()
    out = inv[inv.direction == "outward"]
    output_tax = (out.igst + out.cgst + out.sgst).sum()
    eligible = claimed - rejected - at_risk

    assert lakh(claimed) == 18.6
    assert lakh(rejected) == 1.1
    assert lakh(at_risk) == 4.2
    assert lakh(eligible) == 13.3
    assert lakh(output_tax) == 25.4
    assert lakh(output_tax - claimed) == 6.8  # net payable as filed
    assert lakh(output_tax - eligible) == 12.1  # net payable reconciled
    assert lakh(rejected + at_risk) == 5.3  # exposure caught
    # IMS split: 197 accept · 11 reject · 4 pending
    assert len(ims) - len(rejects) - len(labels["D15"]) == 197


def _inv(demo: dict[str, pd.DataFrame], no: str) -> pd.Series:
    rows = demo["invoices"][demo["invoices"].invoice_no == no]
    assert len(rows) == 1, no
    return rows.iloc[0]


def test_hero_invoices(demo: dict[str, pd.DataFrame]) -> None:
    mb, kn, df_, ar = (_inv(demo, n) for n in ("MB/0877", "KN/1502", "DF/0450", "AR/S/2219"))
    assert (mb.supplier_name, mb.total) == ("Rohilkhand Alloys", 1_18_000)
    assert (kn.supplier_name, kn.total) == ("Ganga Wires", 1_41_600)
    for no in ("JP/1187", "JP/1188", "JP/1192"):
        assert _inv(demo, no).total == 59_000
    assert (df_.hsn, df_.rate, df_.igst, str(df_.invoice_date.date())) == (
        "7307",
        12,
        7_020,
        "2026-09-12",
    )
    assert (ar.buyer_name, ar.buyer_gstin[:2], ar.igst, ar.cgst) == (
        "Capital Hardware",
        "07",
        21_600,
        0,
    )
    a, b = _inv(demo, "INV-0418"), _inv(demo, "INV/418")
    assert a.total == b.total == 1_12_000
    assert (str(a.invoice_date.date()), str(b.invoice_date.date())) == ("2026-09-04", "2026-09-06")
    km = demo["invoices"][demo["invoices"].supplier_gstin == "06AAHCK3367Q1ZW"]
    assert {"KM/26/3341", "KM/26/3367"} <= set(km.invoice_no) and len(km) == 4
    assert lakh((km.igst + km.cgst + km.sgst).sum()) == 4.2


def _trip(demo: dict[str, pd.DataFrame], no: str) -> tuple[pd.Series, pd.DataFrame]:
    inv = _inv(demo, no)
    ewb = demo["eway_bills"].set_index("ewb_no").loc[inv.ewb_no]
    tc = demo["toll_crossings"]
    window = tc[
        (tc.vehicle_no == ewb.vehicle_no)
        & (tc.crossed_at >= ewb.generated_at)
        & (tc.crossed_at <= ewb.valid_until + pd.Timedelta(hours=48))
    ]
    return ewb, window.sort_values("crossed_at")


def _speed(ewb: pd.Series, crossings: pd.DataFrame) -> tuple[float, float]:
    route = routes.load().routes[ewb.route_id]
    km = {p.id: p.km for p in route.plazas}
    first, last = crossings.iloc[0], crossings.iloc[-1]
    hours = (last.crossed_at - first.crossed_at).total_seconds() / 3600
    speed = (km[last.plaza_id] - km[first.plaza_id]) / hours
    return speed, ewb.distance_km / speed * 60  # km/h, minutes for the whole leg


def test_road_heroes(demo: dict[str, pd.DataFrame]) -> None:
    ewb, x = _trip(demo, "LD/2291")
    assert (ewb.vehicle_no, ewb.route_id, len(x)) == ("PB10 GK 7731", "r1", 3)
    assert list(x.plaza_name) == ["Shambhu", "Bastara", "Panipat"]
    _, minutes = _speed(ewb, x)
    assert round(minutes) == 340  # 5h 40m

    ewb, x = _trip(demo, "KN/1502")
    speed, minutes = _speed(ewb, x)
    assert (ewb.distance_km, len(x), round(speed), round(minutes)) == (480, 3, 158, 182)  # 3h 02m

    ewb, x = _trip(demo, "MB/0877")
    window_h = (ewb.valid_until + pd.Timedelta(hours=48) - ewb.generated_at).total_seconds() / 3600
    assert (len(x), window_h, ewb.vehicle_no) == (0, 72, "UP21 T 4410")
    tc = demo["toll_crossings"]
    assert (tc.vehicle_no == "UP21 T 4410").any()  # the truck exists, just not on this trip

    jp = demo["invoices"][demo["invoices"].invoice_no.isin(["JP/1187", "JP/1188", "JP/1192"])]
    assert set(jp.ewb_no) == {"381266305518"}
    ewb, x = _trip(demo, "JP/1187")
    assert (ewb.doc_no, ewb.vehicle_no, ewb.route_id, len(x)) == (
        "JP/1187",
        "RJ14 GD 6620",
        "r4",
        2,
    )


def test_every_other_consignment_moved(demo: dict[str, pd.DataFrame]) -> None:
    """All other e-way bills have a plausible trip (crossings in window, <= 80 km/h)."""
    heroes = {"381299021166", "381300457720"}
    for ewb in demo["eway_bills"].itertuples():
        if ewb.ewb_no in heroes:
            continue
        _, x = (
            _trip(demo, ewb.doc_no)
            if (demo["invoices"].invoice_no == ewb.doc_no).sum() == 1
            else (None, None)
        )
        if x is None:
            continue
        assert len(x) >= 1, ewb.doc_no
        if len(x) >= 2:
            speed, _ = _speed(demo["eway_bills"].set_index("ewb_no").loc[ewb.ewb_no], x)
            assert speed <= config.MAX_AVG_SPEED_KMH, (ewb.doc_no, speed)


def test_benford(demo: dict[str, pd.DataFrame]) -> None:
    def digits(gstin: str) -> list[int]:
        up = demo["upstream_invoices"]
        inv = demo["invoices"]
        values = list(up[up.seller_gstin == gstin].value) + list(
            inv[(inv.supplier_gstin == gstin) & (inv.direction == "inward")].total
        )
        c = Counter(first_digit(v) for v in values)
        return [c.get(d, 0) for d in range(1, 10)]

    def mad(counts: list[int]) -> float:
        n = sum(counts)
        return sum(abs(c / n - p) for c, p in zip(counts, BENFORD, strict=True)) / 9

    kaveri = digits("06AAHCK3367Q1ZW")
    assert sum(kaveri) == 64
    assert round(mad(kaveri), 3) == 0.051
    cp = demo["counterparties"]
    sharma = cp[cp.name == "Sharma Steel"].gstin.iloc[0]
    assert mad(digits(sharma)) < config.BENFORD_MAD_THRESHOLD
    # Nobody else reaches the 50-invoice screening threshold.
    up = demo["upstream_invoices"]
    big = up.seller_gstin.value_counts()
    assert set(big[big >= config.BENFORD_MIN_N].index) <= {"06AAHCK3367Q1ZW", sharma}


def test_supplier_graph_has_one_ring(demo: dict[str, pd.DataFrame]) -> None:
    g = nx.DiGraph()
    up = demo["upstream_invoices"]
    g.add_edges_from(zip(up.seller_gstin, up.buyer_gstin, strict=True))
    inv = demo["invoices"]
    inward = inv[inv.direction == "inward"]
    g.add_edges_from(zip(inward.supplier_gstin, inward.buyer_gstin, strict=True))
    cycles = list(nx.simple_cycles(g, length_bound=config.CYCLE_MAX_LEN))
    assert len(cycles) == 1
    names = demo["counterparties"].set_index("gstin").name
    ring = [names[x] for x in cycles[0]]
    start = ring.index("Zenith Traders")
    assert ring[start:] + ring[:start] == [
        "Zenith Traders",
        "Arka Impex",
        "Nexo Metals",
        "Vrindam Trading",
        "Kairo Enterprises",
    ]
    kaveri = "06AAHCK3367Q1ZW"
    nexo = names[names == "Nexo Metals"].index[0]
    assert g.has_edge(nexo, kaveri) and g.has_edge(kaveri, config.USER_GSTIN)


def test_ring_tells(demo: dict[str, pd.DataFrame]) -> None:
    cp = demo["counterparties"].set_index("name")
    as_of = pd.Timestamp("2026-10-10")
    assert (as_of - cp.loc["Zenith Traders"].registered_on).days == 41
    assert cp.loc["Nexo Metals"].ewb_count_90d == 0
    kairo = cp.loc["Kairo Enterprises"]
    assert round((kairo.turnover_month / kairo.turnover_3m_avg - 1) * 100) == 900
    assert cp.loc["Arka Impex"].address == cp.loc["Vrindam Trading"].address


def test_identities_are_valid(demo: dict[str, pd.DataFrame]) -> None:
    cp = demo["counterparties"]
    assert cp.gstin.is_unique
    assert all(is_valid(g) for g in cp.gstin)
    assert cp.phone.str.startswith("+91 55").all()  # never a real mobile series
    assert cp.bank_account.str.startswith("SYN").all()


def test_only_planted_duplicates(
    demo: dict[str, pd.DataFrame], labels: dict[str, set[str]]
) -> None:
    inv = demo["invoices"]
    flagged: set[str] = set()
    for _, grp in inv.groupby(["direction", "supplier_gstin", "buyer_gstin", "total"]):
        rows = grp.sort_values("invoice_date").to_dict("records")
        for i, a in enumerate(rows):
            for b in rows[i + 1 :]:
                close = (
                    abs((b["invoice_date"] - a["invoice_date"]).days) <= config.NEARDUP_DATE_DAYS
                )
                if (
                    close
                    and Levenshtein.distance(a["invoice_no"], b["invoice_no"])
                    <= config.NEARDUP_EDIT_MAX
                ):
                    flagged.add(b["invoice_id"])
    assert flagged == labels["D07"] | labels["D08"]


def test_funnel_setups(demo: dict[str, pd.DataFrame], labels: dict[str, set[str]]) -> None:
    inv = demo["invoices"].set_index("invoice_id")
    led = demo["ledger"]
    books = led[led.voucher_type.isin(["Purchase", "Sales"])]
    assert len(books) == 552 - 18
    # Stage-2 no-GSTIN ledgers keep the raw reference; ID variants normalise equal.
    for uid in labels["D03"]:
        no = inv.loc[uid].invoice_no
        refs = books[
            books.reference.fillna("").map(normalise_invoice_no) == normalise_invoice_no(no)
        ]
        assert len(refs) >= 1 and (refs.reference != no).all()
    # Stage 3 names are close; stage 4 names are not.
    for code, ok in (
        ("S3", lambda s: s >= config.STAGE3_NAME_MIN),
        ("S4", lambda s: s < config.STAGE3_NAME_MIN),
    ):
        for uid in labels[code]:
            row = inv.loc[uid]
            match = books[(books.amount == row.total) & books.reference.isna()]
            assert len(match) >= 1
            assert any(ok(name_similarity(n, row.buyer_name)) for n in match.party_name)


def test_deterministic(tmp_path: Path, demo: dict[str, pd.DataFrame]) -> None:
    data_build.run("demo", out=tmp_path)

    def digest(folder: Path) -> str:
        h = hashlib.sha256()
        for f in sorted((folder / "sources").iterdir()) + sorted((folder / "reference").iterdir()):
            h.update(f.read_bytes())
        return h.hexdigest()

    assert digest(tmp_path) == digest(demo["_dir"])  # type: ignore[arg-type]
    manifest = json.loads((tmp_path / "truth" / "manifest.json").read_text())
    assert manifest["counts"]["invoices"] == 552
