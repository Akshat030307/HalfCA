"""M3: every endpoint, plus the real upload flow (folder → job → new dataset)."""

from __future__ import annotations

import io
import shutil
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from halfca import config
from halfca.api.main import app
from halfca.data import build as data_build

from .conftest import stub_adjudicator


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    """An isolated data dir with the demo month, and the stub standing in for the model."""
    root = tmp_path_factory.mktemp("api-data")
    mp = pytest.MonkeyPatch()
    mp.setattr(config, "DATA_DIR", root)
    mp.setattr(config, "DB_PATH", root / "halfca.duckdb")
    mp.setattr(data_build, "default_adjudicator", lambda: stub_adjudicator)
    data_build.run("demo", out=root)
    with TestClient(app) as c:
        yield c
    mp.undo()


def wait(client: TestClient, job: dict) -> dict:
    for _ in range(600):
        job = client.get(f"/api/jobs/{job['job_id']}").json()
        if job["status"] != "running":
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")


def test_summary(client: TestClient) -> None:
    s = client.get("/api/summary").json()
    k = s["kpis"]
    assert (k["reconciled"], k["matched"], k["discrepancies"], k["duplicates"], k["unmatched"]) == (
        552,
        489,
        38,
        7,
        18,
    )
    assert round(k["exposure"] / 1e5, 1) == 5.3
    assert [d["value"] for d in s["donut"]] == [489, 38, 7, 18]
    assert [(t["kind"], t["count"]) for t in s["discrepancy_types"]] == [
        ("amount", 11),
        ("tax_rate", 9),
        ("invoice_id", 8),
        ("date", 6),
        ("tax_head", 4),
        ("duplicate", 7),
    ]
    assert s["dataset"]["scenario"] == "demo"


def test_funnel_and_queue(client: TestClient) -> None:
    f = client.get("/api/funnel").json()
    assert [x["paired"] for x in f["stages"]] == [491, 38, 3, 2]
    totals = [u["total"] for u in f["unmatched"]]
    assert len(totals) == 18 and totals == sorted(totals, reverse=True)


def test_discrepancies(client: TestClient) -> None:
    d = client.get("/api/discrepancies").json()
    assert len(d["items"]) == 45  # 38 discrepancies + 7 duplicates
    one = client.get("/api/discrepancies", params={"type": "tax_head"}).json()["items"]
    assert len(one) == 4 and all(x["evidence"]["chain"] for x in one)
    gaps = client.get("/api/discrepancies", params={"category": "gap"}).json()
    assert {c["kind"] for c in gaps["counts"]} <= {"unpaid_aged", "not_in_ims"}


def test_invoice_threads(client: TestClient) -> None:
    pp = client.get("/api/invoices/PP/26/0912").json()
    assert pp["status"] == "matched" and pp["voucher"] and pp["payments"]
    assert pp["ims"]["decision"] == "Accept" and pp["physical"]["verdict"] == "verified"
    mb = client.get("/api/invoices/MB/0877").json()
    assert mb["physical"]["verdict"] == "paper_only" and mb["ims"]["decision"] == "Reject"
    assert client.get("/api/invoices/NOPE/1").status_code == 404


def test_goods(client: TestClient) -> None:
    g = client.get("/api/goods").json()
    assert len(g["routes"]) == 5 and g["view_box"] == [860, 600]
    names = {t["invoice_id"]: t["invoice_no"] for t in g["invoices"]}
    beats = [(b["kind"], [names[i] for i in b["invoice_ids"]]) for b in g["beats"]]
    assert beats == [
        ("verified", ["LD/2291"]),
        ("paper_only", ["MB/0877"]),
        ("impossible_journey", ["KN/1502"]),
        ("recycled_ewb", ["JP/1187", "JP/1188", "JP/1192"]),
    ]
    kn = client.get("/api/goods/KN/1502").json()
    assert round(kn["trip"]["speed_kmh"]) == 158 and len(kn["trip"]["crossings"]) == 3


def test_credit(client: TestClient) -> None:
    g = client.get("/api/credit/graph").json()
    slots = {n["name"]: n["slot"] for n in g["nodes"]}
    assert slots["Kaveri Metals"] == "at_risk" and slots["Arora Hardware Distributors"] == "you"
    assert sum(1 for s in slots.values() if s == "ring") == 5
    assert {"Patel Pipes", "Singh Fittings", "Mehta Tubes", "Bharat Tubes"} <= set(slots)
    s = client.get(f"/api/credit/supplier/{g['focus']}").json()
    assert (round(s["risk"], 2), s["hops_to_you"], len(s["invoices"])) == (0.82, 2, 4)
    assert round(s["itc_at_risk"] / 1e5, 1) == 4.2 and round(s["benford"]["mad"], 3) == 0.051
    full = client.get("/api/credit/graph", params={"scope": "full"}).json()
    assert len(full["nodes"]) > 300


