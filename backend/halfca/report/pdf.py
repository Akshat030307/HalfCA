"""The audit report: the reconciled month as a PDF (WeasyPrint, HTML → PDF).

    make report                      → data/audit-report-2026-09.pdf
    GET /api/report.pdf              → the same, for the current dataset

Everything in it comes from the stored reconciliation; nothing is asked of a model.
Every finding that needs action is printed with its evidence chain (golden rule 5).
Rendered PDFs are cached per dataset, IMS approval state and template version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from halfca import config, fmt
from halfca.api import state
from halfca.api.routers import credit, goods, overview
from halfca.api.routers import ims as ims_router
from halfca.data.build import fingerprint
from halfca.engines.common import KINDS

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"
FONTS = HERE / "fonts"
IST = timezone(timedelta(hours=5, minutes=30))
CATEGORY_ORDER = ["physical", "credit", "discrepancy", "duplicate"]  # evidence appendix
CATEGORY_TITLE = {
    "physical": "Road check",
    "credit": "Supplier network",
    "discrepancy": "Discrepancies",
    "duplicate": "Duplicates",
}
MONEY_KEYS = ("total", "taxable", "amount", "igst", "cgst", "sgst", "itc", "value", "tax", "impact")
VERDICT = {
    "paper_only": "Paper-only supply",
    "impossible_journey": "Impossible journey",
    "recycled_ewb": "Recycled e-way bill",
    "missing_ewb": "Missing e-way bill",
}


# ── formatting helpers (also Jinja filters) ──────────────────────────────────


def _date(v: Any) -> str:
    try:
        return fmt.day_long(pd.Timestamp(v))
    except (ValueError, TypeError):
        return str(v)


def field_text(key: str, v: Any) -> str:
    """An evidence field as a person would write it."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if isinstance(v, list):
        return "; ".join(str(x) for x in v) or "—"
    k = key.lower()
    if isinstance(v, str) and len(v) >= 10 and v[4:5] == "-" and v[7:8] == "-":
        try:
            ts = pd.Timestamp(v)
            return fmt.day_long(ts) + ("" if ts == ts.normalize() else ts.strftime(", %H:%M"))
        except ValueError:
            return v
    if k in ("ewb_no", "ewb") and str(v).isdigit():
        return fmt.ewb(str(v))
    if isinstance(v, int | float) and not isinstance(v, bool):
        if any(m in k for m in MONEY_KEYS) and "rate" not in k:
            return fmt.inr(float(v))
        if k in ("rate",):
            return f"{float(v):g}%"
        return f"{float(v):g}" if isinstance(v, float) else str(v)
    return str(v)


LABELS = {
    "ewb_no": "E-way bill",
    "ewb": "E-way bill",
    "hsn": "HSN",
    "itc": "ITC",
    "gstin": "GSTIN",
    "party_gstin": "Party GSTIN",
    "invoice_no": "Invoice no.",
    "from_city": "From",
    "distance_km": "Distance (km)",
    "generated_at": "Generated",
    "valid_until": "Valid until",
    "crossed_at": "Crossed",
    "utr": "UTR",
    "mad": "MAD",
}


def label(key: str) -> str:
    return LABELS.get(key, key.replace("_", " ").capitalize())


# ── charts (inline SVG; WeasyPrint renders them) ─────────────────────────────


def waterfall_svg(steps: list[dict[str, Any]]) -> str:
    w, h, top, base = 460, 190, 18, 160
    peak = max(abs(s["value"]) for s in steps) or 1
    scale = (base - top) / peak
    colors = {
        "Claimed": "#64748B",
        "Rejected": "#DC2626",
        "At risk": "#C98A00",
        "Eligible": "#16A34A",
    }
    slot = w / len(steps)
    bw = slot * 0.52
    parts, level = [], 0.0
    for i, s in enumerate(steps):
        v = s["value"]
        if s["kind"] == "total":
            y0, y1 = 0.0, v
            level = v
        else:
            y0, y1 = level + v, level
            level += v
        x = i * slot + (slot - bw) / 2
        y_top = base - max(y0, y1) * scale
        height = abs(y1 - y0) * scale
        c = colors.get(s["step"], "#F26B1D")
        parts.append(
            f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bw:.1f}" height="{max(height, 1):.1f}" '
            f'rx="4" fill="{c}" stroke="#1C130C" stroke-width="1.2"/>'
            f'<text x="{x + bw / 2:.1f}" y="{y_top - 5:.1f}" text-anchor="middle" '
            f'font-size="11" font-weight="700" fill="#1C130C">'
            f"{'−' if v < 0 else ''}{abs(v) / 1e5:.1f}</text>"
            f'<text x="{x + bw / 2:.1f}" y="{base + 16:.1f}" text-anchor="middle" '
            f'font-size="10" fill="#7B6352">{s["step"]}</text>'
        )
    axis = f'<line x1="0" x2="{w}" y1="{base}" y2="{base}" stroke="#EBCFB8" stroke-width="1.5"/>'
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" '
        f'font-family="Inter">{axis}{"".join(parts)}</svg>'
    )


