"""M5: reading invoice PDFs. The model is a stub that reads the demo layout with regexes,
so the tests check our side: verification against the document text, linking to the
register, document discrepancies and adding invoices that only exist as PDFs."""

from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from halfca import config
from halfca.ai import llm
from halfca.api.main import app
from halfca.data import build as data_build
from halfca.data.demo_pack import FOLDER, build_pack
from halfca.engines.documents import compare
from halfca.ingest import documents as ingest_docs
from halfca.ingest.llm_extract import Extracted, read_document, verify

from .conftest import stub_adjudicator


class StubReader:
    """Stands in for the model: pulls fields out of the demo invoice layout. `lie` adds a
    value that is not on the document, to prove verification drops it."""

    model = "stub-reader"

    def __init__(self, lie: dict[str, Any] | None = None) -> None:
        self.lie = lie or {}
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], **_: Any) -> str:
        self.calls += 1
        t = messages[1]["content"]
        num = lambda s: float(s.replace(",", ""))  # noqa: E731
        gstins = re.findall(r"GSTIN (\w{15})", t)
        out: dict[str, Any] = {
            "supplier_gstin": gstins[0],
            "buyer_gstin": gstins[1],
            "supplier_name": t.splitlines()[0],
            "invoice_no": re.search(r"No\. (\S+)", t).group(1),
            "invoice_date": datetime.strptime(
                re.search(r"Date (\d\d \w{3} \d{4})", t).group(1), "%d %b %Y"
            )
            .date()
            .isoformat(),
            "place_of_supply": re.search(r"Place of supply .*\((\d\d)\)", t).group(1),
            "total": num(re.search(r"Invoice total \(₹\) ([\d,]+)", t).group(1)),
            "taxable_value": num(re.search(r"\n1 .* ([\d,]+)\n", t).group(1)),
            "hsn": re.search(r"\n1 .*? (\d{4}) ", t).group(1),
        }
        for head in ("IGST", "CGST", "SGST"):
            m = re.search(rf"{head} @ ([\d.]+)% ([\d,]+)", t)
            if m:
                out[f"{head.lower()}_rate"] = float(m.group(1))
                out[head.lower()] = num(m.group(2))
        if m := re.search(r"E-way bill: ([\d ]+)", t):
            out["ewb_no"] = m.group(1).replace(" ", "")
        return json.dumps({**out, **self.lie})


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[dict[str, Any]]:
    root = tmp_path_factory.mktemp("docs-data")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATA_DIR", root)
    mp.setattr(config, "DB_PATH", root / "halfca.duckdb")
    mp.setattr(data_build, "default_adjudicator", lambda: stub_adjudicator)
    data_build.run("demo", out=root)
    folder = build_pack(root / "pack")
    yield {"root": root, "folder": folder, "pdfs": sorted((folder / "invoices").glob("*.pdf"))}
    mp.undo()


def pdf(world: dict[str, Any], no: str) -> Path:
    return next(p for p in world["pdfs"] if p.stem.endswith(no.replace("/", "-")))


def test_reads_a_demo_pdf(world: dict[str, Any]) -> None:
    d = read_document(pdf(world, "MB/0877"), StubReader())
    assert d.status == "read" and not d.problems
    f = d.fields
    assert (f["invoice_no"], f["total"], f["rate"]) == ("MB/0877", 118000.0, 18.0)
    assert f["ewb_no"] == "381299021166" and f["invoice_date"] == "2026-09-17"


def test_values_not_on_the_document_are_dropped(world: dict[str, Any]) -> None:
    lie = {"total": 120000, "buyer_gstin": "07AAAAA0000A1Z5", "invoice_date": "2026-09-30"}
    d = read_document(pdf(world, "MB/0877"), StubReader(lie=lie))
    assert "total" not in d.fields and "buyer_gstin" not in d.fields
    assert "invoice_date" not in d.fields
    assert d.status == "needs_review"  # the total is required
    assert any("total 120000" in p for p in d.problems)


def test_verify_works_out_the_rate_itself() -> None:
    text = "No. X/1 GSTIN 07AAKFA4821M1ZA CGST @ 9% 900 SGST @ 9% 900 Taxable 10,000 Total 11,800"
    x = Extracted(cgst_rate=9, sgst_rate=9, cgst=900, sgst=900, taxable_value=10000, total=11800)
    fields, problems = verify(x, text)
    assert fields["rate"] == 18 and not problems
    bad = Extracted(taxable_value=10000, cgst=900, sgst=900, total=12000)
    _, problems = verify(bad, text + " 12,000")
    assert any("does not" in p or "total says" in p for p in problems)