def test_ims_approve_and_liability(client: TestClient) -> None:
    ims = client.get("/api/ims").json()
    assert ims["counts"] == {
        "records": 212,
        "accept": 197,
        "reject": 11,
        "pending": 4,
        "approved": 0,
    }
    assert ims["gstr2b_date"] == "2026-10-14"
    assert ims["records"][0]["decision"] == "Reject"
    out = client.post("/api/ims/approve").json()
    assert out["message"] == "197 accepted on IMS · 11 rejected · 4 kept pending"
    assert client.get("/api/ims").json()["counts"]["approved"] == 197
    li = client.get("/api/liability").json()
    assert [round(w["value"] / 1e5, 1) for w in li["waterfall"]] == [18.6, -1.1, -4.2, 13.3]
    assert client.get(f"/api/benford/{li['benford_focus']}").json()["n"] == 64


def _files(folder: Path) -> list[tuple[str, tuple[str, bytes]]]:
    return [
        ("files", (f"Arora Hardware – Sep 2026/{p.name}", p.read_bytes()))
        for p in sorted(folder.iterdir())
        if p.is_file()
    ]


def test_upload_folder_is_real(client: TestClient, tmp_path: Path) -> None:
    src = config.DATA_DIR / "sources"
    folder = tmp_path / "pack"
    shutil.copytree(src, folder)
    (folder / "README.txt").write_text("hello")
    (folder / "bill.pdf").write_bytes(b"%PDF-1.4 fake")
    job = wait(client, client.post("/api/upload", files=_files(folder)).json())
    assert job["status"] == "done", job["error"]
    assert [s["state"] for s in job["steps"]] == ["done"] * 5
    assert job["steps"][0]["label"].startswith("Reading 552 invoices")
    kinds = {f["kind"] for f in job["files"]}
    assert {"invoices", "bank", "ledger", "ims", "eway", "document", None} == kinds
    assert job["kpis"]["matched"] == 489 and job["kpis"]["unmatched"] == 18
    assert client.get("/api/dataset").json()["scenario"] == "upload"
    # A fresh dataset clears earlier IMS approvals.
    assert client.get("/api/ims").json()["counts"]["approved"] == 0


def test_editing_a_value_changes_the_result(client: TestClient, tmp_path: Path) -> None:
    src = config.DATA_DIR / "sources" / "invoices_sep26.csv"
    df = pd.read_csv(src, dtype=str, keep_default_na=False)
    row = df[df.invoice_no == "PP/26/0912"].index[0]
    df.loc[row, "total"] = str(float(df.loc[row, "total"]) + 5_000)
    edited = tmp_path / "invoices_sep26.csv"
    df.to_csv(edited, index=False)
    # Only the edited register: the other four sources come from the current dataset.
    job = wait(
        client,
        client.post("/api/upload", files=[("files", (edited.name, edited.read_bytes()))]).json(),
    )
    assert job["status"] == "done", job["error"]
    kept = [f for f in job["files"] if f["note"] and "kept" in f["note"]]
    assert len(kept) == 4
    assert job["kpis"]["discrepancies"] == 39
    d = client.get("/api/invoices/PP/26/0912").json()
    assert "amount" in {f["kind"] for f in d["flags"]}


def test_bad_upload_reports_a_reason(client: TestClient) -> None:
    job = wait(
        client,
        client.post(
            "/api/upload", files=[("files", ("invoices_x.csv", b"invoice_no,foo\nA,1\n"))]
        ).json(),
    )
    assert job["status"] == "error" and job["error"]


def test_reset_and_demo_button(client: TestClient) -> None:
    job = wait(client, client.post("/api/reset").json())
    assert job["status"] == "done", job["error"]
    assert client.get("/api/summary").json()["kpis"]["discrepancies"] == 38
    job = wait(client, client.post("/api/upload/demo").json())
    assert job["status"] == "done" and job["kpis"]["matched"] == 489
    assert client.get("/api/dataset").json()["scenario"] == "demo"
    job = wait(client, client.post("/api/reconcile", params={"period": "2026-09"}).json())
    assert job["status"] == "done"
    assert client.post("/api/reconcile", params={"period": "2025-01"}).status_code == 404


def test_demo_pack_download(client: TestClient) -> None:
    res = client.get("/api/demo-pack.zip")
    assert res.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert sum(n.endswith(".pdf") for n in names) >= 10
    assert any(n.endswith("invoices_sep26.csv") for n in names)
    assert any(n.endswith("README.txt") for n in names)
