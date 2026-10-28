"""Collect per-column, per-peak, per-tick and per-frame facts for the precision diagnosis.

    python teams/t3-precision/scripts/diag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --out out/t3/diag-base.pkl

Everything is in source pixels. For each chart the network runs once; the
extraction is scored raw (canvas ridge mapped back) and refined (refine_lines,
refine_markers, and refine_ticks on a copy), so each record carries both.
Summaries are made by diag_report.py from the pickle.
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

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

# P2D_ROOT selects which tree's p2d is imported: the frozen baseline worktree for "before" numbers,
# this worktree (the default) for "after" numbers.
ML = os.environ.get("P2D_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, ML)

from p2d.data import H_CORNER, H_VERTEX, apply, turning_vertices  # noqa: E402
from p2d.extract import extract, inv_affine, peaks, refine_lines, refine_markers, refine_ticks, run_net  # noqa: E402
from p2d.metrics import LINE_KINDS, gt_curve, peak_vertices, pred_curve  # noqa: E402
from p2d.synth.mpl_render import AXIS, DATA, GRID  # noqa: E402


def match_lines(G: list[np.ndarray], P: list[np.ndarray], ph: float) -> dict[int, int]:
    """The same assignment metrics.score makes."""
    if not G or not P:
        return {}
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
    return {i: j for i, j in zip(gi, pj) if C[i, j] < 0.2}


def slope_at(path: np.ndarray, xs: np.ndarray) -> np.ndarray:
    """dy/dx of the polyline (px per px) at each column, from a half-pixel difference."""
    o = np.argsort(path[:, 0], kind="stable")
    px, py = path[o, 0], path[o, 1]
    y1 = np.interp(xs + 0.5, px, py, left=np.nan, right=np.nan)
    y0 = np.interp(xs - 0.5, px, py, left=np.nan, right=np.nan)
    return y1 - y0


def class_dist(sem: np.ndarray, cls: int, xs: np.ndarray, ys: np.ndarray, reach: int = 12) -> np.ndarray:
    """Vertical distance from (x, y) to the nearest pixel of class `cls` in that column, within `reach`."""
    H, W = sem.shape
    out = np.full(len(xs), np.inf)
    for k, (x, y) in enumerate(zip(xs, ys)):
        if not np.isfinite(y):
            continue
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < W):
            continue
        a, b = max(0, yi - reach), min(H, yi + reach + 1)
        rows = np.nonzero(sem[a:b, xi] == cls)[0]
        if len(rows):
            out[k] = np.min(np.abs(rows + a - y))
    return out


def ink_run(sem: np.ndarray, inst: np.ndarray, sid: int, xs: np.ndarray, ys: np.ndarray, reach: int = 12):
    """Height of this series' own ink run through (x, y): the drawn thickness at that column."""
    H, W = sem.shape
    out = np.full(len(xs), np.nan)
    for k, (x, y) in enumerate(zip(xs, ys)):
        if not np.isfinite(y):
            continue
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= xi < W and 0 <= yi < H):
            continue
        col = (inst[:, xi] == sid)
        if not col[yi]:
            # nearest own pixel within reach
            a, b = max(0, yi - reach), min(H, yi + reach + 1)
            rows = np.nonzero(col[a:b])[0]
            if not len(rows):
                continue
            yi = a + rows[np.argmin(np.abs(rows + a - y))]
        lo = hi = yi
        while lo > 0 and col[lo - 1]:
            lo -= 1
        while hi < H - 1 and col[hi + 1]:
            hi += 1
        out[k] = hi - lo + 1
    return out


