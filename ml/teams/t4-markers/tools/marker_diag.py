"""Per-marker diagnosis of a checkpoint on a synthetic set: every missed and every spurious marker, by cause.

    python teams/t4-markers/tools/marker_diag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --out out/t4/diag-val

Uses the exact ground truth (marker centres, the per-pixel class and instance maps) and the raw marker
heat to say, for each true marker that was not returned, at which stage it was lost:

    no_heat      the network put no heat (max < marker_thr) within the tolerance of the true centre
    no_peak      heat is there but no raw peak survives within tolerance (merged by the NMS with a stronger
                 neighbour, or a plateau)
    peak_off     the nearest raw peak is beyond tolerance but within twice of it (shifted / merged)
    unlabelled   a raw peak within tolerance, but its embedding label was -1 (dropped by extract)
    dropped      a raw peak within tolerance with a label, but it never reached the output (singleton cluster
                 or lost on the way)
    moved        it reached the output but ended beyond tolerance (refine_markers or the sub-pixel fit)
    taken        a returned marker lies within tolerance but the one-to-one matching gave it to another truth

and for each returned marker that matched nothing, what ink is under it (from the GT class map):

    text / tick_label / legend_symbol / axis / grid    not data at all
    line_ink      ink of a line series without markers (a vertex, a crossing, a dash end)
    dup           within twice the tolerance of a true marker that was matched (a split peak)
    marker_ink    on the ink of a marker series but not near any marker centre (a big marker's rim)
    bg            nothing drawn there

Writes <out>/summary.json, <out>/rows.json, overlays of the worst charts and contact sheets per cause.
"""

from __future__ import annotations

import argparse
import collections
import glob
import json
import math
import os
import sys

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment

