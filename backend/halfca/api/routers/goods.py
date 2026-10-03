"""Follow the Goods: routes for the map and a verdict per consignment."""

from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi import APIRouter

from halfca.data import routes as geo
from halfca.models import Goods, GoodsDetail

from ..state import Dataset, current
from ..views import flags_out, json_list, plain

router = APIRouter()

FAILED = ("paper_only", "impossible_journey", "recycled_ewb", "missing_ewb")


def _trip(r: pd.Series) -> dict[str, Any]:
    g = r.get
    recycled = g("recycled_with")
    return {
        "invoice_id": r.invoice_id,
        "invoice_no": r.invoice_no,
        "invoice_date": "",
        "supplier": r.supplier,
        "supplier_gstin": r.supplier_gstin,
        "total": float(r.total),
        "verdict": r.verdict,
        "ewb_no": plain(g("ewb_no")),
        "ewb_doc_no": plain(g("ewb_doc_no")),
        "vehicle_no": plain(g("vehicle_no")),
        "route_id": plain(g("route_id")),
        "from_city": plain(g("from_city")),
        "distance_km": plain(g("distance_km")),
        "generated_at": plain(g("generated_at")),
        "window_hours": plain(g("window_hours")),
        "plazas_expected": plain(g("plazas_expected")),
        "tolls_crossed": int(plain(g("tolls_crossed")) or 0),
        "speed_kmh": plain(g("speed_kmh")),
        "trip_minutes": plain(g("trip_minutes")),
        "crossings": json_list(g("crossings")),
        "recycled_with": [x for x in str(plain(recycled) or "").split(",") if x],
    }


def _trips(ds: Dataset) -> list[dict[str, Any]]:
    phys = ds.res["physical"]
    out = []
    for _, r in phys.iterrows():
        t = _trip(r)
        t["invoice_date"] = plain(ds.invoices.loc[r.invoice_id].invoice_date)
        out.append(t)
    return out


def _beats(ds: Dataset, trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The four story beats, chosen from the data (not hard-coded invoice numbers):
    the biggest clean verified trip, then the biggest of each failure kind."""
    # Findings that make a trip a bad example; anomaly hints and payment gaps do not.
    serious = ds.flags[
        ds.flags.category.isin(["discrepancy", "duplicate", "unmatched", "physical"])
    ]
    flagged = set(serious.invoice_id.dropna())
    at_risk = set(ds.res["taint_nodes"].query("at_risk").gstin)
    beats = []
    clean = [
        t
        for t in trips
        if t["verdict"] == "verified"
        and t["invoice_id"] not in flagged
        and t["supplier_gstin"] not in at_risk
        and t["tolls_crossed"] == t["plazas_expected"]
        and t["tolls_crossed"] >= 2
    ]
    if clean:
        best = max(clean, key=lambda t: t["total"])
        beats.append({"kind": "verified", "invoice_ids": [best["invoice_id"]]})
    for kind in ("paper_only", "impossible_journey"):
        hits = [t for t in trips if t["verdict"] == kind]
        if hits:
            beats.append(
                {"kind": kind, "invoice_ids": [max(hits, key=lambda t: t["total"])["invoice_id"]]}
            )
    recycled = [t for t in trips if t["verdict"] == "recycled_ewb"]
    if recycled:
        groups: dict[str, list[dict[str, Any]]] = {}
        for t in recycled:
            groups.setdefault(t["ewb_no"] or t["invoice_id"], []).append(t)
        group = max(groups.values(), key=len)
        group.sort(key=lambda t: (t["invoice_date"], t["invoice_no"]))
        beats.append({"kind": "recycled_ewb", "invoice_ids": [t["invoice_id"] for t in group]})
    return beats


@router.get("/goods", response_model=Goods)
def goods() -> dict[str, Any]:
    ds = current()
    raw = geo.raw_json()
    g = geo.load()
    trips = _trips(ds)
    verdicts: dict[str, int] = {}
    for t in trips:
        verdicts[t["verdict"]] = verdicts.get(t["verdict"], 0) + 1
    return {
        "view_box": raw["viewBox"],
        "cities": [
            {
                k: c.get(k, False) if k in ("hub", "minor") else c[k]
                for k in ("name", "state_code", "x", "y", "hub", "minor")
            }
            for c in raw["cities"]
        ],
        "routes": [
            {
                "id": r.id,
                "name": r.name,
                "highway": r.highway,
                "origin": r.origin,
                "destination": r.destination,
                "distance_km": r.distance_km,
                "svg_path": r.svg_path,
                "stops": r.stops,
                "plazas": [
                    {"id": p.id, "name": p.name, "frac": p.frac, "km": p.km} for p in r.plazas
                ],
            }
            for r in g.routes.values()
        ],
        "verdicts": verdicts,
        "invoices": sorted(trips, key=lambda t: (t["verdict"] == "verified", -t["total"])),
        "beats": _beats(ds, trips),
    }


@router.get("/goods/{key:path}", response_model=GoodsDetail)
def goods_detail(key: str) -> dict[str, Any]:
    ds = current()
    inv = ds.find_invoice(key)
    phys = ds.res["physical"]
    row = phys[phys.invoice_id == inv.invoice_id]
    if not len(row):
        from fastapi import HTTPException

        raise HTTPException(404, f"{inv.invoice_no} is not an inter-state consignment of ₹50,000+")
    trip = _trip(row.iloc[0])
    trip["invoice_date"] = plain(inv.invoice_date)
    f = ds.flags_for(invoice_id=inv.invoice_id)
    return {"trip": trip, "flags": flags_out(f[f.category == "physical"])}
