"""DuckDB access. Raw source tables are `raw_*`; engine results (M2+) are `res_*`."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

from halfca import config


def save(
    frames: dict[str, pd.DataFrame], meta: dict[str, object], path: Path | None = None
) -> Path:
    """Write a fresh database next to the old one, then swap it in atomically, so a
    running API never reads a half-written file."""
    path = path or config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".duckdb.tmp")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    try:
        for name, df in frames.items():
            con.register("_frame", df)
            con.execute(f'CREATE TABLE "raw_{name}" AS SELECT * FROM _frame')
            con.unregister("_frame")
        con.execute("CREATE TABLE meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
        con.executemany(
            "INSERT INTO meta VALUES (?, ?)",
            [(k, json.dumps(v, default=str)) for k, v in meta.items()],
        )
    finally:
        con.close()
    os.replace(tmp, path)
    return path


@contextmanager
def connect(
    path: Path | None = None, read_only: bool = True
) -> Iterator[duckdb.DuckDBPyConnection]:
    con = duckdb.connect(str(path or config.DB_PATH), read_only=read_only)
    try:
        yield con
    finally:
        con.close()


def table(name: str, path: Path | None = None) -> pd.DataFrame:
    with connect(path) as con:
        return con.execute(f'SELECT * FROM "{name}"').df()


def tables(path: Path | None = None) -> list[str]:
    with connect(path) as con:
        return [r[0] for r in con.execute("SHOW TABLES").fetchall()]


def meta(path: Path | None = None) -> dict[str, object]:
    with connect(path) as con:
        return {k: json.loads(v) for k, v in con.execute("SELECT key, value FROM meta").fetchall()}
