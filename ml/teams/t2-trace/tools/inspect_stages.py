"""Where in the pipeline each ground-truth line series is lost.

    python teams/t2-trace/tools/inspect_stages.py --ckpt runs/v3/best.pt --data data/mpl-val \
        --seeds 9000012 9000031 --out out/t2c/inspect

For every chart: runs PlotNet, records what each decoding stage produced
(embedding clusters, chains per cluster, merged fragments, what drop_duplicates
removed, what the marker-row filter removed), and prints one line per true line
series with a verdict naming the first stage that failed it:

    heat        the line heat is missing along most of the curve
    emb-split   its pixels fall in several embedding clusters, and the chains broke there
    emb-merge   its cluster also holds another series' pixels and a chain hopped
    hop         a chain covering it also follows another series
    fragment    pieces of it were never joined (merge_fragments)
    dropped     a piece covering it was removed (too short, too faint, or as a duplicate)
    marker-row  removed as a row of markers
    wander      found, but off by more than 1% on a tenth of its columns
    ok

The stages are recorded by wrapping the functions of `p2d.extract` by name, so
the tool follows changes to their internals. A composite PNG per chart shows
the overlay, the line heat, the embedding (PCA to RGB), the clusters, the
chains before merging and the final lines with the dropped pieces in red.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

import cv2
import numpy as np

# P2D_SRC points at a frozen copy of the package (out/t2c/base-src), for baseline numbers that do not move
# while the live p2d/ is being edited.
sys.path.insert(0, os.environ.get("P2D_SRC") or os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from p2d import extract as X  # noqa: E402
from p2d.data import CANVAS_H, CANVAS_W, H_LINE, H_MARKER, apply, densify  # noqa: E402
from p2d.evaluate import load_net  # noqa: E402
from p2d.metrics import LINE_KINDS, score  # noqa: E402

PAL = [(230, 0, 230), (0, 120, 255), (255, 120, 0), (0, 0, 0), (200, 0, 0), (0, 160, 160), (120, 60, 0),
       (0, 0, 200), (160, 0, 120), (90, 140, 0)]


class Recorder:
    """Wraps the stage functions of p2d.extract and keeps what they returned."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.lab = None
        self.chains = []  # list of chain lists, one per peel_chains call
        self.merge_in = None
        self.merge_out = None
        self.dd_in = None
        self.dd_out = None
        self.dd_kw = None

    def install(self):
        rec = self
        orig = {k: getattr(X, k) for k in ("cluster_embeddings", "peel_chains", "merge_fragments", "drop_duplicates")}

        def cluster_embeddings(*a, **k):
            out = orig["cluster_embeddings"](*a, **k)
            rec.lab = out
            return out

        def peel_chains(*a, **k):
            out = orig["peel_chains"](*a, **k)
            rec.chains.append(out)
            return out

        def merge_fragments(frags, *a, **k):
            rec.merge_in = [dict(f) for f in frags]
            out = orig["merge_fragments"](frags, *a, **k)
            rec.merge_out = out
            return out

        def drop_duplicates(lines, *a, **k):
            rec.dd_in = list(lines)
            rec.dd_kw = dict(k)
            if a:
                rec.dd_kw["min_cols"] = a[0]
            out = orig["drop_duplicates"](lines, *a, **k)
            rec.dd_out = out
            return out

        X.cluster_embeddings = cluster_embeddings
        X.peel_chains = peel_chains
        X.merge_fragments = merge_fragments
        X.drop_duplicates = drop_duplicates
        self.orig = orig

    def uninstall(self):
        for k, v in self.orig.items():
            setattr(X, k, v)


def gt_canvas_curves(meta: dict, M: np.ndarray):
    """For each true line series: its y per integer canvas column, NaN where not drawn or clipped."""
    pa = apply(M, [[meta["plot_area"][0], meta["plot_area"][1]], [meta["plot_area"][2], meta["plot_area"][3]]])
    x0, y0 = pa[0]
    x1, y1 = pa[1]
    xs = np.arange(int(np.ceil(x0)), int(np.floor(x1)) + 1)
    out = []
    for s in meta["series"]:
        if s["kind"] not in LINE_KINDS:
            continue
        p = apply(M, s["path_px"]) if s["path_px"] else np.zeros((0, 2))
        if len(p) < 2:
            out.append((s, xs, np.full(len(xs), np.nan)))
            continue
        o = np.argsort(p[:, 0], kind="stable")
        y = np.interp(xs, p[o, 0], p[o, 1], left=np.nan, right=np.nan)
        y[(y < y0) | (y > y1)] = np.nan
        out.append((s, xs, y))
    return out, (x0, y0, x1, y1)