def benford_svg(observed: list[float], expected: list[float]) -> str:
    w, h, top, base = 460, 150, 10, 126
    peak = max(observed + expected + [0.01])
    y = lambda v: base - v / peak * (base - top)  # noqa: E731
    slot = w / 9
    bw = slot * 0.55
    bars, labels = [], []
    for i, o in enumerate(observed):
        cx = slot * i + slot / 2
        bars.append(
            f'<rect x="{cx - bw / 2:.1f}" y="{y(o):.1f}" width="{bw:.1f}" '
            f'height="{base - y(o):.1f}" rx="3" fill="#C98A00"/>'
        )
        labels.append(
            f'<text x="{cx:.1f}" y="{base + 14}" text-anchor="middle" font-size="10" '
            f'fill="#7B6352">{i + 1}</text>'
        )
    pts = " ".join(f"{slot * i + slot / 2:.1f},{y(e):.1f}" for i, e in enumerate(expected))
    dots = "".join(
        f'<circle cx="{slot * i + slot / 2:.1f}" cy="{y(e):.1f}" r="2.8" fill="#1C130C"/>'
        for i, e in enumerate(expected)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" '
        f'font-family="Inter"><line x1="0" x2="{w}" y1="{base}" y2="{base}" stroke="#EBCFB8"/>'
        f"{''.join(bars)}{''.join(labels)}"
        f'<polyline points="{pts}" fill="none" stroke="#1C130C" stroke-width="1.6" '
        f'stroke-dasharray="4 4"/>{dots}</svg>'
    )


# ── the report's data ────────────────────────────────────────────────────────


def _evidence(row: pd.Series) -> dict[str, Any]:
    ev = row.evidence
    return json.loads(ev) if isinstance(ev, str) else dict(ev)


def _finding(row: pd.Series) -> dict[str, Any]:
    ev = _evidence(row)
    return {
        "flag_id": row.flag_id,
        "kind": row.kind,
        "label": row.label,
        "category": row.category,
        "ref": row.ref,
        "counterparty": row.counterparty,
        "gstin": row.gstin,
        "title": row.title,
        "recorded": row.recorded,
        "expected": row.expected,
        "impact": float(row.impact or 0),
        "summary": ev["summary"],
        "recorded_fields": ev["recorded"],
        "expected_fields": ev["expected"],
        "chain": ev["chain"],
        "notes": ev["notes"],
    }


