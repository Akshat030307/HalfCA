"""M5: the seven tools, the copilot (templates, a scripted model, the number guard), its SSE
route and the MCP server over stdio."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from halfca import config, tools
from halfca.ai import copilot, llm
from halfca.api.main import app
from halfca.data import build as data_build

from .conftest import stub_adjudicator

SPEC_TOOLS = [
    "reconcile_period",
    "list_discrepancies",
    "trace_goods",
    "supplier_risk",
    "ims_recommendations",
    "estimate_liability",
    "explain",
]


@pytest.fixture(scope="module")
def data_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    root = tmp_path_factory.mktemp("copilot-data")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATA_DIR", root)
    mp.setattr(config, "DB_PATH", root / "halfca.duckdb")
    mp.setattr(data_build, "default_adjudicator", lambda: stub_adjudicator)
    mp.setattr(copilot, "WORD_DELAY_S", 0.0)
    data_build.run("demo", out=root)
    yield root
    mp.undo()


def run(question: str, **kw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"tools": [], "done": [], "text": "", "evidence": [], "order": []}
    for ev in copilot.answer(question, pace=False, **kw):
        out["order"].append(ev.type)
        if ev.type == "tool":
            out["tools"].append(ev.data["call"])
        elif ev.type == "token":
            out["text"] += ev.data["text"]
        elif ev.type == "evidence":
            out["evidence"] = ev.data["items"]
        elif ev.type == "done":
            out["done"] = ev.data
    return out


# ── tools ────────────────────────────────────────────────────────────────────


def test_seven_tools_with_schemas(data_root: Any) -> None:
    assert list(tools.TOOLS) == SPEC_TOOLS
    for s in tools.schemas():
        assert s["type"] == "function" and s["function"]["parameters"]["type"] == "object"


def test_reconcile_period(data_root: Any) -> None:
    r = tools.call("reconcile_period", {"month": "Sep 2026"})
    assert r["invoices"]["reconciled"] == 552 and r["invoices"]["matched_clean"] == 489
    assert r["invoices"]["clean_match"] == "88.6%"
    assert r["road_check"]["failed"] == 5
    assert r["liability"]["exposure_caught"] == "₹5.3 L"
    assert "error" in tools.call("reconcile_period", {"month": "2026-08"})
    assert "error" in tools.call("reconcile_period", {"gstin": "06AAHCK3367Q1ZW"})


def test_list_discrepancies(data_root: Any) -> None:
    road = tools.call("list_discrepancies", {"type": "road"})
    assert road["count"] == 5 and road["total_at_stake"] == "₹66,600"
    assert {e["href"] for e in road["evidence"]} == {"/goods/"}
    default = tools.call("list_discrepancies", {})
    assert default["count"] == 45  # 38 discrepancies + 7 duplicates
    big = tools.call("list_discrepancies", {"type": "duplicate", "min_amount": 100000})
    assert all(i["invoice"] != "CAE/2371" for i in big["items"])
    assert "error" in tools.call("list_discrepancies", {"type": "nonsense"})


def test_trace_goods(data_root: Any) -> None:
    kn = tools.call("trace_goods", {"invoice_id": "KN/1502"})
    assert kn["verdict"] == "impossible_journey"
    assert (kn["trip_time"], kn["average_speed"], kn["distance"]) == (
        "3h 02m",
        "158 km/h",
        "480 km",
    )
    mb = tools.call("trace_goods", {"invoice_id": "MB/0877"})
    assert mb["tolls_crossed"] == 0 and mb["window_checked"] == "72 h"
    jp = tools.call("trace_goods", {"invoice_id": "JP/1188"})
    assert set(jp["shares_trip_with"]) >= {"JP/1187", "JP/1192"} - {"JP/1188"}
    sale = tools.call("trace_goods", {"invoice_id": "AR/S/2219"})
    assert sale["checked"] is False
    assert "error" in tools.call("trace_goods", {"invoice_id": "NOPE/1"})


def test_supplier_risk_by_name_or_gstin(data_root: Any) -> None:
    for q in ("Kaveri Metals", "kaveri", "06AAHCK3367Q1ZW"):
        k = tools.call("supplier_risk", {"gstin": q})
        assert k["supplier"] == "Kaveri Metals"
    assert k["taint_score"] == "0.82" and k["at_risk"]
    assert len(k["ring_upstream"]) == 5 and k["credit_chain_to_you"][0] == "Nexo Metals"
    assert k["itc_at_risk"] == "₹4.2 L" and k["invoice_count"] == 4
    assert k["benford"]["first_digit_mad"] == "0.051" and not k["benford"]["conforms"]


def test_ims_and_liability(data_root: Any) -> None:
    ims = tools.call("ims_recommendations", {"month": "2026-09"})
    assert (ims["accept"]["count"], ims["reject"]["count"], ims["pending"]["count"]) == (197, 11, 4)
    assert ims["gstr2b_generates"] == "14 Oct 2026"
    lb = tools.call("estimate_liability", {"month": "2026-09"})
    assert lb["as_filed"]["net_payable"] == "₹6.8 L"
    assert lb["reconciled"]["net_payable"] == "₹12.1 L"
    assert lb["change_in_net_payable"] == "+₹5.3 L"
    assert lb["reconciled"]["itc_held_pending"]["suppliers"] == ["Kaveri Metals"]
    only = tools.call("estimate_liability", {"scenario": "as_filed"})
    assert "reconciled" not in only


def test_explain(data_root: Any) -> None:
    by_invoice = tools.call("explain", {"flag_id": "MB/0877"})
    first = by_invoice["findings"][0]
    assert first["type"] == "Paper-only supply" and first["chain"]
    assert by_invoice["ims_autopilot"]["decision"] == "Reject"
    by_id = tools.call("explain", {"flag_id": first["flag_id"]})
    assert by_id["findings"][0]["flag_id"] == first["flag_id"]
    assert "error" in tools.call("explain", {"flag_id": "nothing:here"})


def test_every_tool_returns_evidence(data_root: Any) -> None:
    calls = {
        "reconcile_period": {},
        "list_discrepancies": {},
        "trace_goods": {"invoice_id": "LD/2291"},
        "supplier_risk": {"gstin": "Patel Pipes"},
        "ims_recommendations": {},
        "estimate_liability": {},
        "explain": {"flag_id": "DF/0450"},
    }
    for name, args in calls.items():
        out = tools.call(name, args)
        assert "error" not in out, (name, out)
        assert out["headline"] and out["evidence"], name
        assert all(e["href"].startswith("/") and e["label"] for e in out["evidence"])


# ── number guard ─────────────────────────────────────────────────────────────


def test_number_guard() -> None:
    src = json.dumps(
        {"a": "₹4.2 L", "b": "₹1,18,000", "c": 118000.0, "d": "0.82"}, ensure_ascii=False
    )
    assert copilot.untraced("₹4.2 lakh, ₹1,18,000, taint 0.82", src) == []
    assert copilot.untraced("about ₹4,20,000", src) == ["420000"]
    assert copilot.untraced("₹4.20 L across 4 invoices on 14 Oct 2026", src) == []
    assert copilot.untraced("speed 158 km/h", src) == ["158"]


# ── copilot: templates (no key) ──────────────────────────────────────────────


def test_template_answers_the_liability_question(data_root: Any) -> None:
    assert not llm.configured()
    r = run("Why did my liability go up?")
    assert r["tools"][0].startswith("estimate_liability(")
    assert "₹6.8 L" in r["text"] and "₹12.1 L" in r["text"] and "Kaveri Metals" in r["text"]
    hrefs = {e["href"] for e in r["evidence"]}
    assert {"/liability/", "/ims/", "/goods/", "/credit/"} <= hrefs
    assert r["done"]["mode"] == "template" and r["done"]["tool_calls"] == 2
    assert r["order"][0] == "tool" and r["order"][-2:] == ["evidence", "done"]


@pytest.mark.parametrize(
    ("question", "first_tool", "must_say"),
    [
        ("Which invoices failed the road check?", "list_discrepancies", "KN/1502"),
        ("Is Kaveri Metals safe to buy from?", "supplier_risk", "0.82"),
        ("Why was MB/0877 rejected?", "explain", "Reject"),
        ("How many IMS rejects?", "ims_recommendations", "197"),
        ("Any duplicates?", "list_discrepancies", "INV/418"),
        ("How did the month go?", "reconcile_period", "552"),
        ("What about August?", "reconcile_period", "Only Sep 2026"),
    ],
)
def test_template_intents(data_root: Any, question: str, first_tool: str, must_say: str) -> None:
    r = run(question)
    assert r["tools"][0].startswith(first_tool + "(")
    assert must_say in r["text"]


def test_template_numbers_all_trace_to_tools(data_root: Any) -> None:
    for q in copilot.SUGGESTIONS:
        trace = copilot.Trace()
        text = ""
        for ev in copilot._template(q, trace):
            if ev.type == "_answer":
                text = ev.data["text"]
        assert copilot.untraced(text, trace.sources()) == [], q


# ── copilot: a scripted model ────────────────────────────────────────────────


class ScriptedModel:
    """Stands in for LLMClient.complete: returns the scripted messages in order."""

    def __init__(self, *replies: dict[str, Any] | Exception) -> None:
        self.replies = list(replies)
        self.seen: list[list[dict[str, Any]]] = []

    def complete(self, messages: list[dict[str, Any]], **_: Any) -> dict[str, Any]:
        self.seen.append(list(messages))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def call(name: str, args: dict[str, Any], id_: str = "c1") -> dict[str, Any]:
    fn = {"name": name, "arguments": json.dumps(args)}
    return {"content": "", "tool_calls": [{"id": id_, "type": "function", "function": fn}]}


def say(text: str) -> dict[str, Any]:
    return {"content": text, "tool_calls": []}


def test_model_answer_with_tool_trace(data_root: Any) -> None:
    model = ScriptedModel(
        call("estimate_liability", {"month": "2026-09"}),
        say("Net payable went from **₹6.8 L** to **₹12.1 L** because ₹5.3 L of ITC failed."),
    )
    r = run("Why did my liability go up?", client=model)
    assert r["done"]["mode"] == "llm" and r["done"]["numbers_checked"] >= 3
    assert r["tools"] == ["estimate_liability(month='2026-09')"]
    assert r["text"].startswith("Net payable went from")
    tool_msg = model.seen[1][-1]
    assert tool_msg["role"] == "tool" and "₹12.1 L" in tool_msg["content"]


def test_model_number_not_in_tools_gets_one_rewrite(data_root: Any) -> None:
    model = ScriptedModel(
        call("estimate_liability", {}),
        say("You owe about ₹12,09,990 now."),  # converted the lakh figure itself
        say("You owe ₹12.1 L now, up from ₹6.8 L."),
    )
    r = run("Why did my liability go up?", client=model)
    assert r["done"]["mode"] == "llm" and "₹12.1 L" in r["text"]
    assert "1209990" in model.seen[2][-1]["content"]


def test_model_that_keeps_inventing_falls_back(data_root: Any) -> None:
    model = ScriptedModel(
        call("estimate_liability", {}),
        say("You owe ₹12,09,990."),
        say("Roughly ₹12,10,000."),
    )
    r = run("Why did my liability go up?", client=model)
    assert r["done"]["mode"] == "template" and "could not trace" in r["done"]["note"]
    assert "₹12.1 L" in r["text"]
    assert r["tools"].count("estimate_liability(month='2026-09')") == 1  # template reused it


def test_model_failure_falls_back(data_root: Any) -> None:
    r = run("Is Kaveri Metals safe to buy from?", client=ScriptedModel(llm.LLMError("429")))
    assert r["done"]["mode"] == "template" and "unavailable" in r["done"]["note"]
    assert "0.82" in r["text"]


def test_tool_budget_is_capped(data_root: Any) -> None:
    many = [call("reconcile_period", {}, f"c{i}") for i in range(5)]  # one over budget
    model = ScriptedModel(*many, say("552 invoices this month."))
    r = run("Tell me everything", client=model)
    assert len(r["tools"]) == config.COPILOT_MAX_TOOL_CALLS
    assert r["done"]["mode"] == "llm"


# ── API + MCP ────────────────────────────────────────────────────────────────


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_copilot_sse_route(data_root: Any) -> None:
    with TestClient(app) as c:
        info = c.get("/api/copilot").json()
        assert [t["name"] for t in info["tools"]] == SPEC_TOOLS and info["llm"] is None
        res = c.post("/api/copilot", json={"message": "Why did my liability go up?"})
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(res.text)
        kinds = [k for k, _ in events]
        assert kinds[:4] == ["tool", "tool_done", "tool", "tool_done"]
        assert kinds[-2:] == ["evidence", "done"] and "token" in kinds
        assert c.post("/api/copilot", json={"message": ""}).status_code == 422


def test_mcp_server_over_stdio(data_root: Any) -> None:
    from mcp.client.client import Client
    from mcp.client.stdio import StdioServerParameters

    env = {
        "HALFCA_DATA_DIR": str(data_root),
        "HALFCA_LLM_PROVIDER": "",
        "PYTHONPATH": os.getcwd(),
    }
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "halfca.mcp_server"], env=env
    )

    async def session() -> tuple[list[str], dict[str, Any], bool]:
        async with Client(params) as c:
            listed = await c.list_tools()
            risk = await c.call_tool("supplier_risk", {"gstin": "Kaveri Metals"})
            bad = await c.call_tool("trace_goods", {"invoice_id": "NOPE/1"})
            return [t.name for t in listed.tools], json.loads(risk.content[0].text), bad.is_error

    names, risk, bad_is_error = asyncio.run(session())
    assert names == SPEC_TOOLS
    assert risk["taint_score"] == "0.82" and risk["evidence"]
    assert bad_is_error