def chain_owner(cols, ys, curves, tol=3.0):
    """For each column of a chain, the index of the true series it lies on (within tol px), or -1."""
    own = np.full(len(cols), -1)
    best = np.full(len(cols), tol + 1e-9)
    for i, (_, xs, gy) in enumerate(curves):
        idx = np.round(cols).astype(int) - xs[0]
        ok = (idx >= 0) & (idx < len(xs))
        d = np.full(len(cols), np.inf)
        d[ok] = np.abs(ys[ok] - gy[idx[ok]])
        better = d < best
        own[better] = i
        best[better] = d[better]
    return own


def diagnose(meta, out, M, rec: Recorder, ex, row, line_thr=0.25, final_canvas=None):
    heat, sem, emb = out["heat"], out["sem"], out["emb"]
    H, W = heat.shape[1:]
    lh = heat[H_LINE]
    curves, (fx0, fy0, fx1, fy1) = gt_canvas_curves(meta, M)
    frame = X.plot_frame(heat)
    roi = np.zeros((H, W), bool)
    if frame is not None:
        roi[max(0, int(frame[1]) - 1): int(frame[3]) + 3, max(0, int(frame[0]) - 1): int(frame[2]) + 3] = True
    else:
        roi[:] = True
    ink = (lh > line_thr) & roi
    iys, ixs = np.nonzero(ink)
    lab_img = np.full((H, W), -2, np.int32)
    if rec.lab is not None and len(rec.lab) >= len(ixs):
        lab_img[iys, ixs] = rec.lab[: len(ixs)]
    # Chains, flattened, with their owners.
    chains = [c for call in rec.chains for c in call]
    chain_cols = [np.array([c for c, _, _, _ in ch], float) for ch in chains]
    chain_ys = [np.array([y for _, y, _, _ in ch], float) for ch in chains]
    chain_own = [chain_owner(c, y, curves) for c, y in zip(chain_cols, chain_ys)]
    merged = rec.merge_out or []
    merged_own = [chain_owner(f["cols"], f["ys"], curves) for f in merged]
    dd_out_ids = {id(f) for f in (rec.dd_out or [])}
    kept_final = []  # lines that survived the marker-row filter: match by first col and length (before refinement)
    if final_canvas is None:
        final_canvas = [apply(M, s.line_px) for s in ex.series if s.kind == "line"]
    for f in (rec.dd_out or []):
        hit = any(len(fc) == len(f["cols"]) and abs(fc[0, 0] - f["cols"][0]) < 0.6 for fc in final_canvas)
        kept_final.append(hit)
    min_cols = (rec.dd_kw or {}).get("min_cols", 12)
    min_q = (rec.dd_kw or {}).get("min_q", 0.35)
    reports = []
    gi_cov = row["line_cov"]
    gi_good = row["line_good"]
    rms_list = list(row["line_rms"])
    ri = 0
    for i, (s, xs, gy) in enumerate(curves):
        valid = ~np.isnan(gy)
        n = int(valid.sum())
        rep = dict(idx=i, kind=s["kind"], ls=s["linestyle"], lw=s["linewidth_px"], n_pts=len(s["x"]), cols=n)
        cov = gi_cov[i]
        rep["cov"], rep["good"] = cov, gi_good[i]
        rep["rms"] = rms_list[ri] if cov > 0 and ri < len(rms_list) else np.nan
        if cov > 0:
            ri += 1
        if n < 3:
            rep["verdict"] = "n/a"
            reports.append(rep)
            continue
        cx = xs[valid]
        cy = gy[valid]
        yi = np.round(cy).astype(int)
        # Heat along the curve: the max within 2 px of the true y, per column.
        hm = np.zeros(n)
        for j, (x, y) in enumerate(zip(cx, yi)):
            if 0 <= x < W:
                a, b = max(0, y - 2), min(H, y + 3)
                if b > a:
                    hm[j] = lh[a:b, x].max()
        rep["heat_cov"] = float((hm > line_thr).mean())
        rep["heat_mean"] = float(hm.mean())
        # Embedding clusters of the ink within 1.5 px of the curve.
        labs = []
        for x, y in zip(cx, yi):
            if 0 <= x < W:
                a, b = max(0, y - 1), min(H, y + 2)
                l = lab_img[a:b, x]
                l = l[l >= -1]
                if len(l):
                    labs.append(int(np.bincount(l + 1).argmax()) - 1)
        labs = np.array(labs) if labs else np.zeros(0, int)
        if len(labs):
            u, cnt = np.unique(labs, return_counts=True)
            order = np.argsort(-cnt)
            rep["clusters"] = [(int(u[k]), round(float(cnt[k] / len(labs)), 2)) for k in order[:4]]
            dom = int(u[order[0]])
            # How much of the dominant cluster lies on other series.
            if dom >= 0:
                mine = np.zeros((H, W), bool)
                mine[yi.clip(0, H - 1), cx.clip(0, W - 1)] = True
                mine = cv2.dilate(mine.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                others = np.zeros((H, W), bool)
                for k2, (_, xs2, gy2) in enumerate(curves):
                    if k2 == i:
                        continue
                    v2 = ~np.isnan(gy2)
                    others[np.round(gy2[v2]).astype(int).clip(0, H - 1), xs2[v2].clip(0, W - 1)] = True
                others = cv2.dilate(others.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
                cl = lab_img == dom
                rep["cluster_shared"] = float((cl & others & ~mine).sum() / max(cl.sum(), 1))
            else:
                rep["cluster_shared"] = 0.0
        else:
            rep["clusters"] = []
            rep["cluster_shared"] = 0.0
        # Chains covering this series.
        cov_chains = []
        hops = 0
        for ci, own in enumerate(chain_own):
            m = (own == i).sum()
            if m >= max(5, 0.05 * n):
                cov_chains.append((ci, m))
                other = ((own >= 0) & (own != i)).sum()
                if other >= max(8, 0.1 * len(own)):
                    hops += 1
        rep["n_chains"] = len(cov_chains)
        rep["chain_cov"] = float(sum(m for _, m in cov_chains) / n)
        rep["hops"] = hops
        # Merged pieces covering it, and their fate.
        pieces = []
        for mi, own in enumerate(merged_own):
            m = (own == i).sum()
            if m >= max(5, 0.05 * n):
                f = merged[mi]
                fate = "kept"
                if id(f) not in dd_out_ids:
                    if len(f["cols"]) < min_cols:
                        fate = "short"
                    elif f.get("q", 1.0) < min_q:
                        fate = "faint"
                    else:
                        fate = "dup"
                else:
                    k = [id(g) for g in rec.dd_out].index(id(f))
                    if not kept_final[k]:
                        fate = "marker-row"
                wrong = int(((own >= 0) & (own != i)).sum())
                pieces.append((mi, int(m), wrong, fate))
        rep["pieces"] = pieces
        # Why consecutive kept pieces of this series were not joined: the quantities merge_fragments tests.
        kept_pieces = sorted([merged[mi] for mi, _, _, fate in pieces if fate == "kept"], key=lambda f: f["cols"][0])
        refusals = []
        for A, B in zip(kept_pieces[:-1], kept_pieces[1:]):
            dx = float(B["cols"][0] - A["cols"][-1])
            if dx <= 0:
                ov = A["cols"] >= B["cols"][0]
                ygap = float(np.abs(A["ys"][ov] - np.interp(A["cols"][ov], B["cols"], B["ys"])).max()) if ov.any() else 0.0
            else:
                a0, a1 = A["spans"][-1]
                b0, b1 = B["spans"][0]
                ygap = float(max(0, b0 - a1 - 1, a0 - b1 - 1))
            de = float(np.linalg.norm(A["emb"] - B["emb"]))
            # The slope of A at its end, extrapolated over dx, against B's start.
            ka = max(0, len(A["cols"]) - 6)
            slope = float((A["ys"][-1] - A["ys"][ka]) / max(A["cols"][-1] - A["cols"][ka], 1))
            extrap = float(abs(A["ys"][-1] + slope * max(dx, 0) - B["ys"][0]))
            refusals.append(dict(dx=round(dx, 1), ygap=round(ygap, 1), de=round(de, 2), extrap=round(extrap, 1),
                                 lenA=len(A["cols"]), lenB=len(B["cols"])))
        rep["refusals"] = refusals
        # Verdict: first failing stage.
        found = cov > 0.5
        if rep["heat_cov"] < 0.6:
            v = "heat"
        elif found and rep["good"] >= 0.9:
            v = "ok"
        elif hops and rep["cluster_shared"] >= 0.25:
            v = "emb-merge"
        elif hops:
            v = "hop"
        elif len(rep["clusters"]) >= 2 and rep["clusters"][1][1] >= 0.15 and len(cov_chains) >= 2:
            v = "emb-split"
        elif pieces and all(p[3] in ("dup", "short", "faint", "marker-row") for p in pieces):
            v = "dropped:" + pieces[0][3]
        elif len([p for p in pieces if p[3] == "kept"]) >= 2:
            v = "fragment"
        elif len(cov_chains) >= 2 and rep["chain_cov"] > 0.5 and not found:
            v = "fragment"
        elif any(p[3] != "kept" for p in pieces) and not found:
            v = "dropped:" + [p[3] for p in pieces if p[3] != "kept"][0]
        elif not found and rep["chain_cov"] < 0.5:
            v = "chain-gap"
        elif found:
            v = "wander"
        else:
            v = "other"
        rep["verdict"] = v
        reports.append(rep)
    return reports, dict(lab_img=lab_img, chains=(chain_cols, chain_ys), merged=merged, ink=ink, curves=curves)


def composite(img, out, M, ex, meta, dbg, rec):
    heat, emb = out["heat"], out["emb"]
    H, W = heat.shape[1:]
    s = math.hypot(M[0, 0], M[1, 0])
    canvas = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR,
                            borderValue=(255, 255, 255))
    base = (canvas.astype(np.float32) * 0.45 + 255 * 0.55).astype(np.uint8)

    def poly(im, pts, col, th=1):
        if len(pts) > 1:
            cv2.polylines(im, [np.round(np.asarray(pts) * 4).astype(np.int32)], False, col, th, cv2.LINE_AA, shift=2)

    p1 = base.copy()
    gt_series = meta["series"] if meta else []
    for s_ in gt_series:
        if s_["path_px"]:
            poly(p1, apply(M, s_["path_px"]), (0, 200, 0))
    for k, se in enumerate(ex.series):
        if len(se.line_px) > 1:
            poly(p1, apply(M, se.line_px), PAL[k % len(PAL)])
        for m in se.markers_px:
            q = apply(M, [m])[0]
            cv2.drawMarker(p1, (int(round(q[0])), int(round(q[1]))), PAL[k % len(PAL)], cv2.MARKER_TILTED_CROSS, 7, 1)
    p2 = np.repeat((255 - 255 * heat[H_LINE])[..., None].astype(np.uint8), 3, -1)
    p2[..., 0] = np.minimum(p2[..., 0], (255 - 255 * heat[H_MARKER]).astype(np.uint8))
    for s_ in gt_series:
        if s_["path_px"]:
            poly(p2, apply(M, s_["path_px"]), (0, 200, 0))
    ink = dbg["ink"]
    e = emb.reshape(emb.shape[0], -1).T
    ys, xs = np.nonzero(ink)
    p3 = np.full((H, W, 3), 255, np.uint8)
    if len(xs) > 8:
        v = e[ys * W + xs]
        mu = v.mean(0)
        u, sv, vt = np.linalg.svd(v - mu, full_matrices=False)
        proj = (v - mu) @ vt[:3].T
        lo, hi = np.quantile(proj, 0.02, 0), np.quantile(proj, 0.98, 0)
        rgb = np.clip((proj - lo) / np.maximum(hi - lo, 1e-6), 0, 1)
        p3[ys, xs] = (rgb * 255).astype(np.uint8)
    p4 = np.full((H, W, 3), 255, np.uint8)
    lab = dbg["lab_img"]
    rng = np.random.default_rng(3)
    cols = rng.integers(0, 200, (64, 3))
    m = lab >= 0
    p4[m] = cols[lab[m] % 64]
    p4[lab == -1] = (200, 200, 200)
    p5 = base.copy()
    for k, (cc, yy) in enumerate(zip(*dbg["chains"])):
        poly(p5, np.column_stack([cc, yy]), tuple(int(c) for c in cols[(k * 7) % 64]))
    p6 = base.copy()
    kept = {id(f) for f in (rec.dd_out or [])}
    for k, f in enumerate(dbg["merged"]):
        col = PAL[k % len(PAL)] if id(f) in kept else (255, 0, 0)
        poly(p6, np.column_stack([f["cols"], f["ys"]]), col, 1 if id(f) in kept else 2)
    for p, t in ((p1, "overlay: GT green, final lines"), (p2, "line heat (marker heat in red)"), (p3, "embedding PCA"),
                 (p4, "clusters"), (p5, "chains before merge"), (p6, "merged; dropped in red")):
        cv2.putText(p, t, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1, cv2.LINE_AA)
    top = np.hstack([p1, p2, p3])
    bot = np.hstack([p4, p5, p6])
    return np.vstack([top, bot])


def fmt(rep):
    if rep.get("verdict") == "n/a":
        return f"  s{rep['idx']} {rep['kind']} n/a (not drawn)"
    pieces = " ".join(f"m{mi}:{m}c{'/' + str(w) + 'wrong' if w else ''}:{fate}" for mi, m, w, fate in rep["pieces"])
    ref = " ".join(f"(dx={r['dx']} ygap={r['ygap']} extrap={r['extrap']} de={r['de']} {r['lenA']}+{r['lenB']})" for r in rep.get("refusals", []))
    return (f"  s{rep['idx']} {rep['kind']:12s} ls={rep['ls']:2s} lw={rep['lw']:.1f} n={rep['n_pts']:4d} cols={rep['cols']:4d} "
            f"| heat={rep['heat_cov']:.2f} | clusters={rep['clusters']} shared={rep['cluster_shared']:.2f} "
            f"| chains={rep['n_chains']} chain_cov={rep['chain_cov']:.2f} hops={rep['hops']} | pieces=[{pieces}] "
            f"{'| unjoined ' + ref + ' ' if ref else ''}"
            f"| cov={rep['cov']:.2f} good={rep['good']:.2f} rms={rep['rms'] * 100 if rep['rms'] == rep['rms'] else float('nan'):.2f}% -> {rep['verdict']}")


SEM_NAMES = ["bg", "data", "legend_symbol", "axis", "grid", "tick_label", "text"]


def inspect_image(net, rec: Recorder, path: str, out_dir: str | None, refine: bool) -> None:
    """A chart without ground truth: what each returned line runs over."""
    img = cv2.imread(path)[..., ::-1].copy()
    rec.reset()
    out, M = X.run_net(net, img)
    ex = X.extract(out, M, img)
    if refine:
        ex = X.refine_markers(img, X.refine_lines(img, ex))
    sem_cls = out["sem"].argmax(0)
    H, W = sem_cls.shape
    lh = out["heat"][H_LINE]
    lines = [s for s in ex.series if s.kind == "line"]
    print(f"{os.path.basename(path)}: {img.shape[1]}x{img.shape[0]} lines={len(lines)} scatter={len(ex.series) - len(lines)} "
          f"chains={sum(len(c) for c in rec.chains)} merged={len(rec.merge_out or [])} after_drop={len(rec.dd_out or [])} "
          f"frame={np.round(ex.plot_area, 1).tolist() if ex.plot_area else None}")
    for k, s in enumerate(lines):
        c = apply(M, s.line_px)
        xi = np.round(c[:, 0]).astype(int).clip(0, W - 1)
        yi = np.round(c[:, 1]).astype(int).clip(0, H - 1)
        comp = np.bincount(sem_cls[yi, xi], minlength=7) / len(xi)
        under = " ".join(f"{SEM_NAMES[i]}={comp[i]:.2f}" for i in np.argsort(-comp)[:3] if comp[i] > 0.02)
        print(f"  line {k}: cols {c[:, 0].min():.0f}-{c[:, 0].max():.0f} ({len(c)} samples) y {c[:, 1].min():.0f}-{c[:, 1].max():.0f} "
              f"heat_mean={lh[yi, xi].mean():.2f} colour={s.color} markers={len(s.markers_px)} under: {under}")
    for k, f in enumerate(rec.merge_out or []):
        kept = f in (rec.dd_out or [])
        if not kept:
            cols = f["cols"]
            print(f"  dropped piece {k}: cols {cols[0]:.0f}-{cols[-1]:.0f} ({len(cols)}) q={f.get('q', 0):.2f}")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        lab_img = np.full((H, W), -2, np.int32)
        frame = X.plot_frame(out["heat"])
        roi = np.zeros((H, W), bool)
        if frame is not None:
            roi[max(0, int(frame[1]) - 1): int(frame[3]) + 3, max(0, int(frame[0]) - 1): int(frame[2]) + 3] = True
        else:
            roi[:] = True
        ink = (lh > 0.25) & roi
        iys, ixs = np.nonzero(ink)
        if rec.lab is not None and len(rec.lab) >= len(ixs):
            lab_img[iys, ixs] = rec.lab[: len(ixs)]
        chains = [c for call in rec.chains for c in call]
        dbg = dict(lab_img=lab_img, ink=ink, merged=rec.merge_out or [],
                   chains=([np.array([c for c, _, _, _ in ch], float) for ch in chains], [np.array([y for _, y, _, _ in ch], float) for ch in chains]))
        name = os.path.splitext(os.path.basename(path))[0]
        cv2.imwrite(os.path.join(out_dir, f"{name}.png"), composite(img, out, M, ex, None, dbg, rec)[..., ::-1])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--data", default=None)
    ap.add_argument("--image", nargs="*", default=None, help="chart images without ground truth")
    ap.add_argument("--seeds", nargs="*", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None, help="instead of --seeds: the first N charts")
    ap.add_argument("--out", default=None, help="write composite PNGs here")
    ap.add_argument("--json", default=None, help="write the per-series reports here")
    ap.add_argument("--refine", action="store_true")
    ap.add_argument("--only-bad", action="store_true", help="print only series not ok")
    a = ap.parse_args()
    net = load_net(a.ckpt)
    rec = Recorder()
    rec.install()
    if a.image:
        for p in a.image:
            inspect_image(net, rec, p, a.out, a.refine)
        rec.uninstall()
        return
    if a.seeds:
        seeds = a.seeds
    else:
        import glob
        seeds = [int(os.path.basename(f)[:-5]) for f in sorted(glob.glob(os.path.join(a.data, "*.json")))[: a.limit]]
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    all_reports = []
    verdicts = {}
    for seed in seeds:
        f = os.path.join(a.data, f"{seed:07d}.json")
        meta = json.load(open(f))
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        rec.reset()
        out, M = X.run_net(net, img)
        ex = X.extract(out, M, img)
        final_canvas = [apply(M, s.line_px) for s in ex.series if s.kind == "line"]
        if a.refine:
            ex = X.refine_markers(img, X.refine_lines(img, ex))
        row = score(meta, ex, canvas_scale=math.hypot(M[0, 0], M[1, 0]))
        reps, dbg = diagnose(meta, out, M, rec, ex, row, final_canvas=final_canvas)
        n_pred = len([s for s in ex.series if s.kind == "line"])
        print(f"seed {seed}: {meta.get('preset', '')} {meta.get('style', '')} n_series={len(meta['series'])} line_gt={row['n_line_gt']} line_pred={n_pred} "
              f"dens={row['density']:.2f} chains={sum(len(c) for c in rec.chains)} merged={len(rec.merge_out or [])} after_drop={len(rec.dd_out or [])}")
        for r in reps:
            if a.only_bad and r.get("verdict") in ("ok", "n/a"):
                continue
            print(fmt(r))
            verdicts[r.get("verdict")] = verdicts.get(r.get("verdict"), 0) + 1
            all_reports.append(dict(seed=seed, **{k: v for k, v in r.items()}))
        if a.out:
            cv2.imwrite(os.path.join(a.out, f"{seed}.png"), composite(img, out, M, ex, meta, dbg, rec)[..., ::-1])
    print("\nverdicts:", dict(sorted(verdicts.items(), key=lambda kv: -kv[1])))
    if a.json:
        json.dump(all_reports, open(a.json, "w"), default=float)
    rec.uninstall()


if __name__ == "__main__":
    main()
