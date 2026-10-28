"""Score a refinement on cached extractions, on the CPU.

    python teams/t3-precision/scripts/iter_refine.py --cache out/t3/cache-val60 [--mode new|old|none] [--viz DIR] [--ids 9000013,...]

Prints the standard summary (all / simple) and the per-column fallback split of colres.py.
"""

from __future__ import annotations

import argparse
import copy
import glob
import json
import math
import os
import pickle
import sys
import time

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d.extract import refine_lines, refine_markers  # noqa: E402
from p2d.metrics import LINE_KINDS, gt_curve, pred_curve, score, summarise_split  # noqa: E402

KEYS = ["line_found", "line_cov_mean", "line_good_cov_mean", "line_rms_median_pct", "line_rms_mean_pct",
        "line_rms_p90_pct", "peak_err_median_pct", "peak_err_p90_pct", "marker_recall", "marker_precision",
        "marker_err_median_pct"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--mode", default="new", choices=["new", "old", "none"])
    ap.add_argument("--viz", default=None)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.cache, "*.pkl")))
    if a.ids:
        want = set(a.ids.split(","))
        files = [f for f in files if os.path.basename(f)[:-4] in want]
    if a.viz:
        os.makedirs(a.viz, exist_ok=True)
    rows = []
    cols = []
    t_ref = 0.0
    for f in files:
        d = pickle.load(open(f, "rb"))
        ex, M = d["ex"], d["M"]
        meta = json.load(open(d["json"]))
        img = cv2.imread(d["json"][:-5] + ".png")[..., ::-1].copy()
        pre = [se.line_px.copy() for se in ex.series]
        t0 = time.time()
        if a.mode == "new":
            ex = refine_lines(img, ex)
        elif a.mode == "old":
            from p2d.extract import refine_lines_v1

            ex = refine_lines_v1(img, ex)
        t_ref += time.time() - t0
        ex = refine_markers(img, ex)
        s = math.hypot(M[0, 0], M[1, 0])
        r = score(meta, ex, canvas_scale=s)
        rows.append(r)
        collect(meta, ex, pre, s, cols)
        if a.viz:
            from p2d.evaluate import draw

            cv2.imwrite(os.path.join(a.viz, f"{meta['seed']}.png"), draw(img, ex, meta)[..., ::-1])
    split = summarise_split(rows)
    print(f"{'metric':28s} {'all':>10s} {'simple':>10s}   (refine {t_ref:.1f}s over {len(files)} charts)")
    for k in KEYS:
        print(f"{k:28s} {split['all'].get(k, float('nan')):>10.4f} {split['simple'].get(k, float('nan')):>10.4f}")
    if a.json:
        json.dump({"summary": split, "rows": rows}, open(a.json, "w"), default=float)
    if not a.quiet:
        report(cols)


def collect(meta, ex, pre, s, cols):
    from scipy.optimize import linear_sum_assignment

    pa = meta["plot_area"]
    ph = pa[3] - pa[1]
    pw = pa[2] - pa[0]
    xs = np.arange(int(np.ceil(pa[0])), int(np.floor(pa[2])) + 1, dtype=float)
    gts = [q for q in meta["series"] if q["kind"] in LINE_KINDS]
    idx = [i for i, se in enumerate(ex.series) if se.kind == "line"]
    preds = [ex.series[i] for i in idx]
    pre_lines = [pre[i] for i in idx]
    simple = len(meta["series"]) <= 3 and max([len(q["x"]) / max(pw, 1) for q in gts] or [0]) <= 0.5
    G = []
    for q in gts:
        y = gt_curve(np.array(q["path_px"]), xs)
        y[(y < pa[1]) | (y > pa[3])] = np.nan
        G.append(y)
    P = [pred_curve(q.line_px, xs, max_gap=3.0 / s) for q in preds]
    if not G or not P:
        return
    C = np.zeros((len(G), len(P)))
    for i, g in enumerate(G):
        for j, p in enumerate(P):
            both = ~np.isnan(g) & ~np.isnan(p)
            ng = (~np.isnan(g)).sum()
            C[i, j] = 1e3 if both.sum() < 3 else np.median(np.abs(g[both] - p[both])) / ph + 0.5 * (1 - both.sum() / max(ng, 1))
    gi, pj = linear_sum_assignment(C)
    for i, j in zip(gi, pj):
        if C[i, j] >= 0.2:
            continue
        g, p = G[i], P[j]
        lp = pre_lines[j][np.argsort(pre_lines[j][:, 0])]
        yc = np.interp(xs, lp[:, 0], lp[:, 1], left=np.nan, right=np.nan)
        both = ~np.isnan(g) & ~np.isnan(p)
        fb = np.abs(p - yc) < 1e-9
        slope = np.abs(np.gradient(g, xs))
        for c in np.nonzero(both)[0]:
            cols.append((p[c] - g[c], fb[c], slope[c], simple, meta["seed"]))


def report(cols):
    if not cols:
        return
    res = np.array([c[0] for c in cols])
    fb = np.array([c[1] for c in cols])
    sl = np.array([c[2] for c in cols])
    sim = np.array([c[3] for c in cols])
    for name, m in (("all", np.ones(len(res), bool)), ("simple", sim)):
        r, f, q = res[m], fb[m], sl[m]
        print(f"== {name}: {m.sum()} cols  fallback {f.mean():.1%}  rms {np.sqrt(np.mean(r**2)):.3f}  med|r| {np.median(np.abs(r)):.3f}  p90 {np.quantile(np.abs(r), .9):.3f}")
        for lab, mm in (("refined", ~f), ("fallback", f)):
            if mm.any():
                print(f"   {lab:8s} {mm.mean():5.1%}  rms {np.sqrt(np.mean(r[mm]**2)):.3f}  med|r| {np.median(np.abs(r[mm])):.3f}  mean {r[mm].mean():+.3f}  p90 {np.quantile(np.abs(r[mm]), .9):.3f}  sq share {np.sum(r[mm]**2)/np.sum(r**2):.1%}")
        for lo, hi in ((0, 1), (1, 3), (3, 1e9)):
            mm = (q >= lo) & (q < hi)
            if mm.any():
                print(f"   |slope| {lo}..{hi}: {mm.mean():5.1%}  rms {np.sqrt(np.mean(r[mm]**2)):.3f}  med|r| {np.median(np.abs(r[mm])):.3f}  fallback {f[mm].mean():.0%}  sq share {np.sum(r[mm]**2)/np.sum(r**2):.1%}")


if __name__ == "__main__":
    main()
