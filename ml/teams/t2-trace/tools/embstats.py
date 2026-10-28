"""Embedding statistics along the true paths, and an oracle-cluster upper bound for the tracker.

For each GT line series: embeddings at the ridge pixel nearest the true path per column.
Reports: spread to the series mean, adjacent-column distance, nearest other-series mean distance,
and the chain coverage when clusters are the ground-truth instance map (peel_chains unchanged).
"""
from __future__ import annotations
import argparse, glob, json, os, sys
import numpy as np, cv2
sys.path.insert(0, os.getcwd())
from p2d.data import H_LINE, apply, fit_transform, CANVAS_H, CANVAS_W
from p2d.extract import run_net, plot_frame, column_runs, peel_chains
from p2d.evaluate import load_net
from p2d.metrics import gt_curve, LINE_KINDS

ap = argparse.ArgumentParser(); ap.add_argument("--ckpt", required=True); ap.add_argument("--data", required=True)
ap.add_argument("--limit", type=int, default=60); a = ap.parse_args()
net = load_net(a.ckpt)
files = sorted(glob.glob(os.path.join(a.data, "*.json")))[:a.limit]
spread, adj, sep, cov_oracle, cov_oracle_n, q_spread = [], [], [], [], 0, []
for f in files:
    meta = json.load(open(f)); img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
    inst = cv2.imread(f[:-5] + ".inst.png", cv2.IMREAD_UNCHANGED)
    out, M = run_net(net, img); heat, emb = out["heat"], out["emb"]; lh = heat[H_LINE]
    H, W = lh.shape
    cinst = cv2.warpAffine(inst, M, (W, H), flags=cv2.INTER_NEAREST)
    pa = meta["plot_area"]; pac = apply(M, [[pa[0], pa[1]], [pa[2], pa[3]]])
    tol = max(1.5, 0.01 * (pac[1, 1] - pac[0, 1]))
    means, per = {}, {}
    for si, s in enumerate(meta["series"]):
        if s["kind"] not in LINE_KINDS: continue
        path = apply(M, s["path_px"])
        cx = np.arange(int(np.ceil(path[:, 0].min())), int(np.floor(path[:, 0].max())) + 1, dtype=float)
        cy = gt_curve(path, cx)
        ok = np.isfinite(cy) & (cy >= pac[0, 1]) & (cy <= pac[1, 1]) & (cx >= pac[0, 0]) & (cx <= pac[1, 0])
        cx, cy = cx[ok], cy[ok]
        if len(cx) < 3: continue
        xi = cx.astype(int).clip(0, W - 1); yi = np.round(cy).astype(int).clip(2, H - 3)
        win = np.stack([lh[yi + d, xi] for d in range(-2, 3)], 0); b = win.argmax(0)
        ridge_ok = win.max(0) > 0.25
        yr = yi + b - 2
        e = emb[:, yr, xi].T[ridge_ok]
        if len(e) < 5: continue
        mu = e.mean(0); means[si] = mu; per[si] = e
        spread.append(np.linalg.norm(e - mu, axis=1))
        adj.append(np.linalg.norm(np.diff(e, axis=0), axis=1))
        # oracle cluster: GT instance map dilated by 1 -> mask of this series' ridge pixels
        m = (cinst == si + 1)
        m = cv2.dilate(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
        mask = m & (lh > 0.25)
        chains = peel_chains(column_runs(mask, lh))
        hit = np.zeros(len(cx), bool)
        for ch in chains:
            cc = np.array([c for c, _, _, _ in ch], float); yy = np.array([y for _, y, _, _ in ch], float)
            if len(cc) < 2: continue
            y = np.interp(cx, cc, yy, left=np.nan, right=np.nan)
            i = np.clip(np.searchsorted(cc, cx), 1, len(cc) - 1); gap = cc[i] - cc[i - 1]
            hit |= np.isfinite(y) & (np.abs(y - cy) <= tol) & (gap <= 3)
        cov_oracle.append(hit.mean()); cov_oracle_n += 1
    for si, mu in means.items():
        others = [np.linalg.norm(mu - m2) for sj, m2 in means.items() if sj != si]
        if others: sep.append(min(others))
spread = np.concatenate(spread); adj = np.concatenate(adj)
print(f"within-series distance to mean: median {np.median(spread):.2f} p90 {np.quantile(spread,.9):.2f} p99 {np.quantile(spread,.99):.2f}  frac>1.5 {np.mean(spread>1.5):.3f}")
print(f"adjacent-column distance: median {np.median(adj):.2f} p90 {np.quantile(adj,.9):.2f} p99 {np.quantile(adj,.99):.2f} frac>1.0 {np.mean(adj>1.0):.3f}")
print(f"nearest other-series mean distance: median {np.median(sep):.2f} p10 {np.quantile(sep,.1):.2f} min {np.min(sep):.2f} frac<3 {np.mean(np.array(sep)<3):.3f}")
print(f"oracle-cluster chain coverage (metric tol): mean {np.mean(cov_oracle):.3f}  found(>0.5) {np.mean(np.array(cov_oracle)>0.5):.3f} n={cov_oracle_n}")
