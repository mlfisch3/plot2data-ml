"""Two questions about the embedding, answered with numbers and pictures.

    python teams/t2-trace/tools/embcheck.py --ckpt runs/v3/best.pt --data data/t2-cross --limit 20 --out out/t2c/emb

(a) At a crossing of two series: does the embedding change abruptly across the
    ridge blob, so that the pixels of A and of B in one column can be told apart?
    For every column where two true series lie within 6 px of each other, the
    distance between the embedding at A's ridge and at B's ridge is compared
    with the within-series step (embedding distance between adjacent columns
    of the same series) and with the same A-B distance 20 columns away.
(b) For two series: is the embedding different between them away from any
    crossing? For every pair, the distance between the series means, the
    within-series spread (p50, p90 of the distance to the own mean), and the
    fraction of columns where the pixel is nearer its own mean than the other's,
    split by distance from the nearest crossing.

Crops of the embedding (PCA to RGB) around crossings are written as PNGs, with
the true paths drawn in, at 6x magnification.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d import extract as X  # noqa: E402
from p2d.data import H_LINE, apply  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.metrics import LINE_KINDS  # noqa: E402


def curves(meta, M, H, W):
    out = []
    for s in meta["series"]:
        if s["kind"] not in LINE_KINDS or len(s["path_px"]) < 2:
            continue
        p = apply(M, s["path_px"])
        o = np.argsort(p[:, 0], kind="stable")
        xs = np.arange(W)
        y = np.interp(xs, p[o, 0], p[o, 1], left=np.nan, right=np.nan)
        pa = apply(M, [[meta["plot_area"][0], meta["plot_area"][1]], [meta["plot_area"][2], meta["plot_area"][3]]])
        y[(xs < pa[0, 0]) | (xs > pa[1, 0]) | (y < pa[0, 1]) | (y > pa[1, 1])] = np.nan
        out.append((s, y))
    return out


def ridge_emb(emb, lh, x, y, r=2):
    """Embedding at the strongest line-heat pixel within r rows of (x, y); None if no ridge."""
    H = lh.shape[0]
    yi = int(round(y))
    a, b = max(0, yi - r), min(H, yi + r + 1)
    if b <= a:
        return None, None
    col = lh[a:b, x]
    k = int(np.argmax(col))
    if col[k] < 0.25:
        return None, None
    return emb[:, a + k, x], a + k


def pca_rgb(emb, mask):
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    img = np.full((H, W, 3), 255, np.uint8)
    if len(xs) < 8:
        return img
    v = emb[:, ys, xs].T
    mu = v.mean(0)
    _, _, vt = np.linalg.svd(v - mu, full_matrices=False)
    proj = (v - mu) @ vt[:3].T
    lo, hi = np.quantile(proj, 0.02, 0), np.quantile(proj, 0.98, 0)
    img[ys, xs] = (np.clip((proj - lo) / np.maximum(hi - lo, 1e-6), 0, 1) * 255).astype(np.uint8)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-crops", type=int, default=12)
    a = ap.parse_args()
    net = load_net(a.ckpt)
    os.makedirs(a.out, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    cross_ab, cross_step, far_ab, cross_split = [], [], [], []
    pair_stats = []
    n_crops = 0
    for f in files:
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = X.run_net(net, img)
        emb, lh = out["emb"], out["heat"][H_LINE]
        H, W = lh.shape
        cs = curves(meta, M, H, W)
        rgb = pca_rgb(emb, lh > 0.25)
        for i in range(len(cs)):
            si, yi = cs[i]
            ei = {}
            for x in range(W):
                if not np.isnan(yi[x]):
                    e, _ = ridge_emb(emb, lh, x, yi[x])
                    if e is not None:
                        ei[x] = e
            if len(ei) < 10:
                continue
            mi = np.mean([v for v in ei.values()], 0)
            own = np.array([np.linalg.norm(ei[x] - mi) for x in ei])
            for j in range(i + 1, len(cs)):
                sj, yj = cs[j]
                ej = {}
                for x in range(W):
                    if not np.isnan(yj[x]):
                        e, _ = ridge_emb(emb, lh, x, yj[x])
                        if e is not None:
                            ej[x] = e
                if len(ej) < 10:
                    continue
                mj = np.mean([v for v in ej.values()], 0)
                d = np.abs(yi - yj)
                near = np.nonzero(d < 6)[0]
                # Crossings: runs of near columns.
                runs = []
                if len(near):
                    start = near[0]
                    prev = near[0]
                    for x in near[1:]:
                        if x != prev + 1:
                            runs.append((start, prev))
                            start = x
                        prev = x
                    runs.append((start, prev))
                centres = [int((r0 + r1) / 2) for r0, r1 in runs]
                # (a) At each crossing column: A-B distance vs within-series step vs 20 columns away.
                for r0, r1 in runs:
                    for x in range(r0, r1 + 1):
                        if x in ei and x in ej and abs(yi[x] - yj[x]) >= 1.5:
                            cross_ab.append(float(np.linalg.norm(ei[x] - ej[x])))
                            if x + 1 in ei:
                                cross_step.append(float(np.linalg.norm(ei[x] - ei[x + 1])))
                    for x in (r0 - 20, r1 + 20):
                        if x in ei and x in ej:
                            far_ab.append(float(np.linalg.norm(ei[x] - ej[x])))
                    # Can the blob be split within the column? Walk down the column through both ridges and
                    # record the largest embedding jump between adjacent rows versus the A-B distance.
                    xm = int((r0 + r1) / 2)
                    if xm in ei and xm in ej:
                        ya, yb = sorted([int(round(yi[xm])), int(round(yj[xm]))])
                        if yb - ya >= 2:
                            col = emb[:, ya:yb + 1, xm]
                            jumps = np.linalg.norm(np.diff(col, axis=1), axis=0)
                            cross_split.append((float(jumps.max()), float(np.linalg.norm(ei[xm] - ej[xm]))))
                # (b) Separation away from crossings.
                dist_to_cross = np.full(W, np.inf)
                for c in centres:
                    dist_to_cross = np.minimum(dist_to_cross, np.abs(np.arange(W) - c))
                own_i = np.array([np.linalg.norm(ei[x] - mi) < np.linalg.norm(ei[x] - mj) for x in ei])
                own_j = np.array([np.linalg.norm(ej[x] - mj) < np.linalg.norm(ej[x] - mi) for x in ej])
                dci = np.array([dist_to_cross[x] for x in ei])
                dcj = np.array([dist_to_cross[x] for x in ej])
                same_colour = si["color"].lower() == sj["color"].lower()
                for lo, hi in ((0, 5), (5, 20), (20, 1e9)):
                    seli = (dci >= lo) & (dci < hi)
                    selj = (dcj >= lo) & (dcj < hi)
                    n = seli.sum() + selj.sum()
                    if n:
                        pair_stats.append(dict(seed=meta["seed"], i=i, j=j, same=same_colour, band=f"{lo}-{hi if hi < 1e9 else 'inf'}",
                                               n=int(n), own=float((own_i[seli].sum() + own_j[selj].sum()) / n),
                                               mean_dist=float(np.linalg.norm(mi - mj)), spread_p50=float(np.median(own)),
                                               spread_p90=float(np.quantile(own, 0.9)), n_cross=len(runs)))
                # Crops around crossings.
                for c in centres[:2]:
                    if n_crops >= a.max_crops:
                        break
                    yc = int(round(np.nanmean([yi[c], yj[c]])))
                    x0, x1 = max(0, c - 30), min(W, c + 30)
                    y0, y1 = max(0, yc - 24), min(H, yc + 24)
                    crop = rgb[y0:y1, x0:x1].copy()
                    src = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderValue=(255, 255, 255))[y0:y1, x0:x1]
                    heat = np.repeat((255 - 255 * lh[y0:y1, x0:x1])[..., None].astype(np.uint8), 3, -1)
                    z = 6
                    panels = []
                    for p in (src, heat, crop):
                        big = cv2.resize(p, None, fx=z, fy=z, interpolation=cv2.INTER_NEAREST)
                        for s, y in ((si, yi), (sj, yj)):
                            pts = [((x - x0 + 0.5) * z, (y[x] - y0 + 0.5) * z) for x in range(x0, x1) if not np.isnan(y[x])]
                            if len(pts) > 1:
                                cv2.polylines(big, [np.round(np.array(pts)).astype(np.int32)], False, (0, 200, 0), 1, cv2.LINE_AA)
                        panels.append(big)
                    comp = np.hstack(panels)
                    cv2.putText(comp, f"seed {meta['seed']} s{i}/s{j} col {c} same_colour={same_colour}", (4, 14),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
                    cv2.imwrite(os.path.join(a.out, f"cross-{meta['seed']}-s{i}s{j}-c{c}.png"), comp[..., ::-1])
                    n_crops += 1
        # Whole-chart PCA with paths.
        full = rgb.copy()
        for s, y in cs:
            pts = [(x, y[x]) for x in range(W) if not np.isnan(y[x])]
            if len(pts) > 1:
                cv2.polylines(full, [np.round(np.array(pts) * 4).astype(np.int32)], False, (0, 160, 0), 1, cv2.LINE_AA, shift=2)
        cv2.imwrite(os.path.join(a.out, f"pca-{meta['seed']}.png"), full[..., ::-1])

    def q(v):
        v = np.array(v)
        return f"n={len(v)} p10={np.quantile(v, .1):.2f} p50={np.median(v):.2f} p90={np.quantile(v, .9):.2f}" if len(v) else "n=0"

    print("(a) crossings of two series (columns where both ridges are present and >= 1.5 px apart)")
    print("    A-B embedding distance at the crossing column:    ", q(cross_ab))
    print("    within-series step (adjacent columns) there:        ", q(cross_step))
    print("    A-B distance 20 columns away from the crossing:     ", q(far_ab))
    if cross_split:
        cs_ = np.array(cross_split)
        print(f"    walking down the column through both ridges: largest adjacent-row jump {q(cs_[:, 0])}; "
              f"jump >= 0.5 * A-B distance in {np.mean(cs_[:, 0] >= 0.5 * cs_[:, 1]) * 100:.0f}% of crossings, >= 1.5 in {np.mean(cs_[:, 0] >= 1.5) * 100:.0f}%")
    print("(b) pairs of series: nearer own mean than the other's, by distance from the nearest crossing")
    for same in (False, True):
        for band in ("0-5", "5-20", "20-inf"):
            rows = [p for p in pair_stats if p["same"] == same and p["band"] == band]
            if not rows:
                continue
            n = sum(p["n"] for p in rows)
            own = sum(p["own"] * p["n"] for p in rows) / n
            print(f"    same_colour={same!s:5s} band {band:7s} columns {n:6d}  own-mean nearer {own * 100:5.1f}%  "
                  f"mean-to-mean dist p50 {np.median([p['mean_dist'] for p in rows]):.2f}  within spread p50 {np.median([p['spread_p50'] for p in rows]):.2f} p90 {np.median([p['spread_p90'] for p in rows]):.2f}")
    json.dump(dict(cross_ab=cross_ab, cross_step=cross_step, far_ab=far_ab, cross_split=cross_split, pairs=pair_stats),
              open(os.path.join(a.out, "embcheck.json"), "w"))


if __name__ == "__main__":
    main()
