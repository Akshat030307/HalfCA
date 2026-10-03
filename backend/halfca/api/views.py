"""Turn stored rows into JSON-ready dicts for the routers."""

from __future__ import annotations

import json
import math
from typing import Any

import pandas as pd

from halfca import config
from halfca.ai import llm

from .state import Dataset


def plain(v: Any) -> Any:
    """JSON-safe scalar: timestamps → ISO dates, NaN/NA → None, numpy → python."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, pd.Timestamp):
        return v.date().isoformat() if v == v.normalize() else v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item") and not isinstance(v, str):
        try:
            return plain(v.item())
        except (ValueError, AttributeError):
            return v
    return v


def record(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    items = row.items() if isinstance(row, dict) else row.to_dict().items()
    return {k: plain(v) for k, v in items}


def flag_out(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    r = record(row)
    ev = r.get("evidence")
    r["evidence"] = json.loads(ev) if isinstance(ev, str) else ev
    r["impact"] = float(r.get("impact") or 0.0)
    return r


def flags_out(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [flag_out(r) for _, r in df.iterrows()]


def llm_info(ds: Dataset) -> dict[str, Any]:
    return {
        "provider": config.LLM_PROVIDER if llm.configured() else None,
        "model": llm.model_name(),
        "stage4_skipped": bool(ds.summary.get("stage4_skipped")),
    }


def json_list(value: Any) -> list[Any]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        out = json.loads(value)
        return out if isinstance(out, list) else []
    except (TypeError, ValueError):
        return []
