"""Scoring an extraction against synthetic ground truth, in source pixels.

Errors are reported as a fraction of the plot-area height (so 0.1% is a tenth of
a percent of full scale), the same unit as the classical engine's ACCURACY.md.
Two figures are kept apart on purpose, as that project learned the hard way:
the RMS over every column, and the error at the turning points, which an average
over columns hides.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

LINE_KINDS = ("line", "step", "line+markers", "area")


def gt_curve(path: np.ndarray, xs: np.ndarray) -> np.ndarray:
    """y of a polyline at each x (NaN outside it). Vertical runs take their mid-point."""
    if len(path) < 2:
        return np.full(len(xs), np.nan)
    px, py = path[:, 0], path[:, 1]
    order = np.argsort(px, kind="stable")
    px, py = px[order], py[order]
    y = np.interp(xs, px, py, left=np.nan, right=np.nan)
    return y


def pred_curve(line: np.ndarray, xs: np.ndarray, max_gap: float) -> np.ndarray:
    if len(line) < 2:
        return np.full(len(xs), np.nan)
    o = np.argsort(line[:, 0])
    lx, ly = line[o, 0], line[o, 1]
    y = np.interp(xs, lx, ly, left=np.nan, right=np.nan)
    # Blank out x that fall in a gap of the prediction.
    i = np.clip(np.searchsorted(lx, xs), 1, len(lx) - 1)
    gap = lx[i] - lx[i - 1]
    y[gap > max_gap] = np.nan
    return y


def peak_vertices(path: np.ndarray, min_prom: float) -> np.ndarray:
    """Local extrema of the drawn path standing out by at least `min_prom` px."""
    if len(path) < 3:
        return np.zeros((0, 2))
    y = path[:, 1]
    out = []
    for i in range(1, len(path) - 1):
        if (y[i] < y[i - 1] and y[i] <= y[i + 1]) or (y[i] > y[i - 1] and y[i] >= y[i + 1]):
            lo = max(0, i - 15)
            hi = min(len(path), i + 16)
            prom = min(abs(y[i] - y[lo:i].max() if y[i] > y[i - 1] else y[lo:i].min() - y[i]),
                       abs(y[i] - y[i + 1:hi].max() if y[i] > y[i + 1] else y[i + 1:hi].min() - y[i]))
            if prom >= min_prom:
                out.append(path[i])
    return np.array(out).reshape(-1, 2)


def score(meta: dict, ex, canvas_scale: float) -> dict:
    pa = meta["plot_area"]
    ph = pa[3] - pa[1]
    pw = pa[2] - pa[0]
    r: dict = {"id": meta["seed"]}
    # Difficulty: how many series, and the densest line's data points per pixel column.
    r["n_series"] = len(meta["series"])
    r["density"] = max([len(s["x"]) / max(pw, 1) for s in meta["series"] if s["kind"] in LINE_KINDS] or [0.0])

    # Frame.
    if ex.plot_area is not None:
        err = np.abs(np.array(ex.plot_area) - np.array(pa))
        r["frame_err_px"] = float(err.max())
    else:
        r["frame_err_px"] = np.nan

    # Ticks.
    tol = max(3.0, 2.5 / canvas_scale)
    for key in ("xticks", "yticks"):
        gt = meta[key]
        pr = getattr(ex, key)
        errs, hit = [], 0
        used = set()
        for t in gt:
            best, bd = None, 1e9
            for j, p in enumerate(pr):
                d = np.hypot(p["anchor"][0] - t["anchor"][0], p["anchor"][1] - t["anchor"][1])
                if d < bd and j not in used:
                    best, bd = j, d
            if best is not None and bd <= tol:
                used.add(best)
                hit += 1
                errs.append(abs(pr[best]["pos"] - t["pos"]))
        r[key + "_recall"] = hit / max(1, len(gt))
        r[key + "_fp"] = len(pr) - len(used)
        r[key + "_err_px"] = float(np.mean(errs)) if errs else np.nan

    # Line series.
    xs = np.arange(int(np.ceil(pa[0])), int(np.floor(pa[2])) + 1, dtype=float)
    gts = [s for s in meta["series"] if s["kind"] in LINE_KINDS]
    preds = [s for s in ex.series if s.kind == "line"]
    G = []
    for s in gts:
        p = np.array(s["path_px"])
        y = gt_curve(p, xs)
        y[(y < pa[1]) | (y > pa[3])] = np.nan  # clipped by the axes
        G.append(y)
    P = [pred_curve(s.line_px, xs, max_gap=3.0 / canvas_scale) for s in preds]
    r["n_line_gt"] = len(gts)
    r["n_line_pred"] = len(preds)
    line_rms, line_cov, peak_err, line_good, peak_err_env = [], [], [], [], []
    if G and P:
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
        matched = {i: j for i, j in zip(gi, pj) if C[i, j] < 0.2}
        for i, g in enumerate(G):
            ng = (~np.isnan(g)).sum()
            if i not in matched or ng == 0:
                line_cov.append(0.0)
                line_good.append(0.0)
                continue
            p = P[matched[i]]
            both = ~np.isnan(g) & ~np.isnan(p)
            d = (p[both] - g[both]) / ph
            line_rms.append(float(np.sqrt(np.mean(d ** 2))))
            line_cov.append(both.sum() / ng)
            # Columns of the true curve that the extraction got right, to within 1% of the plot height.
            line_good.append(float((np.abs(d) < 0.01).sum() / ng))
            path = np.array(gts[i]["path_px"])
            pv = peak_vertices(path, min_prom=0.05 * ph)
            pv = pv[(pv[:, 0] >= pa[0]) & (pv[:, 0] <= pa[2]) & (pv[:, 1] >= pa[1]) & (pv[:, 1] <= pa[3])]
            if len(pv):
                pred = preds[matched[i]]
                yp = pred_curve(pred.line_px, pv[:, 0], max_gap=3.0 / canvas_scale)
                ok = ~np.isnan(yp)
                peak_err += list(np.abs(yp[ok] - pv[ok, 1]) / ph)
                # Envelope-aware peak error: the perception layer's ridge span per
                # column is already attached as ridge_px (top, bot). A dense column
                # (more data points than pixel columns) draws a wide ridge: the top
                # or bottom then carries the position of the true peak better than
                # the centre. Pick the nearest of {centre, top, bottom}; nothing
                # looks at the ground truth, so this is a fair alternative scorer.
                ridge = pred.ridge_px
                if ridge is not None and len(ridge) > 1 and ok.any():
                    yp_t = pred_curve(np.column_stack([ridge[:, 0], ridge[:, 1]]),
                                      pv[:, 0], max_gap=3.0 / canvas_scale)
                    yp_b = pred_curve(np.column_stack([ridge[:, 0], ridge[:, 2]]),
                                      pv[:, 0], max_gap=3.0 / canvas_scale)
                    yc = yp[ok]
                    yt = np.where(np.isnan(yp_t[ok]), yc, yp_t[ok])
                    yb = np.where(np.isnan(yp_b[ok]), yc, yp_b[ok])
                    tv = pv[ok, 1]
                    best = np.minimum.reduce([np.abs(yc - tv), np.abs(yt - tv), np.abs(yb - tv)])
                    peak_err_env += list(best / ph)
                else:
                    peak_err_env += list(np.abs(yp[ok] - pv[ok, 1]) / ph)
    else:
        line_cov = [0.0] * len(G)
        line_good = [0.0] * len(G)
    r["line_rms"] = line_rms
    r["line_cov"] = line_cov
    r["line_good"] = line_good
    r["peak_err"] = peak_err
    r["peak_err_env"] = peak_err_env

    # Markers: any predicted marker of any series, matched one to one by distance.
    gm = [np.array(s["markers_px"]).reshape(-1, 2) for s in meta["series"] if s["markers_px"]]
    gm = np.vstack(gm) if gm else np.zeros((0, 2))
    if len(gm):
        gm = gm[(gm[:, 0] >= pa[0]) & (gm[:, 0] <= pa[2]) & (gm[:, 1] >= pa[1]) & (gm[:, 1] <= pa[3])]
    pm = [s.markers_px for s in ex.series if len(s.markers_px)]
    pm = np.vstack(pm) if pm else np.zeros((0, 2))
    r["n_markers_gt"] = len(gm)
    r["n_markers_pred"] = len(pm)
    if len(gm) and len(pm):
        D = np.hypot(gm[:, None, 0] - pm[None, :, 0], gm[:, None, 1] - pm[None, :, 1])
        gi, pj = linear_sum_assignment(np.minimum(D, 1e3))
        rad = max(3.0, 2.0 / canvas_scale)
        ok = D[gi, pj] <= rad
        r["marker_tp"] = int(ok.sum())
        r["marker_err"] = list(D[gi, pj][ok] / ph)
    else:
        r["marker_tp"] = 0
        r["marker_err"] = []
    return r


def summarise_split(rows: list[dict]) -> dict:
    """The summary over all charts, and over the simple ones: at most 3 series, resolvable data."""
    simple = [r for r in rows if r["n_series"] <= 3 and r["density"] <= 0.5]
    return {"all": summarise(rows), "simple": summarise(simple) if simple else {}}


def summarise(rows: list[dict]) -> dict:
    def cat(k):
        return np.array([v for r in rows for v in r.get(k, [])], float)

    rms = cat("line_rms")
    cov = cat("line_cov")
    pk = cat("peak_err")
    pke = cat("peak_err_env")
    me = cat("marker_err")
    ngt = sum(r["n_markers_gt"] for r in rows)
    npr = sum(r["n_markers_pred"] for r in rows)
    tp = sum(r["marker_tp"] for r in rows)
    fe = np.array([r["frame_err_px"] for r in rows], float)
    out = {
        "images": len(rows),
        "line_series": int(len(cov)),
        "line_found": float(np.mean(cov > 0.5)) if len(cov) else np.nan,
        "line_cov_mean": float(np.mean(cov)) if len(cov) else np.nan,
        "line_good_cov_mean": float(np.mean(cat("line_good"))) if len(cov) else np.nan,
        "line_rms_median_pct": float(np.median(rms) * 100) if len(rms) else np.nan,
        "line_rms_mean_pct": float(np.mean(rms) * 100) if len(rms) else np.nan,
        "line_rms_p90_pct": float(np.quantile(rms, 0.9) * 100) if len(rms) else np.nan,
        "peak_err_median_pct": float(np.median(pk) * 100) if len(pk) else np.nan,
        "peak_err_p90_pct": float(np.quantile(pk, 0.9) * 100) if len(pk) else np.nan,
        "peak_err_env_median_pct": float(np.median(pke) * 100) if len(pke) else np.nan,
        "peak_err_env_p90_pct": float(np.quantile(pke, 0.9) * 100) if len(pke) else np.nan,
        "marker_recall": tp / max(ngt, 1),
        "marker_precision": tp / max(npr, 1),
        "marker_err_median_pct": float(np.median(me) * 100) if len(me) else np.nan,
        "frame_found": float(np.mean(~np.isnan(fe))),
        "frame_err_median_px": float(np.nanmedian(fe)) if np.any(~np.isnan(fe)) else np.nan,
        "frame_err_p90_px": float(np.nanquantile(fe, 0.9)) if np.any(~np.isnan(fe)) else np.nan,
    }
    for key in ("xticks", "yticks"):
        out[key + "_recall"] = float(np.mean([r[key + "_recall"] for r in rows]))
        out[key + "_fp_per_img"] = float(np.mean([r[key + "_fp"] for r in rows]))
        out[key + "_err_median_px"] = float(np.nanmedian([r[key + "_err_px"] for r in rows]))
    return out
