from fastapi.testclient import TestClient

from halfca.api.main import app


def test_health() -> None:
    res = TestClient(app).get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_dataset_describes_the_demo() -> None:
    from halfca import config

    if not config.DB_PATH.is_file():
        import pytest

        pytest.skip("run `make data` first")
    res = TestClient(app).get("/api/dataset")
    assert res.status_code == 200
    body = res.json()
    assert body["scenario"] == "demo"
    sources = {s["kind"]: s for s in body["sources"]}
    assert sources["invoices"]["records"] == 552
    assert sources["ims"]["filename"] == "ims_feed_2026-09.json"
