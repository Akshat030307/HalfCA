"""Shared fixtures. Tests never call a real model: the provider is blanked before any
halfca module reads the config."""

from __future__ import annotations

import os

os.environ["HALFCA_LLM_PROVIDER"] = ""
os.environ["HALFCA_LLM_API_KEY"] = ""

from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from halfca import config  # noqa: E402
from halfca.data import build as data_build  # noqa: E402
from halfca.ingest.csv_loader import read_folder  # noqa: E402
from halfca.pipeline import Reconciliation, reconcile  # noqa: E402


def stub_adjudicator(
    inv: dict[str, Any], cands: list[dict[str, Any]]
) -> tuple[str | None, float, str]:
    """Deterministic stand-in for the model: exact amount, within 3 days, only one such."""
    ok = [c for c in cands if abs(c["amount_diff"]) <= 1 and c["days_apart"] <= 3]
    if len(ok) == 1:
        return ok[0]["voucher_no"], 0.9, "Same amount and date (stub)"
    return None, 0.0, "No clear candidate (stub)"


DEMO_META = {
    "as_of": "2026-10-10T18:00:00+05:30",
    "user_gstin": config.USER_GSTIN,
    "period": "2026-09",
}


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo-m2")
    data_build.run("demo", out=out)
    return out


@pytest.fixture(scope="session")
def demo_frames(demo_dir: Path) -> dict[str, pd.DataFrame]:
    return {k: v for k, v in read_folder(demo_dir).items() if k != "truth_labels"}


@pytest.fixture(scope="session")
def demo(demo_frames: dict[str, pd.DataFrame]) -> Reconciliation:
    return reconcile(demo_frames, DEMO_META, adjudicator=stub_adjudicator)


@pytest.fixture(scope="session")
def demo_no_llm(demo_frames: dict[str, pd.DataFrame]) -> Reconciliation:
    return reconcile(demo_frames, DEMO_META, adjudicator=None)


def ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(datetime.fromisoformat(s))