def context(ds: state.Dataset | None = None) -> dict[str, Any]:
    ds = ds or state.current()
    s = ds.summary
    summ = overview.summary()
    fun = overview.funnel()
    liab = ims_router.liability()
    ims = ims_router.ims()
    trips = goods._trips(ds)
    failed_trips = [t for t in trips if t["verdict"] in VERDICT]
    flags = ds.flags

    # Road failures, each with its finding.
    road = []
    for t in sorted(failed_trips, key=lambda t: (t["verdict"], t["invoice_no"])):
        f = flags[(flags.invoice_id == t["invoice_id"]) & (flags.category == "physical")]
        road.append({**t, "finding": _finding(f.iloc[0]) if len(f) else None})

    # Suppliers at risk and the rings behind them.
    risky = [credit.supplier_risk(g) for g in ds.res["taint_nodes"].query("at_risk").gstin]
    for r in risky:
        r["path_names"] = [ds.names.get(g, g) for g in r["path"]] + [ds.meta["user_name"]]

    # IMS actions: every Reject and Pending.
    actions = [r for r in ims["records"] if r["decision"] != "Accept"]
    accept_itc = sum(r["itc"] for r in ims["records"] if r["decision"] == "Accept")

    # Discrepancies register (the 38 + 7 on reconciled invoices) and the evidence appendix.
    register = overview.discrepancies(type=None, category=None)["items"]
    appendix_rows = flags[flags.category.isin(CATEGORY_ORDER)]
    status = ds.status.status
    on_paired = appendix_rows.invoice_id.map(
        lambda i: (
            i is None or (isinstance(i, float) and math.isnan(i)) or status.get(i) != "unmatched"
        )
    )
    appendix_rows = appendix_rows[on_paired]
    appendix = []
    for cat in CATEGORY_ORDER:
        part = appendix_rows[appendix_rows.category == cat].sort_values("impact", ascending=False)
        if len(part):
            appendix.append(
                {"title": CATEGORY_TITLE[cat], "items": [_finding(r) for _, r in part.iterrows()]}
            )

    lb = liab["summary"]
    period = str(ds.meta["period"])
    gaps = {KINDS.get(k, (k, k))[1]: n for k, n in s.get("gaps", {}).items()}
    anomalies = {KINDS.get(k, (k, k))[1]: n for k, n in s.get("anomalies", {}).items()}
    docs = s.get("documents", {}).get("counts", {})
    bf = credit.benford_for(ds, liab["benford_focus"]) if liab["benford_focus"] else None
    stage4 = next((st for st in fun["stages"] if st["stage"] == 4), None)
    return {
        "company": ds.meta["user_name"],
        "gstin": ds.meta["user_gstin"],
        "city": config.USER_CITY,
        "period": period,
        "period_label": datetime.strptime(period, "%Y-%m").strftime("%B %Y"),
        "as_of": datetime.fromisoformat(str(ds.meta["as_of"])).strftime("%d %b %Y, %H:%M IST"),
        "generated": datetime.now(IST).strftime("%d %b %Y, %H:%M IST"),
        "dataset_id": ds.dataset_id,
        "scenario": ds.meta.get("scenario"),
        "kpis": summ["kpis"],
        "donut": summ["donut"],
        "types": summ["discrepancy_types"],
        "physical": summ["physical"],
        "ims_counts": ims["counts"],
        "approved_at": ims["approved_at"],
        "gstr2b": _date(ims["gstr2b_date"]),
        "liability": lb,
        "change": lb["net_payable_reconciled"] - lb["net_payable_filed"],
        "waterfall_svg": waterfall_svg(liab["waterfall"]),
        "heads": liab["heads"],
        "funnel": fun["stages"],
        "stage4": stage4,
        "llm": fun["llm"],
        "unmatched": fun["unmatched"],
        "road": road,
        "rings": s["rings"],
        "risky": risky,
        "benford": bf,
        "benford_svg": benford_svg(bf["observed"], bf["expected"]) if bf else None,
        "actions": actions,
        "accept_itc": accept_itc,
        "register": register,
        "appendix": appendix,
        "appendix_count": sum(len(a["items"]) for a in appendix),
        "gaps": gaps,
        "anomalies": anomalies,
        "documents": docs,
        "gstins": s.get("gstins", {}),
        "taint_threshold": config.TAINT_AT_RISK,
        "speed_limit": config.MAX_AVG_SPEED_KMH,
    }


# ── rendering ────────────────────────────────────────────────────────────────


def _env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        inr=fmt.inr,
        lakh=fmt.lakh,
        date=_date,
        ewb=lambda v: fmt.ewb(v) if v else "—",
        field=lambda v, k="": field_text(k, v),
        label=label,
        count=lambda n: f"{int(n):,}",
        pct=lambda v: f"{v * 100:.1f}%",
    )
    return env


def render_html(ctx: dict[str, Any]) -> str:
    fonts = {p.stem.split("[")[0].split("-")[0]: p.as_uri() for p in FONTS.glob("*.ttf")}
    return _env().get_template("audit.html.j2").render(**ctx, fonts=fonts)


def _cache_key(ds: state.Dataset) -> str:
    _, approved_at = state.ims_approvals(ds.dataset_id)
    h = hashlib.sha256()
    h.update(f"{ds.dataset_id}|{approved_at}|{fingerprint()}".encode())
    for f in sorted(TEMPLATES.iterdir()):
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


def report_path(ds: state.Dataset | None = None) -> Path:
    """The PDF for the current dataset, rendered once and reused until anything changes."""
    from weasyprint import HTML  # heavy import; only when rendering
    from weasyprint.text.fonts import FontConfiguration

    ds = ds or state.current()
    folder = config.DATA_DIR / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"audit-{ds.meta['period']}-{_cache_key(ds)}.pdf"
    if out.is_file():
        return out
    for old in folder.glob("audit-*.pdf"):
        old.unlink(missing_ok=True)
    html = render_html(context(ds))
    tmp = out.with_suffix(f".{datetime.now(UTC):%H%M%S%f}.tmp")
    HTML(string=html, base_url=str(TEMPLATES)).write_pdf(tmp, font_config=FontConfiguration())
    tmp.replace(out)
    return out


def download_name(ds: state.Dataset | None = None) -> str:
    ds = ds or state.current()
    return f"Half-CA-audit-report-{ds.meta['period']}.pdf"


def main() -> None:
    ap = argparse.ArgumentParser(description="Write the audit report PDF for the current dataset")
    ap.add_argument("--out", type=Path, help="default: data/audit-report-<period>.pdf")
    ap.add_argument("--html", action="store_true", help="also write the HTML next to it")
    args = ap.parse_args()
    ds = state.current()
    src = report_path(ds)
    out = args.out or config.DATA_DIR / f"audit-report-{ds.meta['period']}.pdf"
    out.write_bytes(src.read_bytes())
    if args.html:
        out.with_suffix(".html").write_text(render_html(context(ds)))
    print(f"→ {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
