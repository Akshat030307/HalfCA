"""Copilot: answers questions by calling the seven tools, and shows its working.

With an LLM: a tool-use loop (at most COPILOT_MAX_TOOL_CALLS calls), then the model writes
the answer from the tool results. Every number in that answer must appear in a tool
result, the question or the background facts in the prompt. The model gets one chance to
rewrite an answer with an untraced number; after that the template answer is used.

Without an LLM, or when the model fails: rules pick the tools from the question and a
template writes the answer from the same tool outputs.

`answer()` yields events for the SSE stream:
  tool       {name, args, call}            a tool call starts
  tool_done  {name, call, headline, ok}    and finishes
  token      {text}                        the answer, a word at a time
  evidence   {items: [{label, href}]}      chips to the screens behind the answer
  done       {mode, model, tool_calls, numbers_checked, note}
"""

from __future__ import annotations

import contextlib
import json
import re
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from halfca import config, fmt, tools
from halfca.ai import llm

SUGGESTIONS = [
    "Why did my liability go up?",
    "Which invoices failed the road check?",
    "Is Kaveri Metals safe to buy from?",
]
WORD_DELAY_S = 0.022  # pacing of the streamed answer
MAX_EVIDENCE = 4
HISTORY_TURNS = 6
LLM_PATIENCE_S = 8.0  # longer rate-limit waits fall back to the template answer
_busy = threading.Semaphore(2)


@dataclass
class Event:
    type: str
    data: dict[str, Any]


@dataclass
class Trace:
    """What the tools returned while answering one question."""

    calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = field(default_factory=list)

    def run(self, name: str, args: dict[str, Any]) -> Iterator[Event]:
        call = tools.signature(name, args)
        yield Event("tool", {"name": name, "args": args, "call": call})
        result = tools.call(name, args)
        self.calls.append((name, args, result))
        yield Event(
            "tool_done",
            {
                "name": name,
                "call": call,
                "ok": "error" not in result,
                "headline": result.get("headline") or result.get("error", ""),
            },
        )

    def result(self, name: str) -> dict[str, Any]:
        for n, _, r in reversed(self.calls):
            if n == name and "error" not in r:
                return r
        return {}

    def has(self, name: str, args: dict[str, Any]) -> bool:
        return any(n == name and a == args for n, a, _ in self.calls)

    def evidence(self) -> list[dict[str, str]]:
        """Chips: every link from the first tool that answered, then the main link of
        each later one."""
        seen: dict[str, dict[str, str]] = {}
        ok = [r for _, _, r in self.calls if "error" not in r]
        for i, r in enumerate(ok):
            for e in r.get("evidence", [])[: None if i == 0 else 1]:
                if e["label"] not in seen and len(seen) < MAX_EVIDENCE:
                    seen[e["label"]] = {"label": e["label"], "href": e["href"]}
        return list(seen.values())

    def sources(self) -> str:
        return json.dumps([r for _, _, r in self.calls], ensure_ascii=False)


# ── number guard: every figure in an answer must come from somewhere ─────────

numbers = fmt.numbers_in


def untraced(answer: str, sources: str) -> list[str]:
    """Numbers in `answer` that appear nowhere in `sources`. Small integers (counts, days)
    and years are allowed: they are words more than figures."""
    allowed = set(numbers(sources))
    bad = []
    for n in numbers(answer):
        if n in allowed:
            continue
        if "." not in n and (int(n) <= 31 or 2017 <= int(n) <= 2030):
            continue
        bad.append(n)
    return bad


# ── intents for the template path ────────────────────────────────────────────


def _find_invoice_no(q: str) -> str | None:
    try:
        nos = tools._ds().invoices.invoice_no
    except tools.ToolError:
        return None
    known = {str(n).upper(): str(n) for n in nos}
    for tok in re.findall(r"[A-Za-z0-9][A-Za-z0-9/\-_.]*\d", q):
        if tok.upper() in known:
            return known[tok.upper()]
    return None


