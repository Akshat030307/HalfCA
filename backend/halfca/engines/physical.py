"""Follow the goods: invoice → e-way bill → the truck's toll crossings.

Applies to inter-state inward goods at or above ₹50,000 (duplicate copies excluded).
  1. e-way bill exists?                                    no → missing_ewb
  2. crossings on the route, inside generation → validity + 48 h?   none → paper_only
  3. average speed ≤ 80 km/h?                              no → impossible_journey
  4. one trip (same e-way bill, or same vehicle in overlapping windows) behind more than
     one invoice?                                          yes → recycled_ewb, on every invoice
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

import pandas as pd

from halfca import config, fmt
from halfca.data.routes import Geography

from .common import Flag, chain, evidence

GRACE = pd.Timedelta(hours=48)


def trip_of(e: object | None) -> str:
    """' (RJ14 GD 6620, e-way bill 3812 6630 5518)' for evidence text."""
    if e is None:
        return ""
    return f" ({e.vehicle_no}, e-way bill {fmt.ewb(e.ewb_no)})"  # type: ignore[attr-defined]


@dataclass
class PhysicalResult:
    verdicts: pd.DataFrame  # one row per applicable invoice
    flags: list[Flag]


def applicable(invoices: pd.DataFrame, dup_of: dict[str, str]) -> pd.DataFrame:
    return invoices[
        (invoices.direction == "inward")
        & (invoices.supplier_state != invoices.place_of_supply)
        & (invoices.total >= config.EWB_THRESHOLD)
        & ~invoices.invoice_id.isin(dup_of)
    ]


def check(
    invoices: pd.DataFrame,
    eway_bills: pd.DataFrame,
    crossings: pd.DataFrame,
    geo: Geography,
    dup_of: dict[str, str],
) -> PhysicalResult:
    todo = applicable(invoices, dup_of)
    ewb_by_no = {e.ewb_no: e for e in eway_bills.itertuples()}
    ewb_by_doc = {(e.supplier_gstin, e.doc_no): e for e in eway_bills.itertuples()}
    by_vehicle = {v: g.sort_values("crossed_at") for v, g in crossings.groupby("vehicle_no")}
    verdicts: list[dict] = []
    flags: list[Flag] = []
    trips: list[tuple[str, object]] = []  # (invoice_id, ewb) for the recycled check

    for r in todo.itertuples():
        e = ewb_by_no.get(r.ewb_no) if isinstance(r.ewb_no, str) else None
        e = e or ewb_by_doc.get((r.supplier_gstin, r.invoice_no))
        base = {
            "invoice_id": r.invoice_id,
            "invoice_no": r.invoice_no,
            "supplier": r.supplier_name,
            "supplier_gstin": r.supplier_gstin,
            "total": r.total,
        }
        inv_link = chain(
            "invoice",
            r.invoice_id,
            f"Invoice {r.invoice_no}",
            date=r.invoice_date,
            total=r.total,
            ewb_no=r.ewb_no,
        )
        if e is None:
            verdicts.append({**base, "verdict": "missing_ewb", "ewb_no": None})
            flags.append(
                Flag(
                    "missing_ewb",
                    r.invoice_id,
                    r.invoice_no,
                    r.supplier_name,
                    r.supplier_gstin,
                    "No e-way bill for an inter-state consignment",
                    recorded="No e-way bill",
                    expected=f"E-way bill (≥ {fmt.inr(config.EWB_THRESHOLD)})",
                    impact=float(r.cgst + r.sgst + r.igst),
                    severity="high",
                    evidence=evidence(
                        f"{r.invoice_no} ({fmt.inr(r.total)}) moved goods across states "
                        "without an e-way bill on record.",
                        {},
                        {},
                        [inv_link],
                    ),
                )
            )
            continue
        trips.append((r.invoice_id, e))
        route = geo.routes.get(e.route_id)
        origin_km = route.stops.get(e.from_city, 0.0) if route else 0.0
        plazas = route.plazas_after(origin_km) if route else ()
        plaza_km = {p.id: p.km for p in plazas}
        window_end = e.valid_until + GRACE
        window_h = (window_end - e.generated_at).total_seconds() / 3600
        ewb_link = chain(
            "ewb",
            e.ewb_no,
            f"E-way bill {fmt.ewb(e.ewb_no)}",
            vehicle=e.vehicle_no,
            route=e.route_id,
            from_city=e.from_city,
            distance_km=e.distance_km,
            generated_at=e.generated_at,
            valid_until=e.valid_until,
        )
        common = {
            **base,
            "ewb_no": e.ewb_no,
            "ewb_doc_no": e.doc_no,
            "vehicle_no": e.vehicle_no,
            "route_id": e.route_id,
            "from_city": e.from_city,
            "distance_km": float(e.distance_km),
            "generated_at": e.generated_at,
            "window_end": window_end,
            "window_hours": round(window_h, 1),
            "plazas_expected": len(plazas),
        }
        if not plazas:
            verdicts.append({**common, "verdict": "unverifiable", "crossings": "[]"})
            continue

        seen = by_vehicle.get(e.vehicle_no)
        in_window = (
            seen[
                (seen.crossed_at >= e.generated_at)
                & (seen.crossed_at <= window_end)
                & seen.plaza_id.isin(plaza_km)
            ]
            if seen is not None
            else pd.DataFrame()
        )
        # Keep the forward pass only (km strictly increasing); a return trip is not delivery.
        forward, last_km = [], -1.0
        for c in in_window.itertuples() if len(in_window) else []:
            km = plaza_km[c.plaza_id]
            if km > last_km:
                forward.append(c)
                last_km = km
        cross_rows = [
            {
                "plaza_id": c.plaza_id,
                "plaza_name": c.plaza_name,
                "crossed_at": c.crossed_at.isoformat(),
                "km": plaza_km[c.plaza_id] - origin_km,
            }
            for c in forward
        ]
        links = [inv_link, ewb_link] + [
            chain(
                "toll",
                c.crossing_id,
                f"{c.plaza_name} toll",
                vehicle=c.vehicle_no,
                crossed_at=c.crossed_at,
            )
            for c in forward
        ]
        if not forward:
            verdicts.append({**common, "verdict": "paper_only", "crossings": "[]"})
            others = seen[~seen.index.isin(in_window.index)] if seen is not None else None
            note = (
                f"{e.vehicle_no} does cross tolls on other days ({len(others)} crossings), "
                "just not on this trip."
                if others is not None and len(others)
                else f"{e.vehicle_no} never appears in the toll data."
            )
            flags.append(
                Flag(
                    "paper_only",
                    r.invoice_id,
                    r.invoice_no,
                    r.supplier_name,
                    r.supplier_gstin,
                    "Paper-only supply",
                    recorded=f"0 toll crossings in {window_h:.0f} h",
                    expected=f"{len(plazas)} crossings on {route.highway}",
                    impact=float(r.cgst + r.sgst + r.igst),
                    severity="high",
                    evidence=evidence(
                        f"E-way bill {fmt.ewb(e.ewb_no)} says {e.vehicle_no} carried the "
                        f"goods from {e.from_city} on {route.highway}, but the truck "
                        f"crossed no toll plaza in the {window_h:.0f} h window.",
                        {"crossings": 0},
                        {"crossings": len(plazas)},
                        links,
                        [note],
                    ),
                )
            )
            continue

        first, last = forward[0], forward[-1]
        if len(forward) >= 2:
            hours = (last.crossed_at - first.crossed_at).total_seconds() / 3600
            span_km = plaza_km[last.plaza_id] - plaza_km[first.plaza_id]
            basis = "between first and last toll"
        else:  # one crossing: a lower bound from the e-way bill's generation time
            hours = (first.crossed_at - e.generated_at).total_seconds() / 3600
            span_km = plaza_km[first.plaza_id] - origin_km
            basis = "from e-way bill generation to the only toll (a lower bound)"
        speed = span_km / hours if hours > 0 else float("inf")
        trip_min = float(e.distance_km) / speed * 60 if speed > 0 else 0.0
        common.update(
            {
                "crossings": json.dumps(cross_rows),
                "tolls_crossed": len(forward),
                "speed_kmh": round(speed, 1),
                "trip_minutes": round(trip_min, 1),
            }
        )
        if speed > config.MAX_AVG_SPEED_KMH:
            verdicts.append({**common, "verdict": "impossible_journey"})
            flags.append(
                Flag(
                    "impossible_journey",
                    r.invoice_id,
                    r.invoice_no,
                    r.supplier_name,
                    r.supplier_gstin,
                    "Impossible journey",
                    recorded=f"{e.distance_km:g} km in {fmt.duration(trip_min)} ≈ {speed:.0f} km/h",
                    expected=f"≤ {config.MAX_AVG_SPEED_KMH:g} km/h",
                    impact=float(r.cgst + r.sgst + r.igst),
                    severity="high",
                    evidence=evidence(
                        f"{e.vehicle_no} would have covered {e.from_city} → Delhi "
                        f"({e.distance_km:g} km) in {fmt.duration(trip_min)}, averaging "
                        f"{speed:.0f} km/h {basis}. A loaded truck cannot.",
                        {"speed_kmh": round(speed, 1)},
                        {"max_kmh": config.MAX_AVG_SPEED_KMH},
                        links,
                    ),
                )
            )
        else:
            verdicts.append({**common, "verdict": "verified"})

    # 4 · recycled: one trip behind several invoices
    groups: dict[str, set[str]] = defaultdict(set)
    for iid, e in trips:
        groups[f"ewb:{e.ewb_no}"].add(iid)
    by_vehicle_trip = defaultdict(list)
    for iid, e in trips:
        by_vehicle_trip[e.vehicle_no].append((e.generated_at, e.valid_until + GRACE, iid, e.ewb_no))
    for vehicle, spans in by_vehicle_trip.items():
        spans.sort()
        for i, (s1, e1, iid1, ewb1) in enumerate(spans):
            for s2, _e2, iid2, ewb2 in spans[i + 1 :]:
                if s2 <= e1 and ewb1 != ewb2:
                    groups[f"veh:{vehicle}:{s1.isoformat()}"].update({iid1, iid2})
    inv = todo.set_index("invoice_id", drop=False)
    verdict_by_id = {v["invoice_id"]: v for v in verdicts}
    recycled: dict[str, set[str]] = {}
    for members in groups.values():
        if len(members) > 1:
            for iid in members:
                recycled.setdefault(iid, set()).update(members)
    for iid, members in sorted(recycled.items()):
        r = inv.loc[iid]
        v = verdict_by_id[iid]
        if v["verdict"] == "verified":
            v["verdict"] = "recycled_ewb"
        v["recycled_with"] = ",".join(sorted(inv.loc[m].invoice_no for m in members if m != iid))
        e = ewb_by_no.get(v.get("ewb_no"))
        sib = sorted(members, key=lambda m: (inv.loc[m].invoice_date, inv.loc[m].invoice_no))
        names = ", ".join(
            f"{inv.loc[m].invoice_no} ({fmt.day(inv.loc[m].invoice_date)})" for m in sib
        )
        links = [
            chain(
                "invoice",
                m,
                f"Invoice {inv.loc[m].invoice_no}",
                date=inv.loc[m].invoice_date,
                total=inv.loc[m].total,
                ewb_no=inv.loc[m].ewb_no,
            )
            for m in sib
        ]
        notes = []
        if e is not None and r.invoice_date > e.generated_at.normalize():
            gap = (r.invoice_date - e.generated_at.normalize()).days
            notes.append(
                f"The e-way bill was generated {gap} days before {r.invoice_no} was issued."
            )
        flags.append(
            Flag(
                "recycled_ewb",
                iid,
                r.invoice_no,
                r.supplier_name,
                r.supplier_gstin,
                "Recycled e-way bill",
                recorded=f"1 trip, {len(members)} invoices",
                expected="1 trip per consignment",
                impact=float(r.cgst + r.sgst + r.igst),
                severity="high",
                evidence=evidence(
                    f"One truck trip{trip_of(e)} is claimed by {len(members)} invoices: {names}.",
                    {"invoices_on_trip": len(members)},
                    {"invoices_on_trip": 1},
                    links,
                    notes,
                ),
            )
        )
    out = pd.DataFrame(verdicts)
    return PhysicalResult(out, flags)
