"""Cache the network's extraction for a set of charts, so refinement can be iterated on the CPU.

    python teams/t3-precision/scripts/cache_ex.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 60 --out out/t3/cache-val60

One pickle per chart: the `Extraction` after `extract()` (raw dropped, the vertex heat kept
as float16) and the placement transform. `iter_refine.py` loads these, runs a refinement
and scores it.
"""

from __future__ import annotations

import argparse
import glob
import os
import pickle
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d.data import H_VERTEX  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.extract import extract, run_net  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    net = load_net(a.ckpt)
    os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    for f in files:
        stem = os.path.basename(f)[:-5]
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = run_net(net, img)
        ex = extract(out, M, img)
        ex.raw = {"heat_vertex": out["heat"][H_VERTEX].astype(np.float16)}
        with open(os.path.join(a.out, stem + ".pkl"), "wb") as fh:
            pickle.dump({"ex": ex, "M": M, "json": f}, fh)
    print(f"cached {len(files)} charts in {a.out}")


if __name__ == "__main__":
    main()
