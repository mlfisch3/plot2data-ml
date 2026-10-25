"""Write a synthetic dataset to disk.

    python -m p2d.synth.build --out data/mpl-v1 --start 0 --count 30000 --workers 14
    python -m p2d.synth.build --out data/plotly-v1 --start 500000 --count 3000 --workers 3 --renderer plotly

Each sample is `<id>.png` (the chart), `<id>.sem.png` and `<id>.inst.png` (label
maps) and `<id>.json` (geometry and values). Seeds are the sample ids, so any
sample can be regenerated exactly.
"""

from __future__ import annotations

import argparse
import os as _os

_os.environ.setdefault("OMP_NUM_THREADS", "1")
import json
import logging
import os
import sys
import time
from multiprocessing import Pool

import cv2


def _work(args):
    out, seed, renderer = args
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    if renderer == "plotly":
        from .plotly_render import generate
    else:
        from .mpl_render import generate

    stem = os.path.join(out, f"{seed:07d}")
    if os.path.exists(stem + ".json"):
        return seed, True
    try:
        r = generate(seed)
    except Exception as e:  # a bad random combination is skipped, not fatal
        return seed, repr(e)
    cv2.imwrite(stem + ".png", r.image[..., ::-1])
    cv2.imwrite(stem + ".sem.png", r.sem)
    cv2.imwrite(stem + ".inst.png", r.inst)
    with open(stem + ".json.tmp", "w") as f:
        json.dump(r.meta, f)
    os.replace(stem + ".json.tmp", stem + ".json")
    return seed, True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, required=True)
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    ap.add_argument("--renderer", choices=["matplotlib", "plotly"], default="matplotlib")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    jobs = [(a.out, s, a.renderer) for s in range(a.start, a.start + a.count)]
    t0 = time.time()
    failed = 0
    with Pool(a.workers, maxtasksperchild=200) as pool:
        for i, (seed, ok) in enumerate(pool.imap_unordered(_work, jobs, chunksize=8)):
            if ok is not True:
                failed += 1
                print(f"seed {seed} failed: {ok}", file=sys.stderr)
            if (i + 1) % 1000 == 0:
                print(f"{i + 1}/{len(jobs)}  {time.time() - t0:.0f}s  failed={failed}", flush=True)
    print(f"done {len(jobs)} in {time.time() - t0:.0f}s, failed={failed}")


if __name__ == "__main__":
    main()
