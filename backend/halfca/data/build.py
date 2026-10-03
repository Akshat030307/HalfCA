"""Generate a dataset and load it into DuckDB.

python -m halfca.data.build --scenario demo              # seed 2609 → data/
python -m halfca.data.build --scenario random --seed 7   # → data/random-7/
"""

from __future__ import annotations

import argparse
import hashlib
import time
from pathlib import Path

from halfca import config, store
from halfca.ai.llm import default_adjudicator
from halfca.ingest.csv_loader import read_folder
from halfca.pipeline import reconcile

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


def run(scenario: str, seed: int | None = None, out: Path | None = None) -> Path:
    started = time.perf_counter()
    world = make_world(scenario, seed)
    out = out or (
        config.DATA_DIR if scenario == "demo" else config.DATA_DIR / f"random-{world.seed}"
    )
    tables = derive(world)
    write(world, tables, out)
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
        "code": fingerprint(),
    }
    result = reconcile(frames, meta, adjudicator=default_adjudicator())
    tables = {f"raw_{k}": v for k, v in frames.items()}
    tables.update({f"res_{k}": v for k, v in result.tables.items()})
    db = store.save(tables, meta, out / "halfca.duckdb")
    took = time.perf_counter() - started
    s = result.summary
    print(
        f"[{scenario} seed {world.seed}] " + ", ".join(f"{k} {len(v)}" for k, v in frames.items())
    )
    print(
        f"  matched {s['matched']} · discrepancies {s['discrepancies']} · duplicates "
        f"{s['duplicates']} · unmatched {s['unmatched']} · IMS {s['ims']['accept']}/"
        f"{s['ims']['reject']}/{s['ims']['pending']} · exposure ₹{s['exposure'] / 1e5:.1f} L"
        + (" · stage 4 skipped (no LLM)" if s["stage4_skipped"] else "")
    )
    print(f"→ {db} ({took:.1f}s)")
    return db


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
    if args.if_stale and args.scenario == "demo" and is_fresh(args.out or config.DB_PATH):
        print("demo database is up to date")
        return
    run(args.scenario, args.seed, args.out)


if __name__ == "__main__":
    main()