def peak_shape(path: np.ndarray, v: np.ndarray, ph: float):
    """Angle at a peak vertex, and its widths (columns) at half prominence and at 2 px below the tip."""
    o = np.argsort(path[:, 0], kind="stable")
    px, py = path[o, 0], path[o, 1]
    i = int(np.argmin(np.abs(px - v[0]) + np.abs(py - v[1])))
    ang = np.nan
    if 0 < i < len(px) - 1:
        a = path[o][i] - path[o][i - 1]
        b = path[o][i + 1] - path[o][i]
        la, lb = np.hypot(*a), np.hypot(*b)
        if la > 0 and lb > 0:
            ang = math.degrees(math.acos(float(np.clip((a @ b) / (la * lb), -1, 1))))
    # Width at a depth below the tip: walk the polyline either side on a fine grid.
    g = np.arange(max(px[0], v[0] - 60), min(px[-1], v[0] + 60) + 1e-9, 0.1)
    gy = np.interp(g, px, py)
    tip = v[1]
    sign = 1.0 if (i > 0 and py[i] < py[i - 1]) or (i < len(py) - 1 and py[i] < py[i + 1]) else -1.0
    # sign = +1 for a maximum (tip is the smallest y), -1 for a minimum
    depth = (gy - tip) * sign  # >= 0 going away from the tip into the body

    def width_at(d: float) -> float:
        c = int(np.argmin(np.abs(g - v[0])))
        l = c
        while l > 0 and depth[l - 1] < d:
            l -= 1
        r = c
        while r < len(g) - 1 and depth[r + 1] < d:
            r += 1
        return (r - l) * 0.1

    prom = 0.05 * ph
    return ang, sign, width_at(0.5 * prom), width_at(2.0), width_at(1.0)


def edge_visibility(sem: np.ndarray, pa: list[float]) -> list[float]:
    """Fraction of each plot edge (left, top, right, bottom) drawn as an AXIS-class spine."""
    H, W = sem.shape
    x0, y0, x1, y1 = [int(round(v)) for v in pa]
    out = []
    for edge in ("left", "top", "right", "bottom"):
        if edge in ("left", "right"):
            x = x0 if edge == "left" else x1
            a, b = max(0, x - 1), min(W, x + 2)
            seg = sem[max(0, y0):min(H, y1 + 1), a:b]
            frac = float((seg == AXIS).any(1).mean()) if seg.size else 0.0
        else:
            y = y0 if edge == "top" else y1
            a, b = max(0, y - 1), min(H, y + 2)
            seg = sem[a:b, max(0, x0):min(W, x1 + 1)]
            frac = float((seg == AXIS).any(0).mean()) if seg.size else 0.0
        out.append(frac)
    return out


