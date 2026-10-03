"""M6: the audit report PDF and the precision/recall evaluation."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

from halfca import config
from halfca import eval as halfca_eval
from halfca.api.main import app
from halfca.data import build as data_build
from halfca.report import pdf as report

from .conftest import stub_adjudicator


@pytest.fixture(scope="module")
def demo_root(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    root = tmp_path_factory.mktemp("report-data")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATA_DIR", root)
    mp.setattr(config, "DB_PATH", root / "halfca.duckdb")
    mp.setattr(data_build, "default_adjudicator", lambda: stub_adjudicator)
    data_build.run("demo", out=root)
    yield root
    mp.undo()


def text_of(pdf_bytes: bytes) -> tuple[int, str]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return len(reader.pages), "\n".join(p.extract_text() or "" for p in reader.pages)


def test_report_context_holds_the_demo_story(demo_root: Path) -> None:
    ctx = report.context()
    k = ctx["kpis"]
    assert (k["reconciled"], k["matched"], k["discrepancies"], k["duplicates"], k["unmatched"]) == (
        552,
        489,
        38,
        7,
        18,
    )
    assert sorted(t["invoice_no"] for t in ctx["road"]) == [
        "JP/1187",
        "JP/1188",
        "JP/1192",
        "KN/1502",
        "MB/0877",
    ]
    assert [r["name"] for r in ctx["risky"]] == ["Kaveri Metals"]
    assert len(ctx["actions"]) == 15  # 11 rejects + 4 pending
    assert len(ctx["register"]) == 45  # 38 discrepancies + 7 duplicates
    # every finding that drives an action is in the evidence appendix
    assert ctx["appendix_count"] == 45 + 5 + 1
    assert all(f["summary"] for g in ctx["appendix"] for f in g["items"])


def test_report_pdf(demo_root: Path) -> None:
    path = report.report_path()
    data = path.read_bytes()
    assert data.startswith(b"%PDF")
    pages, text = text_of(data)
    assert pages >= 8
    for must in (
        "Arora Hardware Distributors",
        "07AAKFA4821M1ZA",
        "₹5.3 L",
        "₹12.1 L",
        "MB/0877",
        "Kaveri Metals",
        "Evidence for every finding",
        "Synthetic data",
    ):
        assert must.lower() in text.lower(), must
    assert report.report_path() == path  # cached until the data changes


def test_report_endpoint(demo_root: Path) -> None:
    with TestClient(app) as c:
        res = c.get("/api/report.pdf")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert "Half-CA-audit-report-2026-09.pdf" in res.headers["content-disposition"]
        assert res.content.startswith(b"%PDF")


def test_field_text() -> None:
    assert report.field_text("total", 118000.0) == "₹1,18,000"
    assert report.field_text("ewb_no", "381299021166") == "3812 9902 1166"
    assert report.field_text("date", "2026-09-17T00:00:00") == "17 Sep 2026"
    assert report.field_text("crossed_at", "2026-09-19T23:00:00") == "19 Sep 2026, 23:00"
    assert report.field_text("rate", 18) == "18%"


def test_eval_scores_one_month(tmp_path: Path) -> None:
    result: dict[str, Any] = halfca_eval.run([3], out_dir=tmp_path)
    s = result["scores"]
    for code in ("D01", "D03", "D04", "D05", "D15"):
        assert s[code].truth > 0 and s[code].recall == 1.0, code
    road = [s[c] for c in ("D11", "D12", "D13", "D14")]
    assert sum(x.truth for x in road) > 0  # road problems are planted every month
    assert all(x.precision in (None, 1.0) for x in road)
    assert result["overall"].recall >= 0.95
    assert "| D13 | Impossible journey |" in halfca_eval.table(result)