# The p2d package to diagnose: this worktree's by default, or the frozen baseline tree through P2D_ROOT.
sys.path.insert(0, os.environ.get("P2D_ROOT") or os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d import extract as E  # noqa: E402
from p2d.data import H_MARKER, apply  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.synth.mpl_render import CLASS_NAMES, DATA  # noqa: E402

MARKER_THR = 0.3


def _capture_cluster():
    """Wrap extract.cluster_embeddings so the labels it returned are visible afterwards."""
    store = {}
    orig = E.cluster_embeddings

    def wrapped(*a, **k):
        lab = orig(*a, **k)
        store["lab"] = lab
        return lab

    E.cluster_embeddings = wrapped
    return store


def raw_peaks(out, M, frame_canvas):
    heat = out["heat"]
    H, W = heat.shape[1:]
    if frame_canvas is not None:
        fx0, fy0, fx1, fy1 = frame_canvas
        roi = np.zeros((H, W), bool)
        roi[max(0, int(fy0) - 1): int(fy1) + 3, max(0, int(fx0) - 1): int(fx1) + 3] = True
    else:
        roi = np.ones((H, W), bool)
    mpk = [p for p in E.peaks(heat[H_MARKER], MARKER_THR, nms=2) if roi[int(round(p[1])), int(round(p[0]))]]
    return mpk, roi


def analyse(meta, img, sem_gt, inst_gt, out, M, ex, lab_store):
    pa = meta["plot_area"]
    ph = pa[3] - pa[1]
    s = math.hypot(M[0, 0], M[1, 0])
    Mi = E.inv_affine(M)
    rad = max(3.0, 2.0 / s)
    mh = out["heat"][H_MARKER]
    Hc, Wc = mh.shape

    # Ground-truth markers with attributes.
    gm, gattr = [], []
    series_kind = {}
    for si, sr in enumerate(meta["series"]):
        series_kind[si] = sr["kind"]
        if not sr["markers_px"]:
            continue
        for x, y in sr["markers_px"]:
            if pa[0] <= x <= pa[2] and pa[1] <= y <= pa[3]:
                gm.append((x, y))
                gattr.append(dict(series=si, kind=sr["kind"], shape=sr["marker"], size_px=sr["markersize_px"],
                                  color=sr["color"]))
    gm = np.array(gm, float).reshape(-1, 2)
    # Nearest other true marker (any series), in source px.
    if len(gm) > 1:
        D = np.hypot(gm[:, None, 0] - gm[None, :, 0], gm[:, None, 1] - gm[None, :, 1])
        np.fill_diagonal(D, np.inf)
        nn = D.min(1)
    else:
        nn = np.full(len(gm), np.inf)

    # Predicted markers, with the series they came in.
    pm, pattr = [], []
    for pi, se in enumerate(ex.series):
        for x, y in se.markers_px:
            pm.append((x, y))
            pattr.append(dict(pred_series=pi, pred_kind=se.kind))
    pm = np.array(pm, float).reshape(-1, 2)

    matched_g = np.full(len(gm), -1)
    matched_p = np.full(len(pm), -1)
    tp_capped = 0
    if len(gm) and len(pm):
        D = np.hypot(gm[:, None, 0] - pm[None, :, 0], gm[:, None, 1] - pm[None, :, 1])
        gi, pj = linear_sum_assignment(np.minimum(D, 1e3))
        for i, j in zip(gi, pj):
            if D[i, j] <= rad:
                matched_g[i] = j
                matched_p[j] = i
        # The same matching with the cost capped at the tolerance: it then maximises the number of pairs
        # within tolerance instead of minimising the summed distance (which can trade a hit for two misses).
        gi2, pj2 = linear_sum_assignment(np.minimum(D, rad * 1.001))
        tp_capped = int((D[gi2, pj2] <= rad).sum())
    # The centre matplotlib actually drew: Agg stamps markers at integer pixel positions, so the drawn
    # centre is round(display) = floor(recorded + 1) in each axis (verified on isolated markers to 0.05 px).
    # A set that records it (`markers_drawn_px`, probe_t4) is believed as it is.
    if any("markers_drawn_px" in sr for sr in meta["series"]):
        gd = [np.array(sr["markers_drawn_px"]).reshape(-1, 2) for sr in meta["series"] if sr["markers_px"]]
        ga = [np.array(sr["markers_px"]).reshape(-1, 2) for sr in meta["series"] if sr["markers_px"]]
        gd = np.vstack(gd) if gd else np.zeros((0, 2))
        ga = np.vstack(ga) if ga else np.zeros((0, 2))
        inside = (ga[:, 0] >= pa[0]) & (ga[:, 0] <= pa[2]) & (ga[:, 1] >= pa[1]) & (ga[:, 1] <= pa[3])
        gm_drawn = gd[inside]
    elif meta.get("generator") == "matplotlib":
        gm_drawn = np.floor(gm + 1.0)
    else:
        gm_drawn = gm

    # Raw peaks and their embedding labels, in source px.
    frame_canvas = apply(M, [[ex.plot_area[0], ex.plot_area[1]], [ex.plot_area[2], ex.plot_area[3]]]).reshape(-1).tolist() if ex.plot_area else None
    mpk, roi = raw_peaks(out, M, frame_canvas)
    rp = np.array([[p[0], p[1]] for p in mpk], float).reshape(-1, 2)
    rp_src = apply(Mi, rp) if len(rp) else np.zeros((0, 2))
    lab = lab_store.get("lab")
    mk_lab = lab[-len(mpk):] if (lab is not None and len(mpk)) else np.zeros(0, int)

    def heat_max_at(x, y, r=3):
        cx, cy = apply(M, [[x, y]])[0]
        ix, iy = int(round(cx)), int(round(cy))
        x0, x1 = max(0, ix - r), min(Wc, ix + r + 1)
        y0, y1 = max(0, iy - r), min(Hc, iy + r + 1)
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return float(mh[y0:y1, x0:x1].max())

    def sem_at(x, y, r=1):
        ix, iy = int(round(x)), int(round(y))
        H, W = sem_gt.shape
        x0, x1 = max(0, ix - r), min(W, ix + r + 1)
        y0, y1 = max(0, iy - r), min(H, iy + r + 1)
        patch = sem_gt[y0:y1, x0:x1].reshape(-1)
        ipatch = inst_gt[y0:y1, x0:x1].reshape(-1)
        nz = patch[patch > 0]
        if len(nz) == 0:
            return "bg", -1
        cls = int(np.bincount(nz).argmax())
        inst = int(np.bincount(ipatch[ipatch > 0]).argmax()) - 1 if (ipatch > 0).any() else -1
        return CLASS_NAMES[cls], inst

    rows_g = []
    for i, (x, y) in enumerate(gm):
        a = dict(gattr[i])
        a.update(x=float(x), y=float(y), nn_px=float(nn[i]), nn_rel=float(nn[i] / max(gattr[i]["size_px"], 1e-6)))
        a["heat_max"] = heat_max_at(x, y, r=int(math.ceil(rad * s)))
        d_peak = float(np.hypot(rp_src[:, 0] - x, rp_src[:, 1] - y).min()) if len(rp_src) else np.inf
        a["d_peak_px"] = d_peak
        d_final = float(np.hypot(pm[:, 0] - x, pm[:, 1] - y).min()) if len(pm) else np.inf
        a["d_final_px"] = d_final
        if matched_g[i] >= 0:
            a["stage"] = "ok"
            a["err_pct"] = float(np.hypot(*(pm[matched_g[i]] - gm[i])) / ph * 100)
            a["err_drawn_pct"] = float(np.hypot(*(pm[matched_g[i]] - gm_drawn[i])) / ph * 100)
            a["dx"], a["dy"] = [float(v) for v in (pm[matched_g[i]] - gm_drawn[i])]
            a["pred_series"] = pattr[matched_g[i]]["pred_series"]
        elif d_final <= rad:
            a["stage"] = "taken"
        elif a["heat_max"] < MARKER_THR:
            a["stage"] = "no_heat"
        elif d_peak > rad:
            a["stage"] = "peak_off" if d_peak <= 2 * rad else "no_peak"
        else:
            j = int(np.argmin(np.hypot(rp_src[:, 0] - x, rp_src[:, 1] - y)))
            if len(mk_lab) and mk_lab[j] < 0:
                a["stage"] = "unlabelled"
            elif d_final <= 2 * rad:
                a["stage"] = "moved"
            else:
                a["stage"] = "dropped"
        rows_g.append(a)

    rows_p = []
    leg = meta.get("legend_bbox")
    # Distance to the nearest point of a traced line: can a decoder veto this return as a dash or a spike?
    traced = [se.line_px for se in ex.series if se.kind == "line" and len(se.line_px)]
    traced = np.vstack(traced) if traced else np.zeros((0, 2))
    for j, (x, y) in enumerate(pm):
        a = dict(pattr[j])
        a.update(x=float(x), y=float(y))
        a["heat"] = heat_max_at(x, y, r=1)
        a["d_line_px"] = float(np.hypot(traced[:, 0] - x, traced[:, 1] - y).min()) if len(traced) else np.inf
        d_gt = float(np.hypot(gm[:, 0] - x, gm[:, 1] - y).min()) if len(gm) else np.inf
        a["d_gt_px"] = d_gt
        if matched_p[j] >= 0:
            a["cause"] = "ok"
            a["gt_series"] = gattr[matched_p[j]]["series"]
        else:
            cls, inst = sem_at(x, y)
            if leg and leg[0] <= x <= leg[2] and leg[1] <= y <= leg[3]:
                a["cause"] = "legend"
            elif cls in ("text", "tick_label", "legend_symbol", "axis", "grid"):
                a["cause"] = cls
            elif cls == "data":
                k = series_kind.get(inst, "?")
                if k in ("scatter", "line+markers"):
                    a["cause"] = "dup" if d_gt <= 2 * rad else "marker_ink"
                else:
                    a["cause"] = "line_ink"
            else:
                a["cause"] = "dup" if d_gt <= 2 * rad else "bg"
            a["under"] = cls
        rows_p.append(a)

    # Grouping: purity of each predicted marker series, fragmentation of each true one.
    groups = []
    for pi, se in enumerate(ex.series):
        gts = [gattr[matched_p[j]]["series"] for j in range(len(pm)) if pattr[j]["pred_series"] == pi and matched_p[j] >= 0]
        n_all = sum(1 for j in range(len(pm)) if pattr[j]["pred_series"] == pi)
        if n_all == 0:
            continue
        c = collections.Counter(gts)
        top = c.most_common(1)[0][1] if c else 0
        groups.append(dict(pred_series=pi, kind=se.kind, n=n_all, n_matched=len(gts), purity=(top / len(gts)) if gts else 0.0,
                           gt_series=sorted(c)))
    frag = {}
    for i in range(len(gm)):
        if matched_g[i] >= 0:
            frag.setdefault(gattr[i]["series"], set()).add(pattr[matched_g[i]]["pred_series"])
    density = max([len(sr["x"]) / max(pa[2] - pa[0], 1) for sr in meta["series"] if sr["kind"] in ("line", "step", "line+markers", "area")] or [0.0])
    return dict(id=meta["seed"], n_gt=len(gm), n_pred=len(pm), tp=int((matched_g >= 0).sum()), tp_capped=tp_capped, rad=rad, scale=s,
                n_series=len(meta["series"]), density=density, probe=meta.get("probe"), gt=rows_g, pred=rows_p,
                groups=groups, frag={str(k): len(v) for k, v in frag.items()}), gm, pm, matched_g, matched_p, mh


def overlay(img, gm, pm, matched_g, matched_p, scale=2):
    out = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
    out = (out.astype(np.float32) * 0.6 + 255 * 0.4).astype(np.uint8)
    for i, (x, y) in enumerate(gm):
        c = (0, 170, 0) if matched_g[i] >= 0 else (220, 0, 0)
        cv2.circle(out, (int(round(x * scale)), int(round(y * scale))), 5, c, 1, cv2.LINE_AA)
    for j, (x, y) in enumerate(pm):
        c = (0, 90, 255) if matched_p[j] >= 0 else (230, 0, 230)
        cv2.drawMarker(out, (int(round(x * scale)), int(round(y * scale))), c, cv2.MARKER_TILTED_CROSS, 7, 1)
    return out


def heat_image(mh, M, img):
    """The marker heat mapped back onto the source image size, as a grey image with the source faintly under it."""
    Mi = E.inv_affine(M)
    h, w = img.shape[:2]
    hm = cv2.warpAffine((mh * 255).astype(np.uint8), Mi, (w, h), flags=cv2.INTER_LINEAR)
    base = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY).astype(np.float32) * 0.25 + 190
    out = np.stack([base, base, base], -1)
    out[..., 0] = np.maximum(out[..., 0], hm)
    out[..., 1] = np.where(hm > 0, out[..., 1] * (1 - hm / 255.0), out[..., 1])
    out[..., 2] = np.where(hm > 0, out[..., 2] * (1 - hm / 255.0), out[..., 2])
    return np.clip(out, 0, 255).astype(np.uint8)


