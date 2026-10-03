"""The seven tools behind the copilot and the MCP server.

Each reads the current reconciled dataset and returns plain JSON: facts with money already
formatted by fmt.py (so a language model never has to do arithmetic), a one-line
`headline`, and an `evidence` list pointing at the screens and records behind the facts.

    reconcile_period(gstin, month)          the month at a glance
    list_discrepancies(type, min_amount)    findings, biggest ₹ first
    trace_goods(invoice_id)                 one consignment against the toll record
    supplier_risk(gstin)                    taint, ring, Benford and what to do
    ims_recommendations(month)              Accept / Reject / Pending with reasons
    estimate_liability(month, scenario)     net payable as filed vs reconciled
    explain(flag_id)                        the full evidence behind one finding
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import HTTPException
from rapidfuzz import fuzz, process, utils

from halfca import config, fmt
from halfca.ai import llm
from halfca.api import state
from halfca.api.routers import credit
from halfca.data import routes as geo
from halfca.engines.common import DISCREPANCY_KINDS, KINDS


class ToolError(ValueError):
    """A problem with the arguments, said in words a model or a person can act on."""


SCREENS = {
    "overview": ("Overview", "/overview/"),
    "matching": ("Matching", "/matching/"),
    "discrepancies": ("Discrepancies", "/discrepancies/"),
    "goods": ("Follow the Goods", "/goods/"),
    "credit": ("Follow the Credit", "/credit/"),
    "ims": ("IMS Autopilot", "/ims/"),
    "liability": ("Liability", "/liability/"),
}
CATEGORY_SCREEN = {
    "discrepancy": "discrepancies",
    "duplicate": "discrepancies",
    "unmatched": "matching",
    "gap": "discrepancies",
    "physical": "goods",
    "credit": "credit",
    "anomaly": "liability",
    "review": "discrepancies",
}
SCREEN_LABEL = {
    "goods": "Road check",
    "credit": "Supplier ring",
    "discrepancies": "Discrepancies",
    "matching": "Unmatched queue",
    "liability": "Anomalies",
    "ims": "IMS actions",
    "overview": "Overview",
}
ALIASES: dict[str, list[str]] = {
    "road": ["physical"],
    "goods": ["physical"],
    "toll": ["physical"],
    "eway": ["physical"],
    "tax": ["tax_rate", "tax_head", "tax_arith"],
    "duplicates": ["duplicate"],
    "ring": ["credit"],
    "gaps": ["gap"],
    "anomalies": ["anomaly"],
    "discrepancies": ["discrepancy"],
}
ROAD_LABEL = {
    "verified": "Goods verified on the road",
    "paper_only": "Paper-only supply",
    "impossible_journey": "Impossible journey",
    "recycled_ewb": "Recycled e-way bill",
    "missing_ewb": "Missing e-way bill",
}
RULE_WORDS = {  # IMS Autopilot rules, as a phrase that follows a count
    "clean": "match your books",
    "tax_wrong": "charged the wrong tax or amount",
    "road_failed": "failed the road check",
    "supplier_taint": "from a supplier fed by a circular-trading ring",
    "not_matched": "not in your books yet",
}
GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]\b")


def link(label: str, screen: str, refs: list[str] | None = None) -> dict[str, Any]:
    """One evidence pointer: a chip in the copilot, a citation for an MCP client."""
    name, href = SCREENS[screen]
    return {"label": label, "screen": name, "href": href, "refs": refs or []}


def _ds() -> state.Dataset:
    try:
        return state.current()
    except HTTPException as e:
        raise ToolError(str(e.detail)) from e


def _period_label(period: str) -> str:
    return datetime.strptime(period, "%Y-%m").strftime("%b %Y")


def _check_period(ds: state.Dataset, month: str | None) -> str:
    """Accept 2026-09, 09-2026, Sep 2026, September 2026; only the loaded month exists."""
    period = str(ds.meta["period"])
    if not month or not month.strip():
        return period
    m = month.strip()
    for f in ("%Y-%m", "%m-%Y", "%b %Y", "%B %Y", "%Y/%m", "%m/%Y", "%b-%Y", "%B-%Y"):
        try:
            if datetime.strptime(m, f).strftime("%Y-%m") == period:
                return period
            break
        except ValueError:
            continue
    raise ToolError(
        f"Only {_period_label(period)} ({period}) is loaded; ask about that month instead."
    )


def _check_gstin(ds: state.Dataset, gstin: str | None) -> str:
    user = str(ds.meta["user_gstin"])
    if gstin and gstin.strip().upper() not in (user, ""):
        raise ToolError(f"Only {ds.meta['user_name']} ({user}) is loaded.")
    return user


def _flags(ds: state.Dataset) -> pd.DataFrame:
    return ds.flags


def _evidence_of(row: pd.Series) -> dict[str, Any]:
    ev = row.evidence
    return json.loads(ev) if isinstance(ev, str) else dict(ev)


def _flag_brief(row: pd.Series) -> dict[str, Any]:
    return {
        "flag_id": row.flag_id,
        "type": row.label,
        "invoice": row.ref,
        "counterparty": row.counterparty,
        "title": row.title,
        "recorded": row.recorded,
        "expected": row.expected,
        "at_stake": fmt.inr(float(row.impact or 0)),
        "why": _evidence_of(row)["summary"],
    }


def _plain_text(v: Any) -> Any:
    if isinstance(v, float):
        return f"{v:g}" if abs(v) < 1e6 else f"{v:.0f}"
    return v


# ── 1. reconcile_period ──────────────────────────────────────────────────────


def reconcile_period(gstin: str | None = None, month: str | None = None) -> dict[str, Any]:
    ds = _ds()
    user = _check_gstin(ds, gstin)
    period = _check_period(ds, month)
    s = ds.summary
    phys = s["physical"]
    funnel = []
    for st in s["funnel"]:
        row = {"stage": f"{st['stage']} {st['label']}", "paired": st["paired"], "left": st["left"]}
        if st["stage"] == 4:
            row["model"] = None if st["skipped"] else (llm.model_name() or s.get("llm"))
            if st["skipped"]:
                row["note"] = "skipped: no AI model configured"
        funnel.append(row)
    liab = s["liability"]
    return {
        "headline": (
            f"{s['reconciled']} invoices · {s['matched']} matched · "
            f"exposure {fmt.lakh(s['exposure'])}"
        ),
        "company": ds.meta["user_name"],
        "gstin": user,
        "period": period,
        "period_label": _period_label(period),
        "data_as_of": fmt.stamp(datetime.fromisoformat(str(ds.meta["as_of"]))),
        "invoices": {
            "reconciled": s["reconciled"],
            "matched_clean": s["matched"],
            "clean_match": f"{s['clean_match_pct'] * 100:.1f}%",
            "with_discrepancies": s["discrepancies"],
            "duplicates": s["duplicates"],
            "unmatched": s["unmatched"],
        },
        "discrepancies_by_type": {KINDS[k][1]: n for k, n in s["discrepancy_types"].items() if n},
        "matching_funnel": funnel,
        "road_check": {
            "consignments_checked": phys["checked"],
            "verified": phys["verified"],
            "failed": phys["failed"],
            "failed_by_kind": {
                ROAD_LABEL.get(k, k): n for k, n in phys["by_verdict"].items() if k != "verified"
            },
            "failed_but_clean_on_paper": phys["failed_inside_matched"],
        },
        "supplier_network": {
            "circular_trading_rings": s["rings"],
            "suppliers_at_risk": s["at_risk_suppliers"],
        },
        "ims": {k: s["ims"][k] for k in ("records", "accept", "reject", "pending")},
        "liability": {
            "net_payable_as_filed": fmt.lakh(liab["net_payable_filed"]),
            "net_payable_reconciled": fmt.lakh(liab["net_payable_reconciled"]),
            "exposure_caught": fmt.lakh(liab["exposure"]),
        },
        "evidence": [
            link("Overview", "overview"),
            link(f"{s['unmatched']} unmatched", "matching"),
        ],
    }


# ── 2. list_discrepancies ────────────────────────────────────────────────────


def _filter_flags(ds: state.Dataset, type_: str | None) -> tuple[pd.DataFrame, str]:
    f = _flags(ds)
    t = (type_ or "").strip().lower().replace("-", "_").replace(" ", "_")
    if t in ("", "all", "default"):
        status = ds.status.status
        on_paired = f.invoice_id.map(lambda i: status.get(i) in ("discrepant", "duplicate"))
        kinds = DISCREPANCY_KINDS + ["duplicate", "near_duplicate"]
        return f[f.kind.isin(kinds) & on_paired], "discrepancies and duplicates"
    wanted = ALIASES.get(t, [t])
    categories = {c for c, _ in KINDS.values()}
    kinds = [w for w in wanted if w in KINDS]
    cats = [w for w in wanted if w in categories]
    if not kinds and not cats:
        options = sorted(set(KINDS) | categories | set(ALIASES))
        raise ToolError(f"Unknown type {type_!r}. Use one of: {', '.join(options)}")
    out = f[f.kind.isin(kinds) | f.category.isin(cats)]
    label = ", ".join([KINDS[k][1] for k in kinds] + cats)
    return out, label


def list_discrepancies(
    type: str | None = None,  # noqa: A002 (the spec's argument name)
    min_amount: float | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    ds = _ds()
    f, label = _filter_flags(ds, type)
    if min_amount:
        f = f[f.impact >= float(min_amount)]
    f = f.sort_values("impact", ascending=False)
    limit = max(1, min(int(limit or 8), 25))
    by_type = f.label.value_counts().to_dict()
    total = float(f.impact.sum())
    evidence = []
    for cat, n in f.category.value_counts().items():
        screen = CATEGORY_SCREEN.get(str(cat), "discrepancies")
        names = {
            "physical": f"{n} road failure{'s' if n != 1 else ''}",
            "credit": "Supplier ring",
            "unmatched": f"{n} unmatched",
            "anomaly": "Anomalies",
        }
        evidence.append(
            link(
                names.get(str(cat), f"{n} {cat} flags"), screen, list(f[f.category == cat].flag_id)
            )
        )
    if any(f.kind == "ring_taint"):
        name = f[f.kind == "ring_taint"].counterparty.iloc[0]
        evidence = [e for e in evidence if e["screen"] != "Follow the Credit"]
        evidence.append(link(f"{name} ring", "credit"))
    return {
        "headline": f"{len(f)} found · {fmt.inr(total)} at stake",
        "filter": label + (f" · at least {fmt.inr(float(min_amount))}" if min_amount else ""),
        "count": len(f),
        "total_at_stake": fmt.inr(total),
        "by_type": {str(k): int(v) for k, v in by_type.items()},
        "items": [_flag_brief(r) for _, r in f.head(limit).iterrows()],
        "more_not_shown": max(0, len(f) - limit),
        "evidence": evidence,
    }


# ── 3. trace_goods ───────────────────────────────────────────────────────────


def _find_invoice(ds: state.Dataset, key: str) -> pd.Series:
    key = (key or "").strip()
    if not key:
        raise ToolError("Give an invoice number, e.g. MB/0877")
    try:
        return ds.find_invoice(key)
    except HTTPException:
        pass
    inv = ds.invoices
    hits = inv[inv.invoice_no.str.upper() == key.upper()]
    if len(hits) == 1:
        return hits.iloc[0]
    if len(hits) > 1:
        raise ToolError(f"{key} matches {len(hits)} invoices; give the invoice_id instead")
    raise ToolError(f"No invoice {key!r} in {_period_label(str(ds.meta['period']))}")


def trace_goods(invoice_id: str) -> dict[str, Any]:
    ds = _ds()
    inv = _find_invoice(ds, invoice_id)
    phys = ds.res["physical"]
    row = phys[phys.invoice_id == inv.invoice_id]
    if not len(row):
        why = (
            "it is a sale, not a purchase"
            if inv.direction != "inward"
            else "it is intra-state"
            if str(inv.supplier_gstin)[:2] == str(inv.buyer_gstin)[:2]
            else f"it is below {fmt.inr(config.EWB_THRESHOLD)}"
            if float(inv.total) < config.EWB_THRESHOLD
            else "it is a duplicate booking (the original was checked)"
        )
        return {
            "headline": f"{inv.invoice_no} · not a road-checked consignment",
            "invoice": inv.invoice_no,
            "checked": False,
            "reason": f"Not checked against the road because {why}. Only inter-state "
            f"purchases of {fmt.inr(config.EWB_THRESHOLD)} or more need an e-way bill.",
            "evidence": [link("Follow the Goods", "goods")],
        }
    r = row.iloc[0]
    route = geo.load().routes.get(str(r.route_id)) if pd.notna(r.route_id) else None
    crossings = json.loads(r.crossings) if isinstance(r.crossings, str) else []
    flags = ds.flags_for(invoice_id=inv.invoice_id)
    flags = flags[flags.category == "physical"]
    ev = _evidence_of(flags.iloc[0]) if len(flags) else None
    out: dict[str, Any] = {
        "headline": f"{inv.invoice_no} · {ROAD_LABEL.get(r.verdict, r.verdict)}",
        "invoice": inv.invoice_no,
        "supplier": r.supplier,
        "invoice_total": fmt.inr(float(r.total)),
        "checked": True,
        "verdict": r.verdict,
        "verdict_label": ROAD_LABEL.get(r.verdict, r.verdict),
        "eway_bill": fmt.ewb(r.ewb_no) if pd.notna(r.ewb_no) else None,
        "vehicle": r.vehicle_no if pd.notna(r.vehicle_no) else None,
        "route": f"{route.name} ({route.highway})" if route else None,
        "distance": f"{float(r.distance_km):g} km" if pd.notna(r.distance_km) else None,
        "eway_bill_generated": fmt.stamp(pd.Timestamp(r.generated_at))
        if pd.notna(r.generated_at)
        else None,
        "window_checked": f"{float(r.window_hours):g} h" if pd.notna(r.window_hours) else None,
        "tolls_expected": int(r.plazas_expected) if pd.notna(r.plazas_expected) else None,
        "tolls_crossed": int(r.tolls_crossed) if pd.notna(r.tolls_crossed) else 0,
        "crossings": [
            {"plaza": c["plaza_name"], "at": fmt.stamp(datetime.fromisoformat(c["crossed_at"]))}
            for c in crossings
        ],
    }
    if pd.notna(r.trip_minutes):
        out["trip_time"] = fmt.duration(float(r.trip_minutes))
    if pd.notna(r.speed_kmh):
        out["average_speed"] = f"{float(r.speed_kmh):.0f} km/h"
        out["speed_limit_used"] = f"{config.MAX_AVG_SPEED_KMH:.0f} km/h"
    recycled = [x for x in str(r.recycled_with or "").split(",") if x and x != "nan"]
    if recycled:
        out["shares_trip_with"] = recycled
    if ev:
        out["finding"] = ev["summary"]
        out["notes"] = ev["notes"]
        out["flag_id"] = flags.iloc[0].flag_id
    else:
        out["finding"] = "The truck crossed the toll plazas on the declared route in time."
    out["evidence"] = [
        link(
            f"{inv.invoice_no} on the map" if r.verdict == "verified" else "Road failures",
            "goods",
            [inv.invoice_id],
        )
    ]
    return out


# ── 4. supplier_risk ─────────────────────────────────────────────────────────


def _resolve_party(ds: state.Dataset, query: str) -> str:
    q = (query or "").strip()
    if not q:
        raise ToolError("Give a supplier GSTIN or name, e.g. Kaveri Metals")
    nodes = ds.res["taint_nodes"]
    known = set(nodes.gstin)
    m = GSTIN_RE.search(q.upper())
    if m and m.group(0) in known:
        return m.group(0)
    names = {str(n): str(g) for g, n in zip(nodes.gstin, nodes["name"], strict=True)}
    best = process.extractOne(q, list(names), scorer=fuzz.WRatio, processor=utils.default_process)
    if best and best[1] >= 85:
        return names[best[0]]
    raise ToolError(f"No supplier called {q!r} in the supplier graph")


def supplier_risk(gstin: str) -> dict[str, Any]:
    ds = _ds()
    g = _resolve_party(ds, gstin)
    try:
        s = credit.supplier_risk(g)
    except HTTPException as e:
        raise ToolError(str(e.detail)) from e
    you = str(ds.meta["user_name"])
    path = [ds.names.get(x, x) for x in s["path"]]
    risky = s["at_risk"]
    itc_total = sum(i["itc"] for i in s["invoices"])
    status = (
        "at risk"
        if risky
        else "high risk (not your direct supplier)"
        if s["risk"] >= config.TAINT_AT_RISK
        else "clean"
    )
    out: dict[str, Any] = {
        "headline": f"{s['name']} · taint {s['risk']:.2f} · {status}",
        "supplier": s["name"],
        "gstin": s["gstin"],
        "state": s["state"],
        "taint_score": f"{s['risk']:.2f}",
        "at_risk_threshold": f"{config.TAINT_AT_RISK:g}",
        "at_risk": risky,
        "own_signals": s["signals"],
        "in_a_ring_itself": bool(s["ring_members"]) and s["name"] in s["ring_members"],
        "ring_upstream": s["ring_members"],
        "ring_signals": s["ring_signals"],
        "credit_chain_to_you": path + [you] if path else [],
        "hops_from_ring_to_you": s["hops_to_you"],
        "invoices_to_you": [
            {
                "invoice": i["invoice_no"],
                "date": fmt.day(datetime.fromisoformat(i["invoice_date"])),
                "total": fmt.inr(i["total"]),
                "itc": fmt.inr(i["itc"]),
                "ims": i["ims_decision"],
            }
            for i in s["invoices"][:8]
        ],
        "invoice_count": len(s["invoices"]),
        "itc_from_supplier": fmt.lakh(itc_total) if itc_total >= 1e5 else fmt.inr(itc_total),
        "itc_at_risk": fmt.lakh(s["itc_at_risk"]) if s["itc_at_risk"] else "₹0",
        "action": s["action"],
    }
    b = s["benford"]
    if b:
        out["benford"] = {
            "invoices_screened": b["n"],
            "first_digit_mad": f"{b['mad']:.3f}",
            "threshold": f"{b['threshold']:g}",
            "conforms": not b["nonconforming"],
        }
    evidence = [link(f"{s['name']} ring" if s["ring_members"] else s["name"], "credit")]
    if risky:
        evidence.append(link("IMS actions", "ims"))
    if b and b["nonconforming"]:
        evidence.append(link("Benford screen", "liability"))
    out["evidence"] = evidence
    return out


# ── 5. ims_recommendations ───────────────────────────────────────────────────


def _ims_row(r: Any) -> dict[str, Any]:
    return {
        "supplier": r.supplier_name,
        "invoice": r.invoice_no,
        "itc": fmt.inr(float(r.itc)),
        "reason": r.reason,
    }


def ims_recommendations(month: str | None = None) -> dict[str, Any]:
    ds = _ds()
    period = _check_period(ds, month)
    df = ds.res["ims"].sort_values("itc", ascending=False)
    y, m = (int(x) for x in period.split("-"))
    gstr2b = datetime(y + (m == 12), m % 12 + 1, config.GSTR2B_DAY)
    buckets = {}
    for d in ("Accept", "Reject", "Pending"):
        part = df[df.decision == d]
        itc = float(part.itc.sum())
        buckets[d.lower()] = {
            "count": len(part),
            "itc": fmt.lakh(itc) if itc >= 1e5 else fmt.inr(itc),
            "why": {RULE_WORDS.get(k, k): int(n) for k, n in part.rule.value_counts().items()},
        }
    rejects = df[df.decision == "Reject"]
    pending = df[df.decision == "Pending"]
    evidence = [link("IMS actions", "ims")]
    if (rejects.rule == "road_failed").any():
        evidence.append(
            link(f"{int((rejects.rule == 'road_failed').sum())} road failures", "goods")
        )
    if (pending.rule == "supplier_taint").any():
        evidence.append(
            link(
                f"{pending[pending.rule == 'supplier_taint'].supplier_name.iloc[0]} ring", "credit"
            )
        )
    return {
        "headline": (
            f"{buckets['accept']['count']} accept · {buckets['reject']['count']} reject · "
            f"{buckets['pending']['count']} pending"
        ),
        "period": period,
        "gstr2b_generates": fmt.day_long(gstr2b),
        "deemed_acceptance": "Records not actioned on IMS by then are deemed accepted into ITC.",
        "records": len(df),
        **buckets,
        "rules_in_order": [
            "not matched to your books → Pending",
            "tax or amount wrong → Reject",
            "physical trail failed → Reject",
            f"supplier taint ≥ {config.TAINT_AT_RISK:g} → Pending",
            "otherwise → Accept",
        ],
        "reject_list": [_ims_row(r) for r in rejects.head(12).itertuples()],
        "pending_list": [_ims_row(r) for r in pending.head(8).itertuples()],
        "evidence": evidence,
    }


# ── 6. estimate_liability ────────────────────────────────────────────────────


def estimate_liability(month: str | None = None, scenario: str = "both") -> dict[str, Any]:
    ds = _ds()
    period = _check_period(ds, month)
    sc = (scenario or "both").strip().lower().replace("-", "_").replace(" ", "_")
    if sc not in ("both", "as_filed", "reconciled", "compare"):
        raise ToolError("scenario must be as_filed, reconciled or both")
    lb = ds.summary["liability"]
    ims = ds.res["ims"]
    rej = ims[ims.decision == "Reject"]
    pend = ims[ims.decision == "Pending"]
    why = RULE_WORDS
    change = lb["net_payable_reconciled"] - lb["net_payable_filed"]
    as_filed = {
        "output_tax": fmt.lakh(lb["output_tax_filed"]),
        "itc_claimed": fmt.lakh(lb["itc_claimed"]),
        "net_payable": fmt.lakh(lb["net_payable_filed"]),
        "note": "As filed, every supplier invoice on IMS is deemed accepted into ITC.",
    }
    reconciled = {
        "output_tax": fmt.lakh(lb["output_tax_reconciled"]),
        "itc_claimed": fmt.lakh(lb["itc_claimed"]),
        "itc_rejected": {
            "amount": fmt.lakh(lb["itc_rejected"]),
            "invoices": len(rej),
            "because": {why.get(k, k): int(n) for k, n in rej.rule.value_counts().items()},
        },
        "itc_held_pending": {
            "amount": fmt.lakh(lb["itc_at_risk"]),
            "invoices": len(pend),
            "suppliers": sorted(set(pend.supplier_name)),
            "because": {why.get(k, k): int(n) for k, n in pend.rule.value_counts().items()},
        },
        "itc_eligible": fmt.lakh(lb["itc_eligible"]),
        "net_payable": fmt.lakh(lb["net_payable_reconciled"]),
        "formula": (
            f"Output tax {fmt.lakh(lb['output_tax_reconciled'])} − eligible ITC "
            f"{fmt.lakh(lb['itc_eligible'])} = {fmt.lakh(lb['net_payable_reconciled'])}"
        ),
    }
    out: dict[str, Any] = {
        "headline": (
            f"net payable {fmt.lakh(lb['net_payable_filed'])} → "
            f"{fmt.lakh(lb['net_payable_reconciled'])}"
        ),
        "period": period,
    }
    if sc in ("both", "compare", "as_filed"):
        out["as_filed"] = as_filed
    if sc in ("both", "compare", "reconciled"):
        out["reconciled"] = reconciled
    if sc in ("both", "compare"):
        out["change_in_net_payable"] = ("+" if change >= 0 else "") + fmt.lakh(change)
        out["output_tax_changed"] = abs(lb["output_tax_reconciled"] - lb["output_tax_filed"]) > 1
        out["under_reported_output_tax"] = fmt.lakh(lb["under_reported_output"])
        out["exposure_caught"] = fmt.lakh(lb["exposure"])
        out["by_tax_head"] = [
            {
                "head": h.head,
                "output": fmt.inr(h.output_reconciled),
                "eligible_itc": fmt.inr(h.itc_eligible),
                "net": fmt.inr(h.net_reconciled),
            }
            for h in ds.res["liability_heads"].itertuples()
        ]
    evidence = [link("Liability", "liability"), link("IMS actions", "ims")]
    if (rej.rule == "road_failed").any():
        evidence.append(link(f"{int((rej.rule == 'road_failed').sum())} road failures", "goods"))
    if (pend.rule == "supplier_taint").any():
        evidence.append(
            link(f"{pend[pend.rule == 'supplier_taint'].supplier_name.iloc[0]} ring", "credit")
        )
    out["evidence"] = evidence
    return out


# ── 7. explain ───────────────────────────────────────────────────────────────


def _flag_full(row: pd.Series) -> dict[str, Any]:
    ev = _evidence_of(row)
    return {
        **_flag_brief(row),
        "category": row.category,
        "chain": [
            {
                "source": c["source"],
                "record": c["label"],
                "fields": {k: _plain_text(v) for k, v in c["fields"].items()},
            }
            for c in ev["chain"]
        ],
        "notes": ev["notes"],
    }


def explain(flag_id: str) -> dict[str, Any]:
    """A flag_id (e.g. paper_only:i0008), or an invoice number / GSTIN to explain all of its
    findings."""
    ds = _ds()
    f = _flags(ds)
    key = (flag_id or "").strip()
    hit = f[f.flag_id == key]
    subject = key
    if not len(hit):
        hit = f[f.ref.str.upper() == key.upper()]
    if not len(hit):
        try:
            inv = _find_invoice(ds, key)
        except ToolError:
            raise ToolError(
                f"No finding {key!r}. Use a flag_id from list_discrepancies, an invoice number "
                "or a supplier GSTIN."
            ) from None
        hit = ds.flags_for(invoice_id=inv.invoice_id)
        subject = inv.invoice_no
        if not len(hit):
            st = ds.status.loc[inv.invoice_id]
            return {
                "headline": f"{inv.invoice_no} · no findings",
                "invoice": inv.invoice_no,
                "status": st.status,
                "explanation": "No findings: it matched the books"
                + (", the bank" if int(st.payments) else "")
                + (", IMS" if st.ims_decision == "Accept" else "")
                + (" and the road" if st.physical == "verified" else "")
                + ".",
                "evidence": [link("Overview", "overview")],
            }
    serious = hit.category != "anomaly"
    hit = hit.assign(_s=serious).sort_values(["_s", "impact"], ascending=False).head(5)
    screens = []
    for cat in hit[hit._s].category.unique() if hit._s.any() else hit.category.unique():
        scr = CATEGORY_SCREEN.get(str(cat), "discrepancies")
        if scr not in screens:
            screens.append(scr)
    out: dict[str, Any] = {
        "headline": f"{len(hit)} finding{'s' if len(hit) != 1 else ''} on {subject}",
        "findings": [_flag_full(r) for _, r in hit.iterrows()],
    }
    iid = hit.invoice_id.dropna()
    if len(iid) and iid.nunique() == 1:
        ims = ds.res["ims"]
        rec = ims[ims.invoice_id == iid.iloc[0]]
        if len(rec):
            out["ims_autopilot"] = {"decision": rec.iloc[0].decision, "reason": rec.iloc[0].reason}
        out["status"] = ds.status.loc[iid.iloc[0]].status
    out["evidence"] = [link(SCREEN_LABEL[s], s, list(hit.flag_id)) for s in screens]
    return out


# ── registry (shared by the copilot and the MCP server) ──────────────────────


@dataclass(frozen=True)
class Tool:
    name: str
    fn: Callable[..., dict[str, Any]]
    description: str
    params: dict[str, dict[str, Any]] = field(default_factory=dict)
    required: tuple[str, ...] = ()

    def schema(self) -> dict[str, Any]:
        """OpenAI-style function schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.params,
                    "required": list(self.required),
                },
            },
        }