def _find_party(q: str) -> str | None:
    """A supplier named in the question (full name, distinctive first word or GSTIN)."""
    try:
        ds = tools._ds()
    except tools.ToolError:
        return None
    m = tools.GSTIN_RE.search(q.upper())
    if m:
        return m.group(0)
    nodes = ds.res["taint_nodes"]
    names = [str(n) for n in nodes["name"]]
    low = q.lower()
    for n in sorted(names, key=len, reverse=True):
        if n.lower() in low:
            return n
    firsts: dict[str, list[str]] = {}
    for n in names:
        firsts.setdefault(n.split()[0].lower(), []).append(n)
    words = set(re.findall(r"[a-z]+", low))
    for first, owners in firsts.items():
        if len(owners) == 1 and len(first) >= 4 and first in words:
            return owners[0]
    return None


MONTHS = "january february march april may june july august september october november december"


def _other_month(q: str, period: str | None) -> str | None:
    """'What about August?' → 'August 2026' when the loaded month is another one."""
    if not period:
        return None
    year = re.search(r"\b(20\d\d)\b", q)
    for i, name in enumerate(MONTHS.split(), start=1):
        if re.search(rf"\b({name}|{name[:3]})\b", q.lower()):
            y = year.group(1) if year else period[:4]
            if f"{y}-{i:02d}" != period:
                return f"{name.title()} {y}"
    return None


Plan = list[tuple[str, dict[str, Any]]]
INTENTS: list[tuple[str, str, Plan]] = [
    (
        "liability",
        r"liabilit|payable|\bowe\b|pay (more|less)|net tax|tax bill|go(ne)? up|went up|"
        r"increase|how much.*(pay|tax)|itc",
        [("estimate_liability", {"month": None}), ("ims_recommendations", {"month": None})],
    ),
    (
        "road",
        r"road|toll|truck|goods|e-?way|ewb|physical|journey|transport|vehicle|lorry|fastag",
        [("list_discrepancies", {"type": "road"}), ("ims_recommendations", {"month": None})],
    ),
    (
        "ims",
        r"\bims\b|accept|reject|pending|gstr-?2b|\b2b\b|approve",
        [("ims_recommendations", {})],
    ),
    ("duplicates", r"duplicat|twice|double", [("list_discrepancies", {"type": "duplicate"})]),
    (
        "unmatched",
        r"unmatched|no partner|not booked|missing",
        [("list_discrepancies", {"type": "unmatched"})],
    ),
    (
        "discrepancy",
        r"discrepan|mismatch|wrong|error|tax rate|slab|tax head|igst|cgst|amount|date|flag",
        [("list_discrepancies", {})],
    ),
    (
        "ring",
        r"ring|taint|circular|shell|risky|supplier|vendor|safe",
        [("list_discrepancies", {"type": "credit"})],
    ),
]


def plan_for(question: str) -> tuple[str, Plan]:
    period = None
    with contextlib.suppress(tools.ToolError):
        period = str(tools._ds().meta["period"])

    def fill(plan: Plan) -> Plan:
        return [(n, {k: (period if v is None else v) for k, v in a.items()}) for n, a in plan]

    asked = _other_month(question, period)
    if asked:
        return "overview", [("reconcile_period", {"month": asked})]
    inv = _find_invoice_no(question)
    if inv:
        return "invoice", [("explain", {"flag_id": inv}), ("trace_goods", {"invoice_id": inv})]
    party = _find_party(question)
    if party:
        return "supplier", [("supplier_risk", {"gstin": party})]
    q = question.lower()
    for name, pattern, plan in INTENTS:
        if re.search(pattern, q):
            return name, fill(plan)
    return "overview", [("reconcile_period", {"month": period})]


# ── templates: the answer in words, built only from tool outputs ─────────────


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def _because(d: dict[str, int]) -> str:
    return _join([f"{n} {why}" for why, n in d.items()])


