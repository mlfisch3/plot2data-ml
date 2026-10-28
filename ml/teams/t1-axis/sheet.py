"""Contact sheet of axis strips from diag overlays, to look at many failures at once.

    python teams/t1-axis/sheet.py out/t1/diag-mpl y out/t1/sheet-y-cropped.png 9000118 9000143 9000004
    python teams/t1-axis/sheet.py out/t1/diag-mpl x out/t1/sheet-x.png 9000003 9000014 --scale 1.5

For a y strip the left 32% of the chart is taken (the whole height); for x the bottom 30% (the whole width).
Strips are scaled to a common width and stacked with the seed written on each.
"""

from __future__ import annotations

import argparse
import json
import os

import cv2
import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("diag_dir")
    ap.add_argument("axis", choices=["x", "y"])
    ap.add_argument("out")
    ap.add_argument("seeds", nargs="+", type=int)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--width", type=int, default=900)
    ap.add_argument("--frac", type=float, default=None)
    a = ap.parse_args()
    recs = {r["seed"]: r for r in json.load(open(os.path.join(a.diag_dir, "diag.json")))}
    tiles = []
    for s in a.seeds:
        p = os.path.join(a.diag_dir, f"{s}.png")
        if not os.path.exists(p):
            continue
        im = cv2.imread(p)
        H, W = im.shape[:2]
        if a.axis == "y":
            f = a.frac or 0.32
            im = im[:, : int(W * f)]
        else:
            f = a.frac or 0.3
            im = im[int(H * (1 - f)):]
        d = recs[s][a.axis]
        fit = d["fit"]
        txt = f"{s} {a.axis}: {d['verdict']} err={100 * (d['err'] or float('nan')):.2f}% {fit['scale'] if fit else '-'}/{d['scale_gt']} " \
              f"cause={','.join(d['cause'])}"
        im = cv2.resize(im, None, fx=a.scale, fy=a.scale, interpolation=cv2.INTER_CUBIC) if a.scale != 1 else im
        bar = np.full((18, im.shape[1], 3), 255, np.uint8)
        cv2.putText(bar, txt[:200], (3, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 0), 1, cv2.LINE_AA)
        tiles.append(np.vstack([bar, im]))
    w = max(t.shape[1] for t in tiles)
    tiles = [np.hstack([t, np.full((t.shape[0], w - t.shape[1], 3), 200, np.uint8)]) if t.shape[1] < w else t for t in tiles]
    sheet = np.vstack(tiles)
    if sheet.shape[1] > a.width:
        f = a.width / sheet.shape[1]
        sheet = cv2.resize(sheet, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    cv2.imwrite(a.out, sheet)
    print(a.out, sheet.shape)


if __name__ == "__main__":
    main()
