"""Follow the Credit: the supplier graph and one supplier's taint."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from halfca import config
from halfca.ingest.gstin import STATES
from halfca.models import BenfordOut, CreditGraph, SupplierRisk

from ..state import Dataset, current
from ..views import flag_out, json_list, plain

router = APIRouter()


def _node(r: pd.Series, slot: str, feeds: str | None = None) -> dict[str, Any]:
    return {
        "gstin": r.gstin,
        "name": r["name"],
        "city": plain(r.city),
        "role": r.role,
        "slot": slot,
        "risk": float(r.risk),
        "own_risk": float(r.own_risk),
        "ring": None if pd.isna(r.ring) else int(r.ring),
        "hops_up": None if pd.isna(r.hops_up) else int(r.hops_up),
        "at_risk": bool(r.at_risk),
        "signals": json_list(r.signals),
        "feeds": feeds,
    }


def _itc_by_supplier(ds: Dataset) -> dict[str, float]:
    inv = ds.raw["invoices"]
    inward = inv[inv.direction == "inward"]
    return (inward.cgst + inward.sgst + inward.igst).groupby(inward.supplier_gstin).sum().to_dict()


def focus_view(ds: Dataset) -> tuple[list[dict[str, Any]], set[str]]:
    """You, the at-risk suppliers and the chain to their ring, a few clean suppliers with
    one upstream each, and every ring member."""
    nodes = ds.res["taint_nodes"].set_index("gstin", drop=False)
    edges = ds.res["taint_edges"]
    user = str(ds.meta["user_gstin"])
    picked: dict[str, tuple[str, str | None]] = {user: ("you", None)}

    for g in nodes[nodes.at_risk].gstin:
        picked[g] = ("at_risk", None)
    for f in ds.flags[ds.flags.kind == "ring_taint"].itertuples():
        for link in json.loads(f.evidence)["chain"]:
            if link["source"] == "graph" and link["id"] not in picked:
                picked[link["id"]] = (
                    "ring" if not pd.isna(nodes.loc[link["id"]].ring) else "upstream",
                    None,
                )
    for g in nodes[nodes.ring.notna()].gstin:
        picked.setdefault(g, ("ring", None))

    tags = ds.raw["counterparties"].set_index("gstin").tags.fillna("")
    showcase = [g for g in nodes.gstin if "showcase" in str(tags.get(g, ""))]
    direct = set(nodes[nodes.role == "supplier"].gstin)
    if showcase:
        for g in showcase:
            if g in direct:
                picked.setdefault(g, ("supplier", None))
        for g in showcase:
            if g not in direct:
                buys = edges[(edges.seller == g) & edges.buyer.isin(showcase)]
                picked.setdefault(g, ("upstream", buys.buyer.iloc[0] if len(buys) else None))
    else:  # any dataset: the three biggest clean suppliers and their biggest seller
        itc = _itc_by_supplier(ds)
        clean = sorted(
            (g for g in direct if not nodes.loc[g].at_risk), key=lambda g: -itc.get(g, 0.0)
        )[:3]
        for g in clean:
            picked.setdefault(g, ("supplier", None))
            sellers = edges[edges.buyer == g].sort_values("value", ascending=False)
            if len(sellers):
                picked.setdefault(sellers.iloc[0].seller, ("upstream", g))

    out = [
        _node(nodes.loc[g], slot, feeds) for g, (slot, feeds) in picked.items() if g in nodes.index
    ]
    return out, set(picked)


@router.get("/credit/graph", response_model=CreditGraph)
def credit_graph(scope: str = Query("focus", pattern="^(focus|full)$")) -> dict[str, Any]:
    ds = current()
    nodes_df = ds.res["taint_nodes"]
    edges = ds.res["taint_edges"]
    if scope == "full":
        nodes = [
            _node(r, "ring" if not pd.isna(r.ring) else ("you" if r.role == "you" else r.role))
            for _, r in nodes_df.iterrows()
        ]
        keep = set(nodes_df.gstin)
    else:
        nodes, keep = focus_view(ds)
    e = edges[edges.seller.isin(keep) & edges.buyer.isin(keep)]
    cycles = [json.loads(c) for c in ds.res["cycles"].members] if len(ds.res["cycles"]) else []
    focus = nodes_df[nodes_df.at_risk].sort_values("risk", ascending=False)
    return {
        "scope": scope,
        "nodes": nodes,
        "edges": [{k: plain(v) for k, v in r.items()} for r in e.to_dict("records")],
        "cycles": cycles,
        "focus": focus.gstin.iloc[0] if len(focus) else None,
        "threshold": config.TAINT_AT_RISK,
    }


def benford_for(ds: Dataset, gstin: str) -> dict[str, Any] | None:
    b = ds.res["benford"]
    row = b[b.gstin == gstin]
    if not len(row):
        return None
    r = row.iloc[0]
    return {
        "gstin": gstin,
        "name": r["name"],
        "n": int(r.n),
        "mad": float(r.mad),
        "threshold": config.BENFORD_MAD_THRESHOLD,
        "nonconforming": bool(r.nonconforming),
        "observed": json.loads(r.observed),
        "expected": json.loads(r.expected),
    }


@router.get("/credit/supplier/{gstin}", response_model=SupplierRisk)
def supplier_risk(gstin: str) -> dict[str, Any]:
    ds = current()
    nodes = ds.res["taint_nodes"].set_index("gstin", drop=False)
    if gstin not in nodes.index:
        raise HTTPException(404, f"{gstin} is not in the supplier graph")
    n = nodes.loc[gstin]
    flag = ds.flags[(ds.flags.kind == "ring_taint") & (ds.flags.ref == gstin)]
    fo = flag_out(flag.iloc[0]) if len(flag) else None
    path = [x["id"] for x in fo["evidence"]["chain"] if x["source"] == "graph"] if fo else []
    ring_id = nodes.loc[path[0]].ring if path else n.ring
    members = [] if pd.isna(ring_id) else list(nodes[nodes.ring == ring_id].name)

    inv = ds.raw["invoices"]
    mine = inv[(inv.direction == "inward") & (inv.supplier_gstin == gstin)]
    decisions = dict(zip(ds.res["ims"].invoice_id, ds.res["ims"].decision, strict=True))
    invoices = [
        {
            "invoice_id": r.invoice_id,
            "invoice_no": r.invoice_no,
            "invoice_date": plain(r.invoice_date),
            "total": float(r.total),
            "itc": round(float(r.cgst + r.sgst + r.igst), 2),
            "ims_decision": decisions.get(r.invoice_id),
        }
        for r in mine.itertuples()
    ]
    at_risk = sum(i["itc"] for i in invoices if i["ims_decision"] == "Pending")
    cp = ds.raw["counterparties"].set_index("gstin")
    city = plain(cp.loc[gstin].city) if gstin in cp.index else None
    action = (
        f"Keep the {len(invoices)} invoices Pending and ask {n['name']} for transport proof "
        "(e-way bills, lorry receipts) and its own purchase invoices before claiming the credit."
        if bool(n.at_risk)
        else "No action needed."
    )
    return {
        "gstin": gstin,
        "name": n["name"],
        "city": city,
        "state": STATES.get(gstin[:2]),
        "risk": float(n.risk),
        "own_risk": float(n.own_risk),
        "at_risk": bool(n.at_risk),
        "signals": json_list(n.signals),
        "ring_members": members,
        "ring_signals": fo["evidence"]["notes"] if fo else [],
        "hops_to_you": len(path) if path else None,
        "path": path,
        "invoices": invoices,
        "itc_at_risk": round(at_risk, 2),
        "benford": benford_for(ds, gstin),
        "action": action,
        "flag": fo,
    }


@router.get("/benford/{gstin}", response_model=BenfordOut)
def benford(gstin: str) -> dict[str, Any]:
    out = benford_for(current(), gstin)
    if out is None:
        raise HTTPException(
            404, f"{gstin} has fewer than {config.BENFORD_MIN_N} invoices to screen"
        )
    return out