def tick_context(sem: np.ndarray, t: dict, axis: str, pa: list[float]) -> dict:
    """What is drawn at a tick: a mark outside/inside the axis, a gridline across the plot."""
    H, W = sem.shape
    ax, ay = t["anchor"]
    xi, yi = int(round(ax)), int(round(ay))
    out = {}
    if axis == "x":
        low = t["side"] == "low"  # labels below: anchor on the bottom edge
        o = range(yi + 1, yi + 9) if low else range(yi - 8, yi)
        i = range(yi - 8, yi) if low else range(yi + 1, yi + 9)
        cols = slice(max(0, xi - 1), min(W, xi + 2))
        out["mark_out"] = int(sum(1 for y in o if 0 <= y < H and (sem[y, cols] == AXIS).any()))
        out["mark_in"] = int(sum(1 for y in i if 0 <= y < H and (sem[y, cols] == AXIS).any()))
        ys = np.arange(int(pa[1]) + 2, int(pa[3]) - 1)
        ys = ys[(ys >= 0) & (ys < H)]
        out["grid"] = float((sem[ys][:, cols] == GRID).any(1).mean()) if len(ys) else 0.0
    else:
        low = t["side"] == "low"  # labels left: anchor on the left edge
        o = range(xi - 8, xi) if low else range(xi + 1, xi + 9)
        i = range(xi + 1, xi + 9) if low else range(xi - 8, xi)
        rows = slice(max(0, yi - 1), min(H, yi + 2))
        out["mark_out"] = int(sum(1 for x in o if 0 <= x < W and (sem[rows, x] == AXIS).any()))
        out["mark_in"] = int(sum(1 for x in i if 0 <= x < W and (sem[rows, x] == AXIS).any()))
        xs = np.arange(int(pa[0]) + 2, int(pa[2]) - 1)
        xs = xs[(xs >= 0) & (xs < W)]
        out["grid"] = float((sem[rows][:, xs] == GRID).any(0).mean()) if len(xs) else 0.0
    b = t["bbox"]
    out["label_off"] = float(((b[0] + b[2]) / 2 - ax) if axis == "x" else ((b[1] + b[3]) / 2 - ay))
    out["label_h"] = float(b[3] - b[1])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-refine-ticks", action="store_true")
    a = ap.parse_args()
    from p2d.evaluate import load_net

    net = load_net(a.ckpt)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    charts = []
    for f in files:
        meta = json.load(open(f))
        stem = f[:-5]
        img = cv2.imread(stem + ".png")[..., ::-1].copy()
        sem = cv2.imread(stem + ".sem.png", cv2.IMREAD_UNCHANGED)
        inst = cv2.imread(stem + ".inst.png", cv2.IMREAD_UNCHANGED)
        pa = meta["plot_area"]
        ph, pw = pa[3] - pa[1], pa[2] - pa[0]
        out, M = run_net(net, img)
        s = math.hypot(M[0, 0], M[1, 0])
        Mi = inv_affine(M)
        ex_raw = extract(out, M, img)
        ex_ref = refine_markers(img, refine_lines(img, copy.deepcopy(ex_raw)))
        ex_tick = ex_ref if a.no_refine_ticks else refine_ticks(img, copy.deepcopy(ex_ref))
        rec = {"id": meta["seed"], "file": stem, "generator": meta.get("generator"), "preset": meta.get("preset"),
               "style": meta.get("style"), "w": meta["width"], "h": meta["height"], "scale": s, "ph": ph, "pw": pw,
               "n_series": len(meta["series"]), "xscale": meta["xscale"], "yscale": meta["yscale"],
               "density": max([len(sr["x"]) / max(pw, 1) for sr in meta["series"] if sr["kind"] in LINE_KINDS] or [0.0]),
               "probe": meta.get("probe")}

        # ---- frame ----
        rec["edge_vis"] = edge_visibility(sem, pa)
        cpk = peaks(out["heat"][H_CORNER], 0.25, nms=5)
        rec["corner_peaks"] = [(float(apply(Mi, [[x, y]])[0][0]), float(apply(Mi, [[x, y]])[0][1]), float(v)) for x, y, v in cpk[:12]]
        rec["frame_pred"] = ex_raw.plot_area
        rec["frame_err"] = [float(p - g) for p, g in zip(ex_raw.plot_area, pa)] if ex_raw.plot_area else None

        # ---- ticks ----
        tol = max(3.0, 2.5 / s)
        ticks = []
        for key, axis in (("xticks", "x"), ("yticks", "y")):
            gt = meta[key]
            pr_raw = getattr(ex_raw, key)
            pr_snap = getattr(ex_tick, key)
            used = set()
            for t in gt:
                best, bd = None, 1e9
                for j, p in enumerate(pr_raw):
                    d = np.hypot(p["anchor"][0] - t["anchor"][0], p["anchor"][1] - t["anchor"][1])
                    if d < bd and j not in used:
                        best, bd = j, d
                row = {"axis": axis, "side": t["side"], "gt": t["pos"], "found": best is not None and bd <= tol}
                row.update(tick_context(sem, t, axis, pa))
                if row["found"]:
                    used.add(best)
                    row["raw"] = pr_raw[best]["pos"]
                    row["snap"] = pr_snap[best]["pos"]
                    row["snapped"] = "pos_net" in pr_snap[best]
                    row["score"] = pr_raw[best]["score"]
                ticks.append(row)
        rec["ticks"] = ticks
        rec["tick_fp"] = {k: len(getattr(ex_raw, k)) - sum(1 for t in ticks if t["axis"] == k[0] and t["found"]) for k in ("xticks", "yticks")}

        # ---- lines ----
        xs = np.arange(int(np.ceil(pa[0])), int(np.floor(pa[2])) + 1, dtype=float)
        gts = [(k, sr) for k, sr in enumerate(meta["series"]) if sr["kind"] in LINE_KINDS]
        G = []
        for _, sr in gts:
            y = gt_curve(np.array(sr["path_px"]), xs)
            y[(y < pa[1]) | (y > pa[3])] = np.nan
            G.append(y)
        preds_raw = [se for se in ex_raw.series if se.kind == "line"]
        preds_ref = [se for se in ex_ref.series if se.kind == "line"]
        max_gap = 3.0 / s
        P_ref = [pred_curve(se.line_px, xs, max_gap) for se in preds_ref]
        P_raw = [pred_curve(se.line_px, xs, max_gap) for se in preds_raw]
        matched = match_lines(G, P_ref, ph)
        lines = []
        vpk = peaks(out["heat"][H_VERTEX], 0.3, nms=2)
        vsrc = apply(Mi, [[x, y] for x, y, _ in vpk]) if vpk else np.zeros((0, 2))
        vh = out["heat"][H_VERTEX]
        for i, (k, sr) in enumerate(gts):
            g = G[i]
            row = {"k": k, "kind": sr["kind"], "lw": sr["linewidth_px"], "ls": sr["linestyle"], "color": sr["color"],
                   "n_pts": len(sr["x"]), "cov": 0.0, "matched": i in matched}
            if i not in matched:
                lines.append(row)
                continue
            j = matched[i]
            p_ref, p_raw = P_ref[j], P_raw[j]
            both = ~np.isnan(g) & ~np.isnan(p_ref)
            row["cov"] = float(both.sum() / max(1, (~np.isnan(g)).sum()))
            path = np.array(sr["path_px"])
            sl = slope_at(path, xs)
            other = np.full(len(xs), np.inf)
            for i2, g2 in enumerate(G):
                if i2 != i:
                    other = np.minimum(other, np.abs(g2 - g))
            vt = turning_vertices(path)
            dvert = np.min(np.abs(xs[:, None] - vt[None, :, 0]), axis=1) if len(vt) else np.full(len(xs), np.inf)
            # columns kept from the net by refine: where refined == raw-mapped sample
            cols = {
                "x": xs[both], "gt": g[both], "ref": p_ref[both], "raw": p_raw[both] if len(p_raw) else np.full(both.sum(), np.nan),
                "slope": sl[both], "other": other[both], "dvert": dvert[both],
                "grid": class_dist(sem, GRID, xs[both], g[both]), "axis": class_dist(sem, AXIS, xs[both], g[both]),
                "ink": ink_run(sem, inst, k + 1, xs[both], g[both]),
            }
            row["cols"] = {kk: np.asarray(v, np.float32) for kk, v in cols.items()}
            # peaks
            pv = peak_vertices(path, min_prom=0.05 * ph)
            pv = pv[(pv[:, 0] >= pa[0]) & (pv[:, 0] <= pa[2]) & (pv[:, 1] >= pa[1]) & (pv[:, 1] <= pa[3])]
            pk = []
            if len(pv):
                yr = pred_curve(preds_ref[j].line_px, pv[:, 0], max_gap)
                yw = pred_curve(preds_raw[j].line_px, pv[:, 0], max_gap) if len(preds_raw) > j else np.full(len(pv), np.nan)
                for q, v in enumerate(pv):
                    ang, sign, w_half, w_2px, w_1px = peak_shape(path, v, ph)
                    c = apply(M, [v])[0]
                    ix, iy = int(round(c[0])), int(round(c[1]))
                    hv = float(vh[max(0, iy - 1):iy + 2, max(0, ix - 1):ix + 2].max()) if 0 <= iy < vh.shape[0] and 0 <= ix < vh.shape[1] else 0.0
                    dv = float(np.min(np.hypot(vsrc[:, 0] - v[0], vsrc[:, 1] - v[1]))) if len(vsrc) else np.inf
                    pk.append({"x": float(v[0]), "y": float(v[1]), "sign": sign, "angle": ang, "w_half": w_half, "w_2px": w_2px,
                               "w_1px": w_1px, "ref": float(yr[q]), "raw": float(yw[q]), "vheat": hv, "dvert": dv,
                               "ink": float(ink_run(sem, inst, k + 1, np.array([v[0]]), np.array([v[1]]))[0])})
            row["peaks"] = pk
            lines.append(row)
        rec["lines"] = lines
        rec["n_line_pred"] = len(preds_ref)
        charts.append(rec)
        if len(charts) % 20 == 0:
            print(f"{len(charts)}/{len(files)}", flush=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "wb") as fh:
        pickle.dump(charts, fh)
    print("wrote", a.out, len(charts))


if __name__ == "__main__":
    main()