def tile(img, hm_img, x, y, half=20, up=3):
    h, w = img.shape[:2]
    x0, y0 = int(round(x)) - half, int(round(y)) - half
    pad = lambda a: cv2.copyMakeBorder(a, half, half, half, half, cv2.BORDER_CONSTANT, value=(128, 128, 128))
    a = pad(img)[y0 + half: y0 + 3 * half + 1, x0 + half: x0 + 3 * half + 1]
    b = pad(hm_img)[y0 + half: y0 + 3 * half + 1, x0 + half: x0 + 3 * half + 1]
    a = cv2.resize(a, None, fx=up, fy=up, interpolation=cv2.INTER_NEAREST)
    b = cv2.resize(b, None, fx=up, fy=up, interpolation=cv2.INTER_NEAREST)
    c = (half * up + up // 2)
    cv2.drawMarker(a, (c, c), (255, 0, 255), cv2.MARKER_CROSS, 9, 1)
    cv2.drawMarker(b, (c, c), (255, 0, 255), cv2.MARKER_CROSS, 9, 1)
    return np.hstack([a, np.full((a.shape[0], 2, 3), 0, np.uint8), b])


def sheet(tiles, cols=6):
    if not tiles:
        return None
    th, tw = tiles[0].shape[:2]
    rows = int(math.ceil(len(tiles) / cols))
    out = np.full((rows * (th + 4), cols * (tw + 4), 3), 255, np.uint8)
    for k, t in enumerate(tiles):
        r, c = divmod(k, cols)
        out[r * (th + 4): r * (th + 4) + th, c * (tw + 4): c * (tw + 4) + tw] = t
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*", type=int, default=None)
    ap.add_argument("--worst", type=int, default=30, help="overlays for this many charts with the most FN+FP")
    ap.add_argument("--no-refine", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    net = load_net(a.ckpt)
    store = _capture_cluster()
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]
    if a.ids:
        want = set(a.ids)
        files = [f for f in files if int(os.path.basename(f)[:-5]) in want]
    rows = []
    tiles = collections.defaultdict(list)
    keep = []
    for f in files:
        meta = json.load(open(f))
        stem = f[:-5]
        img = cv2.imread(stem + ".png")[..., ::-1].copy()
        sem_gt = cv2.imread(stem + ".sem.png", cv2.IMREAD_UNCHANGED)
        inst_gt = cv2.imread(stem + ".inst.png", cv2.IMREAD_UNCHANGED)
        store.clear()
        out, M = E.run_net(net, img)
        ex = E.extract(out, M, img)
        if not a.no_refine:
            ex = E.refine_markers(img, E.refine_lines(img, ex))
        r, gm, pm, mg, mp, mh = analyse(meta, img, sem_gt, inst_gt, out, M, ex, store)
        rows.append(r)
        bad = (len(gm) - r["tp"]) + (len(pm) - r["tp"])
        if len(gm) or len(pm):
            keep.append((bad, meta["seed"], img, gm, pm, mg, mp, mh, M, r))
        print(f"{meta['seed']}  gt {len(gm):4d}  pred {len(pm):4d}  tp {r['tp']:4d}  "
              f"FN {len(gm) - r['tp']:4d}  FP {len(pm) - r['tp']:4d}", flush=True)
    keep.sort(key=lambda t: -t[0])
    for bad, seed, img, gm, pm, mg, mp, mh, M, r in keep[: a.worst]:
        cv2.imwrite(os.path.join(a.out, f"{seed}.png"), overlay(img, gm, pm, mg, mp)[..., ::-1])
        cv2.imwrite(os.path.join(a.out, f"{seed}-heat.png"), heat_image(mh, M, img)[..., ::-1])
    # Contact sheets, up to 48 tiles per cause, at most 4 per chart so the sheet spans many charts.
    for bad, seed, img, gm, pm, mg, mp, mh, M, r in keep:
        hm_img = None
        per = collections.Counter()
        for g in r["gt"]:
            k = "FN-" + g["stage"]
            if g["stage"] != "ok" and len(tiles[k]) < 48 and per[k] < 4:
                hm_img = heat_image(mh, M, img) if hm_img is None else hm_img
                tiles[k].append(tile(img, hm_img, g["x"], g["y"]))
                per[k] += 1
        for p in r["pred"]:
            k = "FP-" + p["cause"]
            if p["cause"] != "ok" and len(tiles[k]) < 48 and per[k] < 4:
                hm_img = heat_image(mh, M, img) if hm_img is None else hm_img
                tiles[k].append(tile(img, hm_img, p["x"], p["y"]))
                per[k] += 1
    for k, ts in tiles.items():
        cv2.imwrite(os.path.join(a.out, f"sheet-{k}.png"), sheet(ts)[..., ::-1])

    # Summary.
    gt_all = [g for r in rows for g in r["gt"]]
    pr_all = [p for r in rows for p in r["pred"]]
    S = dict(charts=len(rows), n_gt=len(gt_all), n_pred=len(pr_all), tp=sum(r["tp"] for r in rows))
    S["recall"] = S["tp"] / max(1, S["n_gt"])
    S["precision"] = S["tp"] / max(1, S["n_pred"])
    S["fn_by_stage"] = dict(collections.Counter(g["stage"] for g in gt_all if g["stage"] != "ok"))
    S["fp_by_cause"] = dict(collections.Counter(p["cause"] for p in pr_all if p["cause"] != "ok"))

    def rate(sel):
        n = len(sel)
        return dict(n=n, recall=(sum(g["stage"] == "ok" for g in sel) / n) if n else None)

    S["by_kind"] = {k: rate([g for g in gt_all if g["kind"] == k]) for k in sorted({g["kind"] for g in gt_all})}
    S["by_shape"] = {k: rate([g for g in gt_all if g["shape"] == k]) for k in sorted({g["shape"] for g in gt_all})}
    bins = [0, 4, 6, 8, 12, 20, 1e9]
    S["by_size_px"] = {f"{bins[i]}-{bins[i + 1]}": rate([g for g in gt_all if bins[i] <= g["size_px"] < bins[i + 1]]) for i in range(len(bins) - 1)}
    nb = [0, 0.5, 1.0, 1.5, 2.0, 4.0, 1e9]
    S["by_nn_over_size"] = {f"{nb[i]}-{nb[i + 1]}": rate([g for g in gt_all if nb[i] <= g["nn_rel"] < nb[i + 1]]) for i in range(len(nb) - 1)}
    pb = [0, 3, 5, 8, 12, 20, 1e9]
    S["by_nn_px"] = {f"{pb[i]}-{pb[i + 1]}": rate([g for g in gt_all if pb[i] <= g["nn_px"] < pb[i + 1]]) for i in range(len(pb) - 1)}
    S["by_n_series"] = {str(k): rate([g for r in rows if r["n_series"] == k for g in r["gt"]]) for k in range(1, 7)}
    # Stage by nn bucket: where the overlaps go.
    S["stage_by_nn_px"] = {f"{pb[i]}-{pb[i + 1]}": dict(collections.Counter(g["stage"] for g in gt_all if pb[i] <= g["nn_px"] < pb[i + 1]))
                           for i in range(len(pb) - 1)}
    S["stage_by_kind"] = {k: dict(collections.Counter(g["stage"] for g in gt_all if g["kind"] == k)) for k in S["by_kind"]}
    S["fp_cause_by_pred_kind"] = {k: dict(collections.Counter(p["cause"] for p in pr_all if p["pred_kind"] == k and p["cause"] != "ok"))
                                  for k in ("line", "scatter")}
    # How many spurious returns, and how many correct ones, sit within 2 px of a traced line.
    S["near_traced_line"] = {
        "fp_line_ink_within_2px": sum(1 for p in pr_all if p["cause"] == "line_ink" and p["d_line_px"] <= 2.0),
        "fp_line_ink": sum(1 for p in pr_all if p["cause"] == "line_ink"),
        "fp_any_within_2px": sum(1 for p in pr_all if p["cause"] != "ok" and p["d_line_px"] <= 2.0),
        "tp_within_2px": sum(1 for p in pr_all if p["cause"] == "ok" and p["d_line_px"] <= 2.0),
        "tp": sum(1 for p in pr_all if p["cause"] == "ok"),
    }
    errs = np.array([g["err_pct"] for g in gt_all if g["stage"] == "ok"])
    S["err_median_pct"] = float(np.median(errs)) if len(errs) else None
    errd = np.array([g["err_drawn_pct"] for g in gt_all if g["stage"] == "ok"])
    S["err_drawn_median_pct"] = float(np.median(errd)) if len(errd) else None
    S["recall_capped"] = sum(r["tp_capped"] for r in rows) / max(1, S["n_gt"])
    S["precision_capped"] = sum(r["tp_capped"] for r in rows) / max(1, S["n_pred"])
    # Bias of the returned centre against the drawn centre, in source px, isolated symmetric markers only.
    iso = [g for g in gt_all if g["stage"] == "ok" and g["nn_px"] >= 12 and g["shape"] in ("o", "s", "D", "d", "h", "8", "x", "+", "P", "X", ".", "*", "circle", "square", "diamond", "cross", "x", "hexagon")]
    if iso:
        S["bias_px_isolated_symmetric"] = dict(n=len(iso), dx_mean=float(np.mean([g["dx"] for g in iso])), dy_mean=float(np.mean([g["dy"] for g in iso])),
                                               dx_median=float(np.median([g["dx"] for g in iso])), dy_median=float(np.median([g["dy"] for g in iso])),
                                               abs_median=float(np.median([math.hypot(g["dx"], g["dy"]) for g in iso])))
    S["err_by_shape_median_pct"] = {k: float(np.median([g["err_pct"] for g in gt_all if g["stage"] == "ok" and g["shape"] == k]))
                                    for k in S["by_shape"] if any(g["stage"] == "ok" and g["shape"] == k for g in gt_all)}
    purs = [g for r in rows for g in r["groups"] if g["n_matched"] > 0]
    S["groups"] = dict(n_pred_marker_series=len(purs), impure=sum(1 for g in purs if g["purity"] < 1.0),
                       mean_purity=float(np.mean([g["purity"] for g in purs])) if purs else None,
                       gt_series_split=sum(1 for r in rows for v in r["frag"].values() if v > 1),
                       gt_series_matched=sum(len(r["frag"]) for r in rows))
    # Charts: worst by FN and by FP.
    S["worst_fn"] = [(r["id"], r["n_gt"] - r["tp"], r["n_gt"]) for r in sorted(rows, key=lambda r: -(r["n_gt"] - r["tp"]))[:15]]
    S["worst_fp"] = [(r["id"], r["n_pred"] - r["tp"], r["n_pred"]) for r in sorted(rows, key=lambda r: -(r["n_pred"] - r["tp"]))[:15]]
    json.dump(S, open(os.path.join(a.out, "summary.json"), "w"), indent=1, default=float)
    json.dump(rows, open(os.path.join(a.out, "rows.json"), "w"), default=float)
    print(json.dumps(S, indent=1, default=float))


if __name__ == "__main__":
    main()
