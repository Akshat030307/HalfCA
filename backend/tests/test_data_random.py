"""M1: random mode produces labelled, reproducible evaluation data."""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path

import networkx as nx
import pytest

from halfca import config
from halfca.data import build as data_build
from halfca.ingest.csv_loader import read_folder
from halfca.ingest.gstin import is_valid


@pytest.fixture(scope="module")
def rnd(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict]:
    out = tmp_path_factory.mktemp("random")
    data_build.run("random", seed=11, out=out)
    return out, read_folder(out)


def test_labels_cover_the_catalogue(rnd: tuple[Path, dict]) -> None:
    _, frames = rnd
    codes = Counter(frames["truth_labels"].code)
    for code in ("D01", "D02", "D03", "D04", "D05", "D09", "D15", "D16"):
        assert codes[code] > 0, code
    assert 500 <= len(frames["invoices"]) <= 620


def test_two_rings_and_valid_ids(rnd: tuple[Path, dict]) -> None:
    _, frames = rnd
    up = frames["upstream_invoices"]
    g = nx.DiGraph(list(zip(up.seller_gstin, up.buyer_gstin, strict=True)))
    cycles = list(nx.simple_cycles(g, length_bound=config.CYCLE_MAX_LEN))
    assert sorted(len(c) for c in cycles) == [4, 5]
    assert all(is_valid(x) for x in frames["counterparties"].gstin)


def test_threshold_hugger(rnd: tuple[Path, dict]) -> None:
    _, frames = rnd
    t = frames["truth_labels"]
    hugger = t[t.code == "D16"].party_gstin.iloc[0]
    inv = frames["invoices"]
    mine = inv[inv.supplier_gstin == hugger]
    share = mine.total.between(config.HUG_LOW, config.HUG_HIGH).mean()
    assert share >= config.HUG_SHARE


def test_reproducible(tmp_path: Path, rnd: tuple[Path, dict]) -> None:
    out, _ = rnd
    data_build.run("random", seed=11, out=tmp_path)

    def digest(folder: Path) -> str:
        return hashlib.sha256(
            b"".join(f.read_bytes() for f in sorted((folder / "sources").iterdir()))
        ).hexdigest()

    assert digest(tmp_path) == digest(out)
