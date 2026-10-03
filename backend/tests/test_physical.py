"""Physical trail on the Jaipur → Delhi route (r4): Shahjahanpur km 98, Kherki Daula km 190.4."""

from __future__ import annotations

import pandas as pd

from halfca.data import routes
from halfca.engines.physical import check

from .factories import DELHI_SUPPLIER, frame, invoice

GEO = routes.load()


def ewb(no: str, doc: str, vehicle: str, generated: str, valid_hours: int = 48) -> dict:
    g = pd.Timestamp(generated)
    return {
        "ewb_no": no,
        "doc_no": doc,
        "supplier_gstin": "08AABFP1234K1Z5",
        "vehicle_no": vehicle,
        "route_id": "r4",
        "from_city": "Jaipur",
        "distance_km": 280.0,
        "generated_at": g,
        "valid_until": g + pd.Timedelta(hours=valid_hours),
    }


def crossing(vehicle: str, plaza: str, at: str) -> dict:
    names = {"PZ-SHAHJAHANPUR": "Shahjahanpur", "PZ-KHERKI-DAULA": "Kherki Daula"}
    return {
        "crossing_id": f"{vehicle}-{plaza}-{at}",
        "vehicle_no": vehicle,
        "plaza_id": plaza,
        "plaza_name": names[plaza],
        "crossed_at": pd.Timestamp(at),
    }


def run(invs: list[dict], ewbs: list[dict], xs: list[dict], dup_of: dict | None = None):
    cols = ["crossing_id", "vehicle_no", "plaza_id", "plaza_name", "crossed_at"]
    return check(frame(invs), frame(ewbs), frame(xs, cols), GEO, dup_of or {})


def big(iid: str, no: str, date: str, ewb_no: str | None) -> dict:
    return invoice(iid, no, date, taxable=60_000, ewb_no=ewb_no)


def test_verified_trip() -> None:
    r = run(
        [big("a", "A/1", "2026-09-08", "E1")],
        [ewb("E1", "A/1", "RJ14 A 1", "2026-09-08 09:00")],
        [
            crossing("RJ14 A 1", "PZ-SHAHJAHANPUR", "2026-09-08 12:00"),
            crossing("RJ14 A 1", "PZ-KHERKI-DAULA", "2026-09-08 13:45"),
        ],
    )
    v = r.verdicts.iloc[0]
    assert v.verdict == "verified" and v.tolls_crossed == 2 and round(v.speed_kmh) == 53
    assert not r.flags


def test_return_leg_does_not_slow_the_delivery() -> None:
    xs = [
        crossing("RJ14 B 2", "PZ-SHAHJAHANPUR", "2026-09-08 12:00"),  # to Delhi
        crossing("RJ14 B 2", "PZ-KHERKI-DAULA", "2026-09-08 13:45"),
        crossing("RJ14 B 2", "PZ-KHERKI-DAULA", "2026-09-09 08:00"),  # driving back
        crossing("RJ14 B 2", "PZ-SHAHJAHANPUR", "2026-09-09 10:00"),
    ]
    r = run(
        [big("a", "A/1", "2026-09-08", "E1")],
        [ewb("E1", "A/1", "RJ14 B 2", "2026-09-08 09:00")],
        xs,
    )
    v = r.verdicts.iloc[0]
    assert (v.verdict, v.tolls_crossed, round(v.speed_kmh)) == ("verified", 2, 53)


def test_paper_only_ignores_other_days() -> None:
    r = run(
        [big("b", "B/1", "2026-09-08", "E2")],
        [ewb("E2", "B/1", "RJ14 C 3", "2026-09-08 09:00")],
        [crossing("RJ14 C 3", "PZ-SHAHJAHANPUR", "2026-09-20 10:00")],
    )
    (f,) = r.flags
    assert f.kind == "paper_only" and f.recorded == "0 toll crossings in 96 h"
    assert "just not on this trip" in f.evidence["notes"][0]


def test_impossible_journey() -> None:
    r = run(
        [big("a", "A/1", "2026-09-08", "E1")],
        [ewb("E1", "A/1", "RJ14 D 4", "2026-09-08 20:00")],
        [
            crossing("RJ14 D 4", "PZ-SHAHJAHANPUR", "2026-09-08 21:00"),
            crossing("RJ14 D 4", "PZ-KHERKI-DAULA", "2026-09-08 21:40"),
        ],
    )
    (f,) = r.flags
    assert f.kind == "impossible_journey" and round(r.verdicts.iloc[0].speed_kmh) == 139


def test_single_crossing_lower_bound() -> None:
    # Generated 21:00, first plaza (km 98) at 21:30: at least 196 km/h.
    r = run(
        [big("a", "A/1", "2026-09-08", "E1")],
        [ewb("E1", "A/1", "RJ14 E 5", "2026-09-08 21:00")],
        [crossing("RJ14 E 5", "PZ-SHAHJAHANPUR", "2026-09-08 21:30")],
    )
    assert [f.kind for f in r.flags] == ["impossible_journey"]


def test_recycled_flags_every_invoice() -> None:
    invs = [
        big("a", "JP/1187", "2026-09-08", "E1"),
        big("b", "JP/1188", "2026-09-15", "E1"),
        big("c", "JP/1192", "2026-09-23", "E1"),
    ]
    xs = [
        crossing("RJ14 GD 6620", "PZ-SHAHJAHANPUR", "2026-09-08 12:00"),
        crossing("RJ14 GD 6620", "PZ-KHERKI-DAULA", "2026-09-08 13:45"),
    ]
    r = run(invs, [ewb("E1", "JP/1187", "RJ14 GD 6620", "2026-09-08 09:00")], xs)
    assert sorted(f.invoice_id for f in r.flags if f.kind == "recycled_ewb") == ["a", "b", "c"]
    assert set(r.verdicts.verdict) == {"recycled_ewb"}


def test_overlapping_trips_of_one_truck() -> None:
    invs = [big("a", "A/1", "2026-09-08", "E1"), big("b", "A/2", "2026-09-08", "E2")]
    ewbs = [
        ewb("E1", "A/1", "RJ14 F 6", "2026-09-08 09:00"),
        ewb("E2", "A/2", "RJ14 F 6", "2026-09-08 10:00"),
    ]
    xs = [
        crossing("RJ14 F 6", "PZ-SHAHJAHANPUR", "2026-09-08 12:00"),
        crossing("RJ14 F 6", "PZ-KHERKI-DAULA", "2026-09-08 13:45"),
    ]
    r = run(invs, ewbs, xs)
    assert sorted(f.invoice_id for f in r.flags) == ["a", "b"]


def test_missing_and_not_applicable() -> None:
    invs = [
        big("a", "A/1", "2026-09-08", None),  # inter-state ≥ ₹50k, no e-way bill
        invoice("b", "B/1", "2026-09-08", taxable=30_000),  # below the threshold
        invoice("c", "C/1", "2026-09-08", taxable=90_000, party=DELHI_SUPPLIER),  # intra-state
        big("d", "D/1", "2026-09-08", None),  # a duplicate copy
    ]
    r = run(invs, [ewb("E9", "Z/9", "RJ14 Z 9", "2026-09-01 09:00")], [], dup_of={"d": "a"})
    assert [(f.invoice_id, f.kind) for f in r.flags] == [("a", "missing_ewb")]
    assert list(r.verdicts.invoice_id) == ["a"]
