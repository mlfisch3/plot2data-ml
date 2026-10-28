"""Stage attribution for lost line series: heat, embedding cluster, chains, merge/dedup, final.

    python teams/t2-trace/tools/diag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 60 [--ids 9000018,...]

For every GT line series: the fraction of its columns where (1) the line heat has a ridge within 2 px
of the truth, (2) that ridge pixel got an embedding cluster, and the purity of the dominant cluster,
(3) a chain (before merging) within 2 px, (4) a final series within 2 px, and which final series.
"""
from __future__ import annotations

import argparse, glob, json, math, os, sys
import numpy as np, cv2, torch
sys.path.insert(0, os.getcwd())
from p2d.data import H_LINE, H_MARKER, apply
from p2d.extract import (run_net, extract, inv_affine, plot_frame, peaks, cluster_embeddings, column_runs,
                         peel_chains, merge_fragments, drop_duplicates)
from p2d.evaluate import load_net
from p2d.metrics import gt_curve, LINE_KINDS
from p2d.synth.mpl_render import DATA


def stages(out, M, meta, img):
    heat, sem, emb = out["heat"], out["sem"], out["emb"]
    H, W = heat.shape[1:]
    lh = heat[H_LINE]
    frame = plot_frame(heat)
    if frame is not None:
        fx0, fy0, fx1, fy1 = frame
        roi = np.zeros((H, W), bool); roi[max(0, int(fy0) - 1): int(fy1) + 3, max(0, int(fx0) - 1): int(fx1) + 3] = True
    else:
        roi = np.ones((H, W), bool)
    ink = (lh > 0.25) & roi
    ys, xs = np.nonzero(ink); pts = np.column_stack([xs, ys])
    mpk = [p for p in peaks(heat[H_MARKER], 0.3, nms=2) if roi[int(round(p[1])), int(round(p[0]))]]
    mp = np.array([[int(round(p[0])), int(round(p[1]))] for p in mpk], np.int64).reshape(-1, 2)
    data_ink = (sem[DATA] > 0.5) & roi & ~ink
    dys, dxs = np.nonzero(data_ink)
    allpts = np.vstack([pts, np.column_stack([dxs, dys]), mp]) if len(mp) or len(dxs) else pts
    e = emb[:, allpts[:, 1], allpts[:, 0]].T
    w = np.concatenate([lh[ys, xs], 0.5 * sem[DATA][dys, dxs], np.ones(len(mp)) * 2.0])
    lab = cluster_embeddings(e, w, min_support=15)
    line_lab = lab[:len(pts)]
    labmap = np.full((H, W), -2, np.int32); labmap[pts[:, 1], pts[:, 0]] = line_lab
    frags = []
    for k in range(lab.max() + 1):
        sel = line_lab == k
        if sel.sum() < 15: continue
        mask = np.zeros((H, W), bool); mask[pts[sel, 1], pts[sel, 0]] = True
        for chain in peel_chains(column_runs(mask, lh)):
            cols = np.array([c for c, _, _, _ in chain], float); cy = np.array([y for _, y, _, _ in chain], float)
            yi = np.round(cy).astype(int).clip(0, H - 1)
            frags.append({"cols": cols, "ys": cy, "emb": emb[:, yi, cols.astype(int)].mean(1), "k": k,
                          "q": float(lh[yi, cols.astype(int)].mean()), "spans": [(a, b) for _, _, a, b in chain]})
    merged = merge_fragments([dict(f) for f in frags])
    final = drop_duplicates([dict(f) for f in merged], min_cols=max(12, int(0.04 * (frame[2] - frame[0])) if frame else 12))
    return dict(lh=lh, labmap=labmap, frags=frags, merged=merged, final=final, frame=frame, nclusters=int(lab.max() + 1))