_MONTH = {"type": "string", "description": "YYYY-MM, e.g. 2026-09"}
TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "reconcile_period",
            reconcile_period,
            "The month at a glance: invoices reconciled, matched, discrepancies, duplicates, "
            "unmatched, the matching funnel, road check, supplier rings, IMS and liability.",
            {"gstin": {"type": "string", "description": "your GSTIN"}, "month": _MONTH},
        ),
        Tool(
            "list_discrepancies",
            list_discrepancies,
            "Findings sorted by ₹ at stake. type: a kind (amount, date, invoice_id, tax_rate, "
            "tax_head, duplicate, near_duplicate, unmatched, paper_only, impossible_journey, "
            "recycled_ewb, ring_taint, benford …) or a group (discrepancy, duplicate, physical "
            "a.k.a. road, credit, gap, anomaly, tax). Default: discrepancies and duplicates.",
            {
                "type": {"type": "string"},
                "min_amount": {"type": "number", "description": "minimum ₹ at stake"},
                "limit": {"type": "integer", "description": "max items, default 8"},
            },
        ),
        Tool(
            "trace_goods",
            trace_goods,
            "Follow one purchase's goods: e-way bill, truck, route, toll crossings, speed and "
            "the road verdict.",
            {"invoice_id": {"type": "string", "description": "invoice number (MB/0877) or id"}},
            ("invoice_id",),
        ),
        Tool(
            "supplier_risk",
            supplier_risk,
            "Is a supplier safe? Taint score, circular-trading ring upstream, ring signals, "
            "Benford screen, its invoices to you, ITC at risk and what to do. Works with a "
            "name; no GSTIN needed.",
            {
                "gstin": {
                    "type": "string",
                    "description": "the supplier's GSTIN or its name, e.g. 'Kaveri Metals'",
                }
            },
            ("gstin",),
        ),
        Tool(
            "ims_recommendations",
            ims_recommendations,
            "IMS Autopilot: how many supplier invoices to Accept, Reject or keep Pending before "
            "GSTR-2B, the ITC in each, and the reason for every Reject and Pending.",
            {"month": _MONTH},
        ),
        Tool(
            "estimate_liability",
            estimate_liability,
            "Net GST payable as filed vs after reconciliation: output tax, ITC claimed, "
            "rejected, held pending, eligible, the change and why, by tax head.",
            {
                "month": _MONTH,
                "scenario": {"type": "string", "enum": ["both", "as_filed", "reconciled"]},
            },
        ),
        Tool(
            "explain",
            explain,
            "The full evidence behind a finding: recorded vs expected and the chain of source "
            "records. Takes a flag_id from list_discrepancies, an invoice number or a GSTIN.",
            {"flag_id": {"type": "string"}},
            ("flag_id",),
        ),
    ]
}


def schemas() -> list[dict[str, Any]]:
    return [t.schema() for t in TOOLS.values()]


def call(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a tool by name. Problems come back as {"error": ...} rather than raising, so a
    model can read them and try again."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"No tool {name!r}. Tools: {', '.join(TOOLS)}"}
    args = {k: v for k, v in (args or {}).items() if k in tool.params and v is not None}
    missing = [r for r in tool.required if r not in args]
    if missing:
        return {"error": f"{name} needs {', '.join(missing)}"}
    try:
        return tool.fn(**args)
    except ToolError as e:
        return {"error": str(e)}
    except (TypeError, ValueError) as e:
        return {"error": f"Bad arguments for {name}: {e}"}


def signature(name: str, args: dict[str, Any] | None) -> str:
    """estimate_liability(month='2026-09')"""
    inner = ", ".join(f"{k}={v!r}" for k, v in (args or {}).items() if v is not None)
    return f"{name}({inner})"
