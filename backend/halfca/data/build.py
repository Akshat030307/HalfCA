"""Generate a dataset and load it into DuckDB.

python -m halfca.data.build --scenario demo              # seed 2609 → data/
python -m halfca.data.build --scenario random --seed 7   # → data/random-7/
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from halfca import config, store
from halfca.ingest.csv_loader import read_folder

from .derive import derive
from .model import World
from .write import write


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
    db = store.save(
        frames,
        {
            "scenario": world.scenario,
            "seed": world.seed,
            "period": world.period,
            "as_of": world.as_of.isoformat(),
            "user_gstin": world.me.gstin,
            "user_name": world.me.name,
            "targets": world.targets,
        },
        out / "halfca.duckdb",
    )
    took = time.perf_counter() - started
    counts = ", ".join(f"{k} {len(v)}" for k, v in frames.items())
    print(f"[{scenario} seed {world.seed}] {counts}")
    print(f"→ {db} ({took:.1f}s)")
    return db


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scenario", choices=["demo", "random"], default="demo")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.scenario, args.seed, args.out)


if __name__ == "__main__":
    main()
