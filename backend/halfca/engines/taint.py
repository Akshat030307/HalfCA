"""Follow the credit: is this ITC built on a circular-trading ring?

Graph: GSTINs, edge seller → buyer (upstream invoices + the user's own purchases).
  cycles      simple cycles of length ≤ 6, kept when a member is ≤ 3 hops upstream of the user
  own risk    ring member 0.91; otherwise new registration +0.3, zero e-way bills on goods
              trade +0.3, turnover spike +0.2, shared identity +0.2, filing gaps +0.2 (cap 1)
  propagation r(v) = max(own(v), 0.9 × max over sellers r(u)), to a fixed point
  at risk     a direct supplier with r ≥ 0.7
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import networkx as nx
import pandas as pd

from halfca import config, fmt

from .common import Flag, chain, evidence


@dataclass
class TaintResult:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    cycles: list[list[str]]
    flags: list[Flag]
    risk: dict[str, float]
    at_risk: set[str] = field(default_factory=set)  # direct suppliers with r ≥ 0.7


def build_graph(
    upstream: pd.DataFrame, invoices: pd.DataFrame, dup_of: dict[str, str]
) -> nx.DiGraph:
    g = nx.DiGraph()
    inward = invoices[(invoices.direction == "inward") & ~invoices.invoice_id.isin(dup_of)]
    trades = pd.concat(
        [
            upstream[["seller_gstin", "buyer_gstin", "value"]],
            inward.rename(
                columns={
                    "supplier_gstin": "seller_gstin",
                    "buyer_gstin": "buyer_gstin",
                    "total": "value",
                }
            )[["seller_gstin", "buyer_gstin", "value"]],
        ]
    )
    for (s, b), grp in trades.groupby(["seller_gstin", "buyer_gstin"]):
        g.add_edge(s, b, invoices=len(grp), value=float(grp.value.sum()))
    return g


def _shared_identity(cp: pd.DataFrame) -> dict[str, list[str]]:
    """GSTIN → descriptions of identity fields it shares with other GSTINs."""
    out: dict[str, list[str]] = defaultdict(list)
    names = dict(zip(cp.gstin, cp.name, strict=True))
    for col, label in (
        ("pan", "PAN"),
        ("bank_account", "bank account"),
        ("phone", "phone"),
        ("address", "address"),
    ):
        for _, grp in cp[cp[col].notna() & (cp[col] != "")].groupby(col):
            members = list(grp.gstin)
            if len(members) < 2:
                continue
            for m in members:
                others = ", ".join(names[x] for x in members if x != m)
                out[m].append(f"shares {label} with {others}")
    return out


def analyse(
    counterparties: pd.DataFrame,
    upstream: pd.DataFrame,
    invoices: pd.DataFrame,
    user_gstin: str,
    as_of: date,
    dup_of: dict[str, str],
) -> TaintResult:
    g = build_graph(upstream, invoices, dup_of)
    cp = counterparties.set_index("gstin", drop=False)
    names = cp.name.to_dict()

    # Distance upstream of the user (sellers of sellers …).
    hops_up = (
        nx.single_source_shortest_path_length(g.reverse(copy=False), user_gstin)
        if user_gstin in g
        else {}
    )
    cycles = [
        c
        for c in nx.simple_cycles(g, length_bound=config.CYCLE_MAX_LEN)
        if any(hops_up.get(n, 99) <= config.CYCLE_UPSTREAM_HOPS for n in c)
    ]
    ring_of = {n: i for i, c in enumerate(cycles) for n in c}

    shared = _shared_identity(counterparties)
    sellers = {s for s, _ in g.edges}
    as_of_ts = pd.Timestamp(as_of)
    own: dict[str, float] = {}
    signals: dict[str, list[dict]] = {}
    for node in g.nodes:
        sig: list[dict] = []
        if node in cp.index:
            x = cp.loc[node]
            age = (as_of_ts - pd.Timestamp(x.registered_on)).days
            if age < config.NEW_REG_DAYS:
                sig.append(
                    {
                        "signal": "new_registration",
                        "weight": config.RISK_NEW_REGISTRATION,
                        "text": f"Registered {age} days ago",
                    }
                )
            if node in sellers and node != user_gstin and int(x.ewb_count_90d) == 0:
                sig.append(
                    {
                        "signal": "zero_ewb",
                        "weight": config.RISK_ZERO_EWB,
                        "text": "Zero e-way bills on goods trade",
                    }
                )
            avg, month = float(x.turnover_3m_avg or 0), float(x.turnover_month or 0)
            if avg > 0 and month > config.TURNOVER_SPIKE * avg:
                sig.append(
                    {
                        "signal": "turnover_spike",
                        "weight": config.RISK_TURNOVER_SPIKE,
                        "text": f"Turnover +{(month / avg - 1) * 100:.0f}%",
                    }
                )
            if shared.get(node):
                sig.append(
                    {
                        "signal": "shared_identity",
                        "weight": config.RISK_SHARED_IDENTITY,
                        "text": "; ".join(shared[node]).capitalize(),
                    }
                )
            if int(x.returns_missed_6m) > 0:
                sig.append(
                    {
                        "signal": "filing_gaps",
                        "weight": config.RISK_FILING_GAPS,
                        "text": f"Missed {int(x.returns_missed_6m)} return(s) in 6 months",
                    }
                )
        signals[node] = sig
        if node in ring_of:
            own[node] = config.RING_RISK
        else:
            own[node] = min(1.0, sum(s["weight"] for s in sig))

    risk = dict(own)
    for _ in range(200):
        changed = 0.0
        for v in g.nodes:
            preds = [risk[u] for u in g.predecessors(v)]
            new = max(own[v], config.TAINT_DECAY * max(preds)) if preds else own[v]
            changed = max(changed, abs(new - risk[v]))
            risk[v] = new
        if changed < 1e-12:
            break

    direct = set(g.predecessors(user_gstin)) if user_gstin in g else set()
    at_risk = {s for s in direct if risk[s] >= config.TAINT_AT_RISK}

    # Path from the nearest ring member down to each at-risk supplier.
    ring_nodes = set(ring_of)
    flags: list[Flag] = []
    inward = invoices[(invoices.direction == "inward") & ~invoices.invoice_id.isin(dup_of)]
    for s in sorted(at_risk):
        path: list[str] = []
        for r in sorted(ring_nodes):
            try:
                p = nx.shortest_path(g, r, s)
            except nx.NetworkXNoPath:
                continue
            if not path or len(p) < len(path):
                path = p
        mine = inward[inward.supplier_gstin == s]
        itc = float((mine.cgst + mine.sgst + mine.igst).sum())
        ring = cycles[ring_of[path[0]]] if path else []
        ring_names = [names.get(n, n) for n in ring]
        hops_to_you = len(path)  # ring member → … → supplier → you
        links = [
            chain(
                "graph",
                n,
                names.get(n, n),
                risk=round(risk[n], 2),
                own_risk=own[n],
                signals=[x["text"] for x in signals[n]],
            )
            for n in path
        ]
        links += [
            chain(
                "invoice",
                i.invoice_id,
                f"Invoice {i.invoice_no}",
                total=i.total,
                itc=i.cgst + i.sgst + i.igst,
            )
            for i in mine.itertuples()
        ]
        ring_signals = [f"{names.get(n, n)}: {x['text']}" for n in ring for x in signals[n]]
        feeder = names.get(path[-2], "?") if len(path) > 1 else "?"
        flags.append(
            Flag(
                "ring_taint",
                None,
                s,
                names.get(s, s),
                s,
                "Supplier fed by a circular-trading ring",
                recorded=f"Taint {risk[s]:.2f}",
                expected=f"< {config.TAINT_AT_RISK:.2f}",
                impact=itc,
                severity="high",
                evidence=evidence(
                    f"{names.get(s, s)} buys from {feeder}, "
                    f"a member of a {len(ring)}-firm ring ({' → '.join(ring_names)}). Your ITC of "
                    f"{fmt.inr(itc)} on {len(mine)} invoices sits {hops_to_you} hops downstream.",
                    {"taint": round(risk[s], 3)},
                    {"max": config.TAINT_AT_RISK},
                    links,
                    ring_signals,
                ),
            )
        )

    rows = []
    for n in g.nodes:
        x = cp.loc[n] if n in cp.index else None
        rows.append(
            {
                "gstin": n,
                "name": names.get(n, n),
                "city": None if x is None else x.city,
                "role": "you" if n == user_gstin else ("supplier" if n in direct else "upstream"),
                "tier": None if x is None else int(x.tier),
                "own_risk": round(own[n], 4),
                "risk": round(risk[n], 4),
                "ring": ring_of.get(n),
                "hops_up": hops_up.get(n),
                "at_risk": n in at_risk,
                "signals": json.dumps([s["text"] for s in signals[n]]),
            }
        )
    edges = pd.DataFrame(
        [
            {
                "seller": s,
                "buyer": b,
                "invoices": d["invoices"],
                "value": round(d["value"], 2),
                "ring_edge": s in ring_of and b in ring_of and ring_of[s] == ring_of[b],
            }
            for s, b, d in g.edges(data=True)
        ]
    )
    return TaintResult(pd.DataFrame(rows), edges, cycles, flags, risk, at_risk)
