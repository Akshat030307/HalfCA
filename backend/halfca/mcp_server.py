"""Half CA as an MCP server (stdio): the same seven tools the in-app copilot uses.

    make mcp                                  # run it
    claude mcp add halfca -- uv --directory /path/to/HalfCA/backend run python -m halfca.mcp_server

It reads the current reconciled dataset (data/halfca.duckdb, or HALFCA_DATA_DIR). Every
tool returns JSON with an `evidence` array; money comes pre-formatted in ₹ lakh / Indian
grouping. Nothing here calls a language model.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from halfca import __version__, tools

server = MCPServer(
    "halfca",
    title="Half CA",
    version=__version__,
    instructions=(
        "GST reconciliation for one Indian SME and one month (synthetic demo data). Start "
        "with reconcile_period for the overview; list_discrepancies to find problems; "
        "trace_goods and supplier_risk to dig into the road check and the supplier network; "
        "ims_recommendations and estimate_liability for what to file; explain for the "
        "evidence behind one finding. Quote amounts exactly as the tools format them."
    ),
)


def _run(name: str, **args: Any) -> dict[str, Any]:
    out = tools.call(name, args)
    if "error" in out:
        raise ToolError(out["error"])  # reaches the client as is_error with the message
    return out


@server.tool(description=tools.TOOLS["reconcile_period"].description)
def reconcile_period(gstin: str | None = None, month: str | None = None) -> dict[str, Any]:
    return _run("reconcile_period", gstin=gstin, month=month)


@server.tool(description=tools.TOOLS["list_discrepancies"].description)
def list_discrepancies(
    type: str | None = None,  # noqa: A002 (the spec's argument name)
    min_amount: float | None = None,
    limit: int = 8,
) -> dict[str, Any]:
    return _run("list_discrepancies", type=type, min_amount=min_amount, limit=limit)


@server.tool(description=tools.TOOLS["trace_goods"].description)
def trace_goods(invoice_id: str) -> dict[str, Any]:
    return _run("trace_goods", invoice_id=invoice_id)


@server.tool(description=tools.TOOLS["supplier_risk"].description)
def supplier_risk(gstin: str) -> dict[str, Any]:
    return _run("supplier_risk", gstin=gstin)


@server.tool(description=tools.TOOLS["ims_recommendations"].description)
def ims_recommendations(month: str | None = None) -> dict[str, Any]:
    return _run("ims_recommendations", month=month)


@server.tool(description=tools.TOOLS["estimate_liability"].description)
def estimate_liability(month: str | None = None, scenario: str = "both") -> dict[str, Any]:
    return _run("estimate_liability", month=month, scenario=scenario)


@server.tool(description=tools.TOOLS["explain"].description)
def explain(flag_id: str) -> dict[str, Any]:
    return _run("explain", flag_id=flag_id)


def main() -> None:
    server.run("stdio")


if __name__ == "__main__":
    main()
