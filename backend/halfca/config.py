"""Env, paths and thresholds. The single source of constants (see CLAUDE.md)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: KEY=VALUE lines, no overriding of real env vars."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


_load_dotenv(BACKEND_DIR / ".env")

# ── Paths ────────────────────────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get("HALFCA_DATA_DIR", REPO_DIR / "data"))
DB_PATH = DATA_DIR / "halfca.duckdb"
ROUTES_PATH = BACKEND_DIR / "halfca" / "data" / "routes.json"

# ── LLM (optional; no provider means templated fallbacks) ────────────────────
LLM_PROVIDER = os.environ.get("HALFCA_LLM_PROVIDER", "").strip().lower()
LLM_MODEL = os.environ.get("HALFCA_LLM_MODEL", "").strip()
LLM_API_KEY = os.environ.get("HALFCA_LLM_API_KEY", "").strip()
LLM_BASE_URL = os.environ.get("HALFCA_LLM_BASE_URL", "").strip()

# ── The user and the demo ────────────────────────────────────────────────────
USER_GSTIN = "07AAKFA4821M1ZA"
USER_NAME = "Arora Hardware Distributors"
USER_CITY = "New Delhi"
DEMO_SEED = 2609
DEMO_PERIOD = "2026-09"
GSTR2B_DAY = 14  # GSTR-2B generates on the 14th of the following month

# ── GST rules ────────────────────────────────────────────────────────────────
GST2_EFFECTIVE = date(2025, 9, 22)  # GST 2.0 slabs 0/5/18/40; 12% and 28% abolished
GST2_SLABS = (0.0, 5.0, 18.0, 40.0)
TRANSITION_WINDOW_DAYS = 30
EWB_THRESHOLD = 50_000.0  # e-way bill needed for consignments at or above this value

# ── Matching cascade ─────────────────────────────────────────────────────────
STAGE2_AMOUNT_TOL = 1.0  # ₹
STAGE3_AMOUNT_PCT = 0.02
STAGE3_DATE_DAYS = 7
STAGE3_NAME_MIN = 85.0  # RapidFuzz token_sort_ratio
STAGE4_TOP_K = 3

# ── Field diffs, duplicates, gaps ────────────────────────────────────────────
DIFF_AMOUNT_TOL = 1.0  # ₹
DIFF_DATE_DAYS = 3
NEARDUP_EDIT_MAX = 2
NEARDUP_DATE_DAYS = 5
PAYMENT_TERMS_DAYS = 30  # unpaid beyond this is an aged gap
TAX_ARITH_TOL = 1.0  # ₹

# ── Physical trail ───────────────────────────────────────────────────────────
MAX_AVG_SPEED_KMH = 80.0

# ── ITC taint graph ──────────────────────────────────────────────────────────
CYCLE_MAX_LEN = 6
CYCLE_UPSTREAM_HOPS = 3
RING_RISK = 0.91
RISK_NEW_REGISTRATION = 0.3  # registered < NEW_REG_DAYS ago
RISK_ZERO_EWB = 0.3  # goods trade with zero e-way bills
RISK_TURNOVER_SPIKE = 0.2  # turnover > TURNOVER_SPIKE x trailing average
RISK_SHARED_IDENTITY = 0.2  # shared PAN / bank / phone / address
RISK_FILING_GAPS = 0.2
NEW_REG_DAYS = 90
TURNOVER_SPIKE = 3.0
TAINT_DECAY = 0.9
TAINT_AT_RISK = 0.7

# ── Anomaly ──────────────────────────────────────────────────────────────────
BENFORD_MIN_N = 50
BENFORD_MAD_THRESHOLD = 0.015
HUG_LOW = 45_000.0
HUG_HIGH = 49_999.0
HUG_SHARE = 0.30
ISOFOREST_CONTAMINATION = 0.02

# ── Copilot ──────────────────────────────────────────────────────────────────
COPILOT_MAX_TOOL_CALLS = 4