def test_no_model_scans_and_images(world: dict[str, Any], tmp_path: Path) -> None:
    assert read_document(pdf(world, "LD/2291"), None).status == "unread"
    img = tmp_path / "bill.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    assert read_document(img, StubReader()).status == "needs_review"
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 nonsense")
    assert read_document(broken, StubReader()).status == "needs_review"


def test_compare_flags_a_register_that_disagrees(world: dict[str, Any]) -> None:
    d = read_document(pdf(world, "MB/0877"), StubReader())
    inv = pd.read_csv(
        next((world["root"] / "sources").glob("invoices_*.csv")),
        dtype={"hsn": str, "ewb_no": str, "place_of_supply": str, "supplier_state": str},
    )
    inv["invoice_date"] = pd.to_datetime(inv.invoice_date)
    docs = pd.DataFrame([{**d.as_row(), "added": False}])
    flags, stats = compare(docs, inv)
    assert flags == [] and stats["counts"]["agree"] == 1

    edited = inv.copy()
    edited.loc[edited.invoice_no == "MB/0877", "total"] = 112000.0
    flags, stats = compare(docs, edited)
    assert len(flags) == 1 and stats["counts"]["differ"] == 1
    f = flags[0]
    assert f.kind == "document" and f.category == "discrepancy" and f.ref == "MB/0877"
    assert f.recorded == "Register: Total ₹1,12,000" and f.expected == "PDF: Total ₹1,18,000"
    assert [c["source"] for c in f.evidence["chain"]] == ["document", "invoice"]


def test_a_pdf_missing_from_the_register_is_added(world: dict[str, Any]) -> None:
    d = read_document(pdf(world, "LD/2291"), StubReader())
    inv = pd.read_csv(next((world["root"] / "sources").glob("invoices_*.csv")), dtype=str)
    without = inv[inv.invoice_no != "LD/2291"]
    out, docs = ingest_docs.add_missing([d], without, config.USER_GSTIN, {})
    assert len(out) == len(inv) and bool(docs.added.iloc[0])
    row = out.iloc[-1]
    assert row.invoice_no == "LD/2291" and row.direction == "inward" and row.total == 486000.0


# ── the real upload path ─────────────────────────────────────────────────────


def wait(c: TestClient, job: dict[str, Any]) -> dict[str, Any]:
    for _ in range(600):
        job = c.get(f"/api/jobs/{job['job_id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def upload(c: TestClient, folder: Path) -> dict[str, Any]:
    files = [
        ("files", (str(p.relative_to(folder.parent)), p.read_bytes()))
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    ]
    return wait(c, c.post("/api/upload", files=files).json())


def test_upload_with_pdfs_end_to_end(world: dict[str, Any], tmp_path: Path) -> None:
    mp = pytest.MonkeyPatch()
    mp.setattr(llm, "configured", lambda: True)
    mp.setattr(llm, "LLMClient", lambda: StubReader())
    try:
        with TestClient(app) as c:
            job = upload(c, world["folder"])
            assert job["status"] == "done", job["error"]
            notes = [f["note"] for f in job["files"] if f["kind"] == "document"]
            assert len(notes) == 13 and all("agrees" in n for n in notes)
            assert "13 PDFs read by" in job["steps"][0]["detail"]
            assert job["kpis"]["discrepancies"] == 38  # the demo is untouched
            assert c.get("/api/dataset").json()["documents"]["agree"] == 13

            # Edit MB/0877's total in the register: the PDF now disagrees with the books.
            edited = tmp_path / FOLDER
            shutil.copytree(world["folder"], edited)
            csv = next(edited.glob("invoices_*.csv"))
            text = csv.read_text().replace(",118000.0,", ",112000.0,", 1)
            assert text != csv.read_text()
            csv.write_text(text)
            job = upload(c, edited)
            assert job["status"] == "done", job["error"]
            mb = next(f for f in job["files"] if f["name"].endswith("MB-0877.pdf"))
            assert "differs" in mb["note"] and "₹1,18,000" in mb["note"]
            flags = c.get("/api/discrepancies?type=document").json()["items"]
            assert [f["ref"] for f in flags] == ["MB/0877"]
    finally:
        mp.undo()
