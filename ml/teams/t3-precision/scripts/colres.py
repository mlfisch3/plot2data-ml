"""Where the line error goes: per-column residuals of refined traces against the truth.

    python teams/t3-precision/scripts/colres.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 60 --out out/t3/colres.npz

For every matched line series of every chart, each integer source column inside the
plot area gets a record: residual (pred - gt, source px, and as a fraction of the plot
height), whether the refined centroid or the network fallback produced it, the local
slope of the truth, the line width, the canvas scale, the distance to the nearest
drawn vertex, and the vertex heat the refinement saw. A second table holds one record
per true peak vertex (prominence >= 5% of the plot height): signed shortfall, angle,
line width, whether a vertex was snapped there.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d.data import H_VERTEX, apply, turning_vertices  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.extract import extract, refine_lines, run_net  # noqa: E402
from p2d.metrics import LINE_KINDS, gt_curve, peak_vertices, pred_curve  # noqa: E402


def match(meta, series, xs, ph, max_gap):
    gts = [s for s in meta["series"] if s["kind"] in LINE_KINDS]
    preds = [s for s in series if s.kind == "line"]
    G = []
    for s in gts:
        y = gt_curve(np.array(s["path_px"]), xs)
        y[(y < meta["plot_area"][1]) | (y > meta["plot_area"][3])] = np.nan
        G.append(y)
    P = [pred_curve(s.line_px, xs, max_gap=max_gap) for s in preds]
    out = {}
    if not G or not P:
        return gts, preds, G, P, out
    C = np.zeros((len(G), len(P)))
    for i, g in enumerate(G):
        for j, p in enumerate(P):
            both = ~np.isnan(g) & ~np.isnan(p)
            ng = (~np.isnan(g)).sum()
            if both.sum() < 3:
                C[i, j] = 1e3
                continue
            C[i, j] = np.median(np.abs(g[both] - p[both])) / ph + 0.5 * (1 - both.sum() / max(ng, 1))
    gi, pj = linear_sum_assignment(C)
    out = {i: j for i, j in zip(gi, pj) if C[i, j] < 0.2}
    return gts, preds, G, P, out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-refine", action="store_true")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    cols = []  # per column records
    pks = []  # per peak records
    for f in files:
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = run_net(net, img)
        ex = extract(out, M, img)
        s = math.hypot(M[0, 0], M[1, 0])
        pre = [se.line_px.copy() for se in ex.series]
        if not a.no_refine:
            ex = refine_lines(img, ex)
        pa = meta["plot_area"]
        ph = pa[3] - pa[1]
        pw = pa[2] - pa[0]
        xs = np.arange(int(np.ceil(pa[0])), int(np.floor(pa[2])) + 1, dtype=float)
        gts, preds, G, P, mt = match(meta, ex.series, xs, ph, 3.0 / s)
        simple = len(meta["series"]) <= 3 and max([len(q["x"]) / max(pw, 1) for q in gts] or [0]) <= 0.5
        vh = out["heat"][H_VERTEX]
        # Map pre-refinement series to the same index as ex.series (refine_lines keeps order).
        pre_lines = [p for p, se in zip(pre, ex.series) if se.kind == "line"]
        for i, j in mt.items():
            g, p = G[i], P[j]
            gt = gts[i]
            path = np.array(gt["path_px"])
            verts = turning_vertices(path)
            pv = peak_vertices(path, min_prom=0.05 * ph)
            lp = pre_lines[j]
            o = np.argsort(lp[:, 0])
            lp = lp[o]
            yc = np.interp(xs, lp[:, 0], lp[:, 1], left=np.nan, right=np.nan)
            both = ~np.isnan(g) & ~np.isnan(p)
            slope = np.gradient(g, xs)
            # Which columns kept the network estimate: the refined value equals the interpolated one.
            fb = np.abs(p - yc) < 1e-9
            dv = np.full(len(xs), np.inf)
            if len(verts):
                dv = np.min(np.abs(xs[:, None] - verts[None, :, 0]), axis=1)
            dpk = np.full(len(xs), np.inf)
            if len(pv):
                dpk = np.min(np.abs(xs[:, None] - pv[None, :, 0]), axis=1)
            # Vertex heat at the (canvas) position of each column.
            cp = apply(M, np.column_stack([xs, np.nan_to_num(g, nan=0.0)]))
            ix = np.clip(np.round(cp[:, 0]).astype(int), 1, vh.shape[1] - 2)
            iy = np.clip(np.round(cp[:, 1]).astype(int), 1, vh.shape[0] - 2)
            vmax = np.array([vh[y - 1:y + 2, x - 1:x + 2].max() for x, y in zip(ix, iy)])
            # Other true lines within 6 px of this one at the column.
            near_other = np.zeros(len(xs), bool)
            for k, g2 in enumerate(G):
                if k != i:
                    near_other |= np.abs(g2 - g) < 6
            for c in np.nonzero(both)[0]:
                cols.append((meta["seed"], i, xs[c], p[c] - g[c], (p[c] - g[c]) / ph, fb[c], slope[c], gt["linewidth_px"],
                             s, dv[c], dpk[c], vmax[c], near_other[c], simple, len(gt["x"]) / max(pw, 1), ph))
            # Peaks.
            if len(pv):
                yp = pred_curve(preds[j].line_px, pv[:, 0], max_gap=3.0 / s)
                for (vx, vy), yq in zip(pv, yp):
                    if np.isnan(yq) or not (pa[0] <= vx <= pa[2] and pa[1] <= vy <= pa[3]):
                        continue
                    k = int(np.argmin(np.abs(path[:, 0] - vx) + np.abs(path[:, 1] - vy)))
                    a_ = path[k] - path[max(0, k - 1)]
                    b_ = path[min(len(path) - 1, k + 1)] - path[k]
                    ang = math.degrees(math.acos(np.clip((a_ @ b_) / max(1e-9, np.linalg.norm(a_) * np.linalg.norm(b_)), -1, 1)))
                    up = 1.0 if (k > 0 and path[k, 1] < path[k - 1, 1]) else -1.0  # a maximum on screen (y smaller)
                    short = (yq - vy) * up  # positive: short of the tip
                    snapped = preds[j].vertices_px is not None and len(preds[j].vertices_px) and \
                        np.min(np.abs(preds[j].vertices_px[:, 0] - vx)) < 1.0
                    cx, cy = apply(M, [[vx, vy]])[0]
                    vhv = vh[int(np.clip(round(cy), 0, vh.shape[0] - 1)), int(np.clip(round(cx), 0, vh.shape[1] - 1))]
                    pks.append((meta["seed"], i, vx, vy, short, short / ph, ang, gt["linewidth_px"], s, bool(snapped), vhv,
                                min(np.linalg.norm(a_), np.linalg.norm(b_)), simple, ph))
    cols = np.array(cols, dtype=object)
    pks = np.array(pks, dtype=object)
    np.savez(a.out, cols=cols, pks=pks, allow_pickle=True)
    report(cols, pks)


def report(cols, pks):
    def arr(t, k):
        return np.array([r[k] for r in t], float)

    print(f"columns {len(cols)}  peaks {len(pks)}")
    for name, sel in (("all", np.ones(len(cols), bool)), ("simple", arr(cols, 13) > 0)):
        c = cols[sel]
        res = arr(c, 3)
        resf = arr(c, 4) * 100
        fb = arr(c, 5) > 0
        print(f"\n== {name}: {len(c)} columns, fallback {fb.mean():.1%}")
        print(f"  all      rms {np.sqrt(np.mean(res ** 2)):.3f} px  med|r| {np.median(np.abs(res)):.3f}  rms% {np.sqrt(np.mean(resf ** 2)):.3f}  p90|r| {np.quantile(np.abs(res), .9):.2f}")
        for lab, m in (("refined", ~fb), ("fallback", fb)):
            if m.any():
                print(f"  {lab:8s} rms {np.sqrt(np.mean(res[m] ** 2)):.3f} px  med|r| {np.median(np.abs(res[m])):.3f}  mean r {res[m].mean():+.3f}  p90|r| {np.quantile(np.abs(res[m]), .9):.2f}  share of sq err {np.sum(res[m] ** 2) / np.sum(res ** 2):.1%}")
        slope = np.abs(arr(c, 6))
        for lo, hi in ((0, 0.25), (0.25, 1), (1, 3), (3, 1e9)):
            m = (slope >= lo) & (slope < hi)
            if m.any():
                print(f"  |slope| {lo:>4}..{hi:<4}: {m.mean():5.1%} cols  rms {np.sqrt(np.mean(res[m] ** 2)):.3f}  med|r| {np.median(np.abs(res[m])):.3f}  fallback {fb[m].mean():.0%}  sq share {np.sum(res[m] ** 2) / np.sum(res ** 2):.1%}")
        lw = arr(c, 7)
        for lo, hi in ((0, 1.5), (1.5, 2.5), (2.5, 4), (4, 1e9)):
            m = (lw >= lo) & (lw < hi)
            if m.any():
                print(f"  lw {lo}..{hi}: {m.mean():5.1%} cols  rms {np.sqrt(np.mean(res[m] ** 2)):.3f}  med|r| {np.median(np.abs(res[m])):.3f}  mean r {res[m].mean():+.3f}")
        sc = arr(c, 8)
        for lo, hi in ((0, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 3)):
            m = (sc >= lo) & (sc < hi)
            if m.any():
                print(f"  scale {lo}..{hi}: {m.mean():5.1%} cols  rms {np.sqrt(np.mean(res[m] ** 2)):.3f}  med|r| {np.median(np.abs(res[m])):.3f}  fallback {fb[m].mean():.0%}")
        dv = arr(c, 9)
        for lo, hi in ((0, 1.5), (1.5, 4), (4, 10), (10, 1e12)):
            m = (dv >= lo) & (dv < hi)
            if m.any():
                print(f"  dist to vertex {lo}..{hi}: {m.mean():5.1%} cols  rms {np.sqrt(np.mean(res[m] ** 2)):.3f}  med|r| {np.median(np.abs(res[m])):.3f}  fallback {fb[m].mean():.0%}  sq share {np.sum(res[m] ** 2) / np.sum(res ** 2):.1%}")
        vm = arr(c, 11)
        m = vm > 0.3
        print(f"  vertex-heat gate on: {m.mean():.1%} cols  rms {np.sqrt(np.mean(res[m] ** 2)):.3f}  sq share {np.sum(res[m] ** 2) / np.sum(res ** 2):.1%}")
        no = arr(c, 12) > 0
        print(f"  near another line: {no.mean():.1%} cols  rms {np.sqrt(np.mean(res[no] ** 2)):.3f}  sq share {np.sum(res[no] ** 2) / np.sum(res ** 2):.1%}")
    if len(pks):
        for name, sel in (("all", np.ones(len(pks), bool)), ("simple", arr(pks, 12) > 0)):
            p = pks[sel]
            sh = arr(p, 4)
            shf = arr(p, 5) * 100
            sn = arr(p, 9) > 0
            print(f"\n== peaks {name}: {len(p)}  snapped {sn.mean():.0%}  median |err| {np.median(np.abs(shf)):.3f}%  median signed short {np.median(sh):+.2f} px  mean {sh.mean():+.2f}")
            for lab, m in (("snapped", sn), ("not", ~sn)):
                if m.any():
                    print(f"  {lab:8s} n {m.sum()}  med|err| {np.median(np.abs(shf[m])):.3f}%  med short {np.median(sh[m]):+.2f} px  p90|err| {np.quantile(np.abs(shf[m]), .9):.2f}%")
            ang = arr(p, 6)
            for lo, hi in ((0, 30), (30, 60), (60, 120), (120, 181)):
                m = (ang >= lo) & (ang < hi)
                if m.any():
                    print(f"  angle {lo}..{hi}: n {m.sum()}  med|err| {np.median(np.abs(shf[m])):.3f}%  med short {np.median(sh[m]):+.2f} px")
            lw = arr(p, 7)
            for lo, hi in ((0, 1.5), (1.5, 2.5), (2.5, 4), (4, 1e9)):
                m = (lw >= lo) & (lw < hi)
                if m.any():
                    print(f"  lw {lo}..{hi}: n {m.sum()}  med|err| {np.median(np.abs(shf[m])):.3f}%  med short {np.median(sh[m]):+.2f} px")
            seg = arr(p, 11)
            for lo, hi in ((0, 3), (3, 8), (8, 20), (20, 1e9)):
                m = (seg >= lo) & (seg < hi)
                if m.any():
                    print(f"  shortest flank {lo}..{hi} px: n {m.sum()}  med|err| {np.median(np.abs(shf[m])):.3f}%  med short {np.median(sh[m]):+.2f} px")


if __name__ == "__main__":
    main()
