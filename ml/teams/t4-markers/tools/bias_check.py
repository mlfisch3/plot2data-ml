"""Marker-centre bias on images without pixel ground truth: returned centre vs the ink centroid.

    P2D_ROOT=... python teams/t4-markers/tools/bias_check.py --ckpt runs/v3/best.pt --out out/t4/bias.json image.png ...

For every returned marker, the blob of source pixels whose colour lies on the paper-to-series-colour
blend around it (the same ink weight `refine_markers` uses) gives an ink centroid; on a renderer that
places markers sub-pixel (Chart.js, Plotly) that centroid is the drawn centre. The difference, for the
raw network peak and for the refined position, is the bias of each stage, in source pixels.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d import extract as E  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402


def ink_centroid(img, paper, colour, x, y, r=10):
    H, W = img.shape[:2]
    x0, y0 = int(round(x)) - r, int(round(y)) - r
    if x0 < 0 or y0 < 0 or x0 + 2 * r + 1 > W or y0 + 2 * r + 1 > H:
        return None
    d = colour - paper
    dd = float(d @ d)
    if dd < 400:
        return None
    patch = img[y0:y0 + 2 * r + 1, x0:x0 + 2 * r + 1] - paper
    t = (patch @ d) / dd
    off = np.linalg.norm(patch - t[..., None] * d, axis=-1) / math.sqrt(dd)
    w = np.where(off < 0.3, np.clip(t, 0, 1), 0.0)
    n, lab = cv2.connectedComponents((w > 0.5).astype(np.uint8), connectivity=8)
    c0 = lab[r, r]
    if c0 == 0:
        ys, xs = np.nonzero(lab)
        if not len(xs):
            return None
        k = np.argmin((xs - r) ** 2 + (ys - r) ** 2)
        c0 = lab[ys[k], xs[k]]
    blob = cv2.dilate((lab == c0).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    if blob[0].any() or blob[-1].any() or blob[:, 0].any() or blob[:, -1].any():
        return None
    ww = np.where(blob, w, 0.0)
    yy, xx = np.mgrid[0:2 * r + 1, 0:2 * r + 1]
    s = ww.sum()
    return x0 + (ww * xx).sum() / s, y0 + (ww * yy).sum() / s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+")
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    net = load_net(a.ckpt)
    report = {}
    for path in a.images:
        img = cv2.imread(path)[..., ::-1].copy()
        out, M = E.run_net(net, img)
        ex_raw = E.extract(out, M, img)
        raw = [(x, y, se.color) for se in ex_raw.series for x, y in se.markers_px]
        ex_ref = E.refine_markers(img, E.refine_lines(img, E.extract(out, M, img)))
        ref = [(x, y, se.color) for se in ex_ref.series for x, y in se.markers_px]
        imf = img.astype(np.float32)
        paper = E._paper_colour(img, ex_raw.plot_area).astype(np.float32)
        rows = {"raw": [], "refined": []}
        for key, mk in (("raw", raw), ("refined", ref)):
            for x, y, col in mk:
                c = ink_centroid(imf, paper, np.array(col, np.float32), x, y)
                if c is not None:
                    rows[key].append((x - c[0], y - c[1]))
        rep = {"n_markers": len(raw)}
        for key, v in rows.items():
            if v:
                v = np.array(v)
                rep[key] = dict(n=len(v), dx_mean=float(v[:, 0].mean()), dy_mean=float(v[:, 1].mean()),
                                dx_median=float(np.median(v[:, 0])), dy_median=float(np.median(v[:, 1])),
                                abs_median=float(np.median(np.hypot(v[:, 0], v[:, 1]))), abs_p90=float(np.quantile(np.hypot(v[:, 0], v[:, 1]), 0.9)))
        report[os.path.basename(path)] = rep
        print(os.path.basename(path), json.dumps(rep))
    if a.out:
        json.dump(report, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