def _t_liability(t: Trace) -> str:
    L, ims = t.result("estimate_liability"), t.result("ims_recommendations")
    if not L:
        return ""
    f, r = L["as_filed"], L["reconciled"]
    change = L["change_in_net_payable"]
    more = "more" if change.startswith("+") else "less"
    parts = [
        f"Your net GST payable for the month goes from **{f['net_payable']}** as filed to "
        f"**{r['net_payable']}** after reconciliation, {change.lstrip('+')} {more}."
    ]
    if not L.get("output_tax_changed"):
        parts.append(
            f"Output tax is {r['output_tax']} either way, so the whole change is input tax credit."
        )
    rej, pend = r["itc_rejected"], r["itc_held_pending"]
    s = f"Of the {f['itc_claimed']} ITC you would claim as filed, {rej['amount']} on "
    s += f"{rej['invoices']} invoices is rejected ({_because(rej['because'])})"
    if pend["invoices"]:
        why = pend["because"]
        names = _join(pend["suppliers"])
        if len(why) == 1 and "ring" in next(iter(why)):
            who = "that supplier is" if len(pend["suppliers"]) == 1 else "those suppliers are"
            tail = f"because {who} fed by a circular-trading ring"
        else:
            tail = f"({_because(why)})"
        s += (
            f", and {pend['amount']} on {pend['invoices']} invoices from **{names}** is held "
            f"Pending {tail}"
        )
    parts.append(s + ".")
    parts.append(f"That leaves {r['itc_eligible']} eligible: {r['formula']}.")
    if ims:
        parts.append(
            f"GSTR-2B generates on {ims['gstr2b_generates']}; act on IMS before then, or the "
            "bad credit is deemed accepted."
        )
    return " ".join(parts)


def _t_road(t: Trace) -> str:
    D, ims = t.result("list_discrepancies"), t.result("ims_recommendations")
    if not D:
        return ""
    if not D["count"]:
        return "No consignment failed the road check: every e-way bill was seen at the tolls."
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for it in D["items"]:
        groups.setdefault((it["type"], it["counterparty"]), []).append(it)
    lines = []
    for (kind, party), items in groups.items():
        nos = _join([f"**{i['invoice']}**" for i in items])
        detail = items[0]["recorded"] or ""
        if len(items) > 1 and kind == "Recycled e-way bill":
            detail = f"one truck trip on {len(items)} invoices"
        lines.append(f"{nos} from {party}: {kind.lower()} ({detail})")
    out = (
        f"**{D['count']} invoices** passed every paper check but failed the road, with "
        f"{D['total_at_stake']} of ITC at stake. " + "; ".join(lines) + "."
    )
    if D.get("more_not_shown"):
        out += f" {D['more_not_shown']} more are on the Follow the Goods screen."
    if ims:
        road = {i["invoice"] for i in ims.get("reject_list", [])}
        shown = {i["invoice"] for i in D["items"]}
        if shown and shown <= road:
            out += " IMS Autopilot rejects all of them, so that credit stays out of your return."
    return out


SIGNAL_ORDER = ("registered", "e-way", "turnover", "missed", "shares")


def _ring_badges(signals: list[str], n: int = 3) -> list[str]:
    """'Nexo Metals: Zero e-way bills on goods trade' → 'Nexo Metals (zero e-way bills on
    goods trade)', one per firm, the most telling kinds first."""
    seen, out = set(), []
    parsed = []
    for s in signals:
        firm, _, rest = s.partition(": ")
        first = rest.split("; ")[0]
        rank = next((i for i, k in enumerate(SIGNAL_ORDER) if k in first.lower()), 9)
        parsed.append((rank, firm, first))
    for _, firm, first in sorted(parsed, key=lambda x: x[0]):
        if firm not in seen and first:
            seen.add(firm)
            out.append(f"{firm} ({first[0].lower() + first[1:]})")
    return out[:n]


def _t_supplier(t: Trace) -> str:
    S = t.result("supplier_risk")
    if not S:
        return ""
    name = f"**{S['supplier']}**"
    if S["at_risk"]:
        out = [
            f"Not right now. {name} ({S['gstin']}) has a taint score of **{S['taint_score']}**, "
            f"above the {S['at_risk_threshold']} line."
        ]
        ring = S["ring_upstream"]
        chain = S["credit_chain_to_you"]
        if ring and chain:
            loop = " → ".join(ring + [ring[0]])
            out.append(
                f"It buys from **{chain[0]}**, part of a {len(ring)}-firm circular-trading ring "
                f"({loop})."
            )
        badges = _ring_badges(S["ring_signals"])
        if badges:
            out.append(f"Warning signs in the ring: {_join(badges)}.")
        b = S.get("benford")
        if b and not b["conforms"]:
            out.append(
                f"Its own invoices fail Benford's first-digit test too (MAD {b['first_digit_mad']}"
                f" against {b['threshold']}, {b['invoices_screened']} invoices)."
            )
        out.append(
            f"Your {S['invoice_count']} invoices from it carry {S['itc_at_risk']} of ITC. "
            + S["action"]
        )
        return " ".join(out)
    if S["ring_upstream"] and S["in_a_ring_itself"]:
        return (
            f"{name} is itself part of a circular-trading ring "
            f"({_join(S['ring_upstream'])}), taint score {S['taint_score']}. You do not buy "
            "from it directly, but credit that flows through it is suspect."
        )
    signals = S["own_signals"]
    out = [
        f"{name} looks fine: taint score {S['taint_score']}, under the "
        f"{S['at_risk_threshold']} line, with {S['invoice_count']} invoices to you carrying "
        f"{S['itc_from_supplier']} of ITC."
    ]
    if signals:
        out.append("Minor signals to keep an eye on: " + "; ".join(signals) + ".")
    return " ".join(out)