def near_trace(cols_c, ys_c, traces, tol=2.0):
    """For each GT canvas column, is any trace within tol px? Returns the hit mask and the trace index hit."""
    hit = np.zeros(len(cols_c), bool); who = np.full(len(cols_c), -1)
    for ti, t in enumerate(traces):
        if len(t["cols"]) < 2: continue
        y = np.interp(cols_c, t["cols"], t["ys"], left=np.nan, right=np.nan)
        i = np.clip(np.searchsorted(t["cols"], cols_c), 1, len(t["cols"]) - 1)
        gap = t["cols"][i] - t["cols"][i - 1]
        ok = np.isfinite(y) & (np.abs(y - ys_c) <= tol) & (gap <= 3)
        who[ok & ~hit] = ti; hit |= ok
    return hit, who


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True); ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=60); ap.add_argument("--ids", default=None)
    ap.add_argument("--only-bad", action="store_true")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[:a.limit]
    ids = set(int(i) for i in a.ids.split(",")) if a.ids else None
    tot = {"gt": 0, "heat": 0.0, "clu": 0.0, "chain": 0.0, "merged": 0.0, "final": 0.0}
    for f in files:
        meta = json.load(open(f))
        if ids and meta["seed"] not in ids: continue
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        out, M = run_net(net, img)
        st = stages(out, M, meta, img)
        pa = meta["plot_area"]
        lines = []
        for si, s in enumerate(meta["series"]):
            if s["kind"] not in LINE_KINDS: continue
            path = apply(M, s["path_px"])
            cx = np.arange(int(np.ceil(path[:, 0].min())), int(np.floor(path[:, 0].max())) + 1, dtype=float)
            cy = gt_curve(path, cx)
            pac = apply(M, [[pa[0], pa[1]], [pa[2], pa[3]]])
            inside = np.isfinite(cy) & (cy >= pac[0, 1]) & (cy <= pac[1, 1]) & (cx >= pac[0, 0]) & (cx <= pac[1, 0])
            cx, cy = cx[inside], cy[inside]
            if len(cx) < 3: continue
            xi, yi = cx.astype(int), np.round(cy).astype(int)
            H, W = st["lh"].shape
            yi = yi.clip(2, H - 3); xi = xi.clip(0, W - 1)
            # heat ridge within 2 px
            win = np.stack([st["lh"][yi + d, xi] for d in range(-2, 3)], 0)
            heat_ok = win.max(0) > 0.25
            labs = np.stack([st["labmap"][yi + d, xi] for d in range(-2, 3)], 0)
            # cluster of the strongest heat pixel in the window
            best = win.argmax(0); lab_at = labs[best, np.arange(len(xi))]
            clu_ok = heat_ok & (lab_at >= 0)
            vals, cnts = np.unique(lab_at[clu_ok], return_counts=True) if clu_ok.any() else (np.array([]), np.array([]))
            dom = vals[cnts.argmax()] if len(vals) else -1
            purity = cnts.max() / cnts.sum() if len(vals) else 0.0
            ch_ok, _ = near_trace(cx, cy, st["frags"])
            mg_ok, _ = near_trace(cx, cy, st["merged"])
            fi_ok, who = near_trace(cx, cy, st["final"])
            whos = np.unique(who[who >= 0])
            lines.append((si, s["kind"], s["linestyle"], round(s["linewidth_px"], 1), s["color"], len(cx),
                          heat_ok.mean(), clu_ok.mean(), purity, len(vals), ch_ok.mean(), mg_ok.mean(), fi_ok.mean(), whos.tolist()))
            tot["gt"] += 1; tot["heat"] += heat_ok.mean(); tot["clu"] += clu_ok.mean(); tot["chain"] += ch_ok.mean()
            tot["merged"] += mg_ok.mean(); tot["final"] += fi_ok.mean()
        bad = [l for l in lines if l[12] < 0.9]
        if a.only_bad and not bad: continue
        print(f"== {meta['seed']} preset={meta['preset']} n_series={len(meta['series'])} clusters={st['nclusters']} "
              f"frags={len(st['frags'])} merged={len(st['merged'])} final={len(st['final'])} shared_colours="
              f"{len(meta['series']) - len(set(s['color'] for s in meta['series']))}")
        for l in lines:
            si, kind, ls, lw, col, n, h, c, p, nk, ch, mg, fi, whos = l
            flag = " <--" if fi < 0.9 else ""
            print(f"  s{si} {kind:13s} ls={ls:2s} lw={lw:4.1f} {col} cols={n:4d} | heat {h:.2f} clu {c:.2f} (pur {p:.2f}, {nk} cl) "
                  f"chain {ch:.2f} merged {mg:.2f} final {fi:.2f} -> {whos}{flag}")
    n = max(1, tot["gt"])
    print(f"TOTAL gt={tot['gt']} heat {tot['heat']/n:.3f} clu {tot['clu']/n:.3f} chain {tot['chain']/n:.3f} merged {tot['merged']/n:.3f} final {tot['final']/n:.3f}")


if __name__ == "__main__":
    main()
