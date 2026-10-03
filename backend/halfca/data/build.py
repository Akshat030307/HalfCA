"""Generate a dataset and load it into DuckDB.

python -m halfca.data.build --scenario demo              # seed 2609 → data/
python -m halfca.data.build --scenario random --seed 7   # → data/random-7/
"""

from __future__ import annotations

import argparse
import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd

from halfca import config, store
from halfca.ai.llm import default_adjudicator
from halfca.engines.matching import Adjudicator
from halfca.ingest.csv_loader import read_folder
from halfca.pipeline import Progress, reconcile

from .derive import derive
from .model import World
from .write import write


def fingerprint() -> str:
    """Hash of the backend's code and data definitions. A database built by different
    code is stale and gets rebuilt when the container starts."""
    root = Path(__file__).resolve().parents[1]
    h = hashlib.sha256()
    for f in sorted(root.rglob("*")):
        if f.suffix in (".py", ".json") and "__pycache__" not in f.parts:
            h.update(f.relative_to(root).as_posix().encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


def is_fresh(db: Path) -> bool:
    if not db.is_file():
        return False
    try:
        return store.meta(db).get("code") == fingerprint()
    except Exception:  # an unreadable or pre-M2 database is stale
        return False


def make_world(scenario: str, seed: int | None) -> World:
    if scenario == "demo":
        from .scenario_demo import build

        return build(seed or config.DEMO_SEED)
    if scenario == "random":
        from .scenario_random import build as build_random

        return build_random(seed if seed is not None else 7)
    raise SystemExit(f"unknown scenario {scenario!r}")


DEFAULT = "default"  # use the configured LLM adjudicator (None when no provider)


def reconcile_and_save(
    frames: dict[str, pd.DataFrame],
    meta: dict[str, Any],
    db: Path,
    adjudicator: Adjudicator | None | str = DEFAULT,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Run the pipeline and atomically replace `db` with raw + results. Returns the summary."""
    adj = default_adjudicator() if adjudicator == DEFAULT else adjudicator
    meta = {**meta, "code": fingerprint(), "dataset_id": uuid.uuid4().hex[:12]}
    result = reconcile(frames, meta, adjudicator=adj, progress=progress)  # type: ignore[arg-type]
    tables = {f"raw_{k}": v for k, v in frames.items()}
    tables.update({f"res_{k}": v for k, v in result.tables.items()})
    store.save(tables, meta, db)
    return result.summary


def describe(summary: dict[str, Any]) -> str:
    s = summary
    return (
        f"matched {s['matched']} · discrepancies {s['discrepancies']} · duplicates "
        f"{s['duplicates']} · unmatched {s['unmatched']} · IMS {s['ims']['accept']}/"
        f"{s['ims']['reject']}/{s['ims']['pending']} · exposure ₹{s['exposure'] / 1e5:.1f} L"
        + (" · stage 4 skipped (no LLM)" if s["stage4_skipped"] else "")
    )


def run(
    scenario: str,
    seed: int | None = None,
    out: Path | None = None,
    adjudicator: Adjudicator | None | str = DEFAULT,
    progress: Progress | None = None,
) -> Path:
    started = time.perf_counter()
    world = make_world(scenario, seed)
    out = out or (
        config.DATA_DIR if scenario == "demo" else config.DATA_DIR / f"random-{world.seed}"
    )
    write(world, derive(world), out)
    # Truth labels stay on disk for tests and eval; the engines must never see them.
    frames = {k: v for k, v in read_folder(out).items() if k != "truth_labels"}
    meta = {
        "scenario": world.scenario,
        "seed": world.seed,
        "period": world.period,
        "as_of": world.as_of.isoformat(),
        "user_gstin": world.me.gstin,
        "user_name": world.me.name,
        "targets": world.targets,
    }
    db = out / "halfca.duckdb"
    summary = reconcile_and_save(frames, meta, db, adjudicator, progress)
    print(
        f"[{scenario} seed {world.seed}] " + ", ".join(f"{k} {len(v)}" for k, v in frames.items())
    )
    print(f"  {describe(summary)}")
    print(f"→ {db} ({time.perf_counter() - started:.1f}s)")
    return db


def rereconcile(
    db: Path | None = None,
    adjudicator: Adjudicator | None | str = DEFAULT,
    progress: Progress | None = None,
) -> dict[str, Any]:
    """Re-run the engines over the raw tables already in `db` (e.g. an uploaded dataset)."""
    db = db or config.DB_PATH
    frames = store.load_prefixed("raw_", db)
    return reconcile_and_save(frames, store.meta(db), db, adjudicator, progress)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scenario", choices=["demo", "random"], default="demo")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument(
        "--if-stale",
        action="store_true",
        help="skip when the database was built by this exact code",
    )
    args = ap.parse_args()
    db = args.out / "halfca.duckdb" if args.out else config.DB_PATH
    if args.if_stale and args.scenario == "demo":
        if is_fresh(db):
            print("database is up to date")
            return
        if db.is_file() and _scenario(db) == "upload":
            # Someone's uploaded month: re-run the new engines on it, don't replace it.
            print(f"re-reconciling the uploaded dataset: {describe(rereconcile(db))}")
            return
    run(args.scenario, args.seed, args.out)


def _scenario(db: Path) -> str | None:
    try:
        return str(store.meta(db).get("scenario"))
    except Exception:
        return None


if __name__ == "__main__":
    main()
