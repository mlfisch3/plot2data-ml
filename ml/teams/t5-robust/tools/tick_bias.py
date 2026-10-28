"""The network's tick-position bias per renderer: its label-only estimate against the truth.

    python teams/t5-robust/tools/tick_bias.py --data data/t5-chartjs-val --limit 100 [--ckpt ... --ocr ...]

For every true tick matched to a detected one (within 3 source px along the
axis), prints the signed offset of the network's own estimate (`pos_net` when
the tick was snapped, else `pos`) and of the final position, along the axis,
in source pixels, for x and y ticks separately, split by whether a snap target
was found. A renderer whose labels sit differently from matplotlib's shows up
as a shifted median of the unsnapped estimate.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.abspath(os.path.join(HERE, "..", "..", "..")))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from p2d.evaluate import load_net  # noqa: E402
from p2d.extract import extract, refine_ticks, run_net  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--ckpt", default="runs/v3/best.pt")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    rows = {("x", s): [] for s in ("snapped", "unsnapped")} | {("y", s): [] for s in ("snapped", "unsnapped")}
    net_err = {("x", s): [] for s in ("snapped", "unsnapped")} | {("y", s): [] for s in ("snapped", "unsnapped")}
    n_gt = n_hit = 0
    for f in files:
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = run_net(net, img)
        ex = refine_ticks(img, extract(out, M, img))
        for key, axis in (("xticks", "x"), ("yticks", "y")):
            pr = getattr(ex, key)
            for t in meta[key]:
                n_gt += 1
                best, bd = None, 1e9
                for p in pr:
                    d = abs(p["pos"] - t["pos"])
                    if d < bd:
                        best, bd = p, d
                if best is None or bd > 3.0:
                    continue
                n_hit += 1
                snapped = "pos_net" in best
                est = best.get("pos_net", best["pos"])
                net_err[(axis, "snapped" if snapped else "unsnapped")].append(est - t["pos"])
                rows[(axis, "snapped" if snapped else "unsnapped")].append(best["pos"] - t["pos"])
    print(f"{a.data}: {n_gt} true labelled ticks, {n_hit} matched within 3 px")
    print(f"{'axis':5s} {'kind':10s} {'n':>5s} {'net median':>11s} {'net mean':>9s} {'net |e|>1px':>12s} {'final median':>13s} {'final |e|>1px':>14s}")
    for (axis, kind), v in rows.items():
        v = np.array(v)
        e = np.array(net_err[(axis, kind)])
        if not len(v):
            continue
        print(f"{axis:5s} {kind:10s} {len(v):5d} {np.median(e):+11.2f} {e.mean():+9.2f} {np.mean(np.abs(e) > 1):12.0%} "
              f"{np.median(v):+13.2f} {np.mean(np.abs(v) > 1):14.0%}")


if __name__ == "__main__":
    main()