def _t_ims(t: Trace) -> str:
    I = t.result("ims_recommendations")  # noqa: E741
    if not I:
        return ""
    a, r, p = I["accept"], I["reject"], I["pending"]
    out = [
        f"Of {I['records']} supplier invoices on IMS, Autopilot says Accept **{a['count']}** "
        f"({a['itc']} ITC), Reject **{r['count']}** ({r['itc']}) and keep **{p['count']}** "
        f"Pending ({p['itc']})."
    ]
    if r["count"]:
        out.append(f"Rejects: {_because(r['why'])}.")
    if p["count"]:
        out.append(f"Pending: {_because(p['why'])}.")
    top = I["reject_list"][:3]
    if top:
        out.append(
            "Biggest rejects: "
            + "; ".join(f"**{x['invoice']}** {x['supplier']} ({x['reason']})" for x in top)
            + "."
        )
    out.append(f"GSTR-2B generates on {I['gstr2b_generates']}. {I['deemed_acceptance']}")
    return " ".join(out)


def _t_list(t: Trace) -> str:
    D = t.result("list_discrepancies")
    if not D:
        return ""
    if not D["count"]:
        return f"Nothing found for {D['filter']}."
    kinds = _join([f"{n} {k.lower()}" for k, n in D["by_type"].items()])
    out = [f"**{D['count']}** found ({kinds}), {D['total_at_stake']} at stake."]
    for it in D["items"][:3]:
        s = f"**{it['invoice']}** {it['counterparty']}: {it['title']}"
        if it["recorded"] and it["expected"]:
            s += f" (recorded {it['recorded']}, expected {it['expected']})"
        out.append(s + ".")
    if D["count"] > 3:
        out.append("The rest are on the screens linked below.")
    return " ".join(out)


def _t_invoice(t: Trace) -> str:
    E, G = t.result("explain"), t.result("trace_goods")
    out = []
    if E.get("findings"):
        found = E["findings"]
        serious = [f for f in found if f["category"] != "anomaly"] or found
        for f in serious[:3]:
            s = f"**{f['invoice']}** {f['counterparty']}: {f['title'].lower()}. {f['why']}"
            out.append(s if s.endswith(".") else s + ".")
        ims = E.get("ims_autopilot")
        if ims:
            out.append(f"IMS Autopilot: **{ims['decision']}** ({ims['reason']}).")
    elif E:
        out.append(f"**{E['invoice']}**: {E['explanation']}")
    if G and G.get("checked") and G["verdict"] == "verified":
        out.append(
            f"On the road it checks out: {G['vehicle']} crossed {G['tolls_crossed']} of "
            f"{G['tolls_expected']} tolls on {G['route']}."
        )
    return " ".join(out)


def _t_overview(t: Trace) -> str:
    R = t.result("reconcile_period")
    if not R:
        return ""
    i, road, net = R["invoices"], R["road_check"], R["liability"]
    rings = R["supplier_network"]["circular_trading_rings"]
    at_risk = R["supplier_network"]["suppliers_at_risk"]
    out = [
        f"{R['period_label']} for {R['company']}: {i['reconciled']} invoices reconciled, "
        f"{i['matched_clean']} matched clean ({i['clean_match']}), {i['with_discrepancies']} "
        f"with discrepancies, {i['duplicates']} duplicates and {i['unmatched']} unmatched."
    ]
    out.append(
        f"{road['failed']} of {road['consignments_checked']} consignments failed the road check"
        + (
            f", and {len(rings)} circular-trading ring sits upstream of **{_join(at_risk)}**."
            if rings and at_risk
            else "."
        )
    )
    out.append(
        f"Net payable is {net['net_payable_as_filed']} as filed and "
        f"**{net['net_payable_reconciled']}** reconciled; exposure caught "
        f"{net['exposure_caught']}."
    )
    out.append("Ask me about your liability, the road check, a supplier or IMS.")
    return " ".join(out)


TEMPLATES: dict[str, Callable[[Trace], str]] = {
    "liability": _t_liability,
    "road": _t_road,
    "supplier": _t_supplier,
    "ims": _t_ims,
    "duplicates": _t_list,
    "unmatched": _t_list,
    "discrepancy": _t_list,
    "ring": _t_list,
    "invoice": _t_invoice,
    "overview": _t_overview,
}


def _template(question: str, trace: Trace) -> Iterator[Event]:
    """Run the intent's tools (skipping calls already made) and write the answer."""
    intent, plan = plan_for(question)
    for name, args in plan:
        if not trace.has(name, args):
            yield from trace.run(name, args)
    text = TEMPLATES[intent](trace)
    if not text:
        errors = [r["error"] for _, _, r in trace.calls if "error" in r]
        text = errors[0] if errors else "I could not find that in this month's data."
    yield Event("_answer", {"text": text})


# ── the LLM path ─────────────────────────────────────────────────────────────


def system_prompt() -> str:
    ds = tools._ds()
    period = str(ds.meta["period"])
    return f"""You are the copilot inside Half CA, a GST reconciliation app, talking to the \
owner of {ds.meta["user_name"]} (GSTIN {ds.meta["user_gstin"]}) about \
{tools._period_label(period)} ({period}).

Use the tools to get facts, then answer. Rules:
1. Every number you write must be copied from a tool result or the question. Never add, \
subtract, convert or estimate a number. If a figure you want is not in a tool result, \
describe it in words.
2. Money in tool results is already formatted ("₹4.2 L" means ₹4.2 lakh). Copy it as given.
3. Tools take names and invoice numbers: supplier_risk(gstin="Kaveri Metals") and \
trace_goods(invoice_id="MB/0877") both work. At most {config.COPILOT_MAX_TOOL_CALLS} tool \
calls; one or two is usually enough.
4. Lead with the direct answer, then the facts that explain it: 2 to 5 short sentences of \
plain prose for a small-business owner. No headings, tables, bullet points or line breaks. \
Put invoice numbers and supplier names in **bold**.
5. Only recommend actions that a tool result supports (an `action` field, an IMS decision, \
the GSTR-2B date). Do not invent procedures.
6. If the tools cannot answer, say so briefly.

Background you may use: GST 2.0 slabs 0/5/18/40% apply from 22 Sep 2025 (12% and 28% \
abolished). IMS action is mandatory from 1 Apr 2026; supplier invoices not acted on are \
deemed accepted into ITC; GSTR-2B generates on the 14th. E-way bills are mandatory for \
inter-state goods consignments over ₹50,000. Toll and upstream supplier data are synthetic."""


def _llm(
    question: str,
    history: list[dict[str, str]],
    trace: Trace,
    client: llm.LLMClient,
    patience: float = LLM_PATIENCE_S,
) -> Iterator[Event]:
    system = system_prompt()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages += history
    messages.append({"role": "user", "content": question})
    schemas = tools.schemas()
    calls = 0
    text = ""
    for _ in range(config.COPILOT_MAX_TOOL_CALLS + 2):
        budget_left = calls < config.COPILOT_MAX_TOOL_CALLS
        msg = client.complete(
            messages,
            tools=schemas,
            tool_choice="auto" if budget_left else "none",
            max_tokens=900,
            max_wait=patience,
        )
        if not msg["tool_calls"]:
            text = msg["content"].strip()
            break
        messages.append(
            {"role": "assistant", "content": msg["content"], "tool_calls": msg["tool_calls"]}
        )
        for tc in msg["tool_calls"]:
            name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"] or "{}")
            except ValueError:
                args = None
            if not isinstance(args, dict):
                result: dict[str, Any] = {"error": "arguments were not a JSON object"}
            elif calls >= config.COPILOT_MAX_TOOL_CALLS:
                result = {"error": "tool budget used up; answer with what you have"}
            else:
                calls += 1
                yield from trace.run(name, args)
                result = trace.calls[-1][2]
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    if not text:
        raise llm.LLMError("the model gave no answer")

    sources = trace.sources() + question + json.dumps(history, ensure_ascii=False) + system
    bad = untraced(text, sources)
    if bad:  # one rewrite, then give up on the model's wording
        messages += [
            {"role": "assistant", "content": text},
            {
                "role": "user",
                "content": f"These numbers are not in any tool result: {', '.join(bad)}. "
                "Rewrite the answer using only numbers that appear in the tool results.",
            },
        ]
        text = client.complete(messages, max_tokens=700, max_wait=patience)["content"].strip()
        bad = untraced(text, sources)
        if bad or not text:
            raise UntracedNumbers(bad)
    yield Event("_answer", {"text": text, "checked": len(numbers(text))})


class UntracedNumbers(llm.LLMError):
    def __init__(self, bad: list[str]) -> None:
        super().__init__(f"untraced numbers: {', '.join(bad)}")
        self.bad = bad


# ── entry point ──────────────────────────────────────────────────────────────


def _clean_history(history: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    out = []
    for h in (history or [])[-HISTORY_TURNS:]:
        role, content = h.get("role"), str(h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content[:1500]})
    return out


def _words(text: str, pace: bool) -> Iterator[Event]:
    for w in re.findall(r"\S+\s*", text):
        yield Event("token", {"text": w})
        if pace:
            time.sleep(WORD_DELAY_S)


def answer(
    question: str,
    history: list[dict[str, Any]] | None = None,
    *,
    pace: bool = True,
    client: llm.LLMClient | None = None,
    patience: float = LLM_PATIENCE_S,
) -> Iterator[Event]:
    """Answer one question, streaming the working. Never raises: problems become a
    templated answer with a note."""
    question = (question or "").strip()[:2000]
    trace = Trace()
    try:
        tools._ds()
    except tools.ToolError as e:
        yield from _words(str(e), pace)
        yield Event("done", {"mode": "error", "model": None, "tool_calls": 0, "note": str(e)})
        return

    mode, note, text, checked = "template", None, "", 0
    if client is None and llm.configured():
        try:
            client = llm.LLMClient()
        except llm.LLMError:
            client = None
    if client is not None:
        if _busy.acquire(timeout=20):
            try:
                for ev in _llm(question, _clean_history(history), trace, client, patience):
                    if ev.type == "_answer":
                        text, checked, mode = ev.data["text"], ev.data["checked"], "llm"
                    else:
                        yield ev
            except UntracedNumbers as e:
                note = (
                    "The model's wording used a figure I could not trace to a tool "
                    f"({', '.join(e.bad[:3])}), so this answer comes from the template."
                )
            except llm.LLMError as e:
                note = f"The AI model is unavailable right now ({e}); templated answer."
            except Exception as e:  # never break the chat
                note = f"Something went wrong with the AI answer ({type(e).__name__}); templated."
            finally:
                _busy.release()
        else:
            note = "The AI model is busy; templated answer."
    else:
        note = "No AI model configured: templated answer from the same tools."

    if mode != "llm":
        for ev in _template(question, trace):
            if ev.type == "_answer":
                text = ev.data["text"]
            else:
                yield ev
        checked = len(numbers(text))

    yield from _words(text, pace)
    yield Event("evidence", {"items": trace.evidence()})
    yield Event(
        "done",
        {
            "mode": mode,
            "model": llm.model_name() if mode == "llm" else None,
            "tool_calls": len(trace.calls),
            "numbers_checked": checked,
            "note": note,
        },
    )


def info() -> dict[str, Any]:
    return {
        "llm": llm.model_name(),
        "max_tool_calls": config.COPILOT_MAX_TOOL_CALLS,
        "suggestions": SUGGESTIONS,
        "tools": [{"name": t.name, "description": t.description} for t in tools.TOOLS.values()],
    }
