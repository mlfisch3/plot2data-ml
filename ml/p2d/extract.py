"""From PlotNet outputs to geometry: plot frame, ticks, tick-label boxes, series.

Everything here works in canvas pixels and is mapped back to the source image
at the end through the inverse of the placement transform. Positions are
sub-pixel: peaks and ridges are refined by fitting a parabola to the log of the
heat around the maximum, which is exact for a Gaussian.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
import torch

from .data import (CANVAS_H, CANVAS_W, H_CORNER, H_LINE, H_MARKER, H_VERTEX, H_XTICK, H_YTICK, MEAN, STD, apply,
                   fit_transform)
from .synth.mpl_render import DATA, TICK_LABEL


@dataclass
class Series:
    kind: str  # "line" or "scatter" ("line" may also carry markers)
    line_px: np.ndarray  # N x 2 (x, y) in source pixels, one per canvas column, NaN-free
    markers_px: np.ndarray  # M x 2 in source pixels
    color: tuple[int, int, int] = (0, 0, 0)
    support: int = 0


@dataclass
class Extraction:
    M: np.ndarray
    plot_area: list[float] | None  # x0, y0, x1, y1 in source px
    xticks: list[dict] = field(default_factory=list)  # {pos, anchor, score, label_box}
    yticks: list[dict] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    raw: dict | None = None


def prepare(img: np.ndarray) -> tuple[torch.Tensor, np.ndarray]:
    """RGB uint8 image -> normalised canvas tensor and the placement transform."""
    h, w = img.shape[:2]
    M = fit_transform(w, h)
    bg = np.full((CANVAS_H, CANVAS_W, 3), img[0, 0], np.float32)
    valid = cv2.warpAffine(np.ones((h, w), np.uint8), M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_NEAREST)
    c = cv2.warpAffine(img, M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    c = np.where(valid[..., None] > 0, c, bg)
    x = (c - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1).copy())[None], M


def run_net(net, img: np.ndarray, device="cuda") -> tuple[dict, np.ndarray]:
    x, M = prepare(img)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
        o = net(x.to(device))
    out = {
        "sem": torch.softmax(o["sem"].float(), 1)[0].cpu().numpy(),
        "heat": torch.sigmoid(o["heat"].float())[0].cpu().numpy(),
        "emb": o["emb"].float()[0].cpu().numpy(),
    }
    return out, M


def inv_affine(M: np.ndarray) -> np.ndarray:
    A = np.vstack([M, [0, 0, 1]])
    return np.linalg.inv(A)[:2]


def _parabola_offset(a: float, b: float, c: float) -> float:
    """Sub-sample offset of the vertex of a parabola through (-1,a), (0,b), (1,c)."""
    den = a - 2 * b + c
    if den >= -1e-9:
        return 0.0
    return float(np.clip(0.5 * (a - c) / den, -0.5, 0.5))


def refine_peak(h: np.ndarray, x: int, y: int) -> tuple[float, float]:
    H, W = h.shape
    lg = np.log(np.clip(h, 1e-6, 1))
    dx = _parabola_offset(lg[y, x - 1], lg[y, x], lg[y, x + 1]) if 0 < x < W - 1 else 0.0
    dy = _parabola_offset(lg[y - 1, x], lg[y, x], lg[y + 1, x]) if 0 < y < H - 1 else 0.0
    return x + dx, y + dy


def peaks(h: np.ndarray, thr: float, nms: int = 3) -> list[tuple[float, float, float]]:
    mx = cv2.dilate(h, np.ones((2 * nms + 1, 2 * nms + 1), np.uint8))
    ys, xs = np.nonzero((h >= mx) & (h >= thr))
    out = []
    for x, y in zip(xs, ys):
        rx, ry = refine_peak(h, int(x), int(y))
        out.append((rx, ry, float(h[y, x])))
    out.sort(key=lambda p: -p[2])
    return out


def _split2(v: np.ndarray) -> tuple[float, float] | None:
    v = np.sort(v)
    if len(v) < 2:
        return None
    gaps = np.diff(v)
    i = int(np.argmax(gaps))
    if gaps[i] < 20:
        return None
    return float(np.median(v[: i + 1])), float(np.median(v[i + 1 :]))


def plot_frame(heat: np.ndarray) -> list[float] | None:
    pk = peaks(heat[H_CORNER], 0.25, nms=5)[:12]
    if len(pk) < 2:
        return None
    xs = np.array([p[0] for p in pk])
    ys = np.array([p[1] for p in pk])
    sx, sy = _split2(xs), _split2(ys)
    if sx is None or sy is None:
        return None
    return [sx[0], sy[0], sx[1], sy[1]]


def label_boxes(sem: np.ndarray, thr: float = 0.5) -> list[list[float]]:
    m = (sem[TICK_LABEL] > thr).astype(np.uint8)
    m = cv2.dilate(m, np.ones((3, 5), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
    boxes = []
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 6:
            continue
        boxes.append([x + 0.5, y + 0.5, x + w - 1.5, y + h - 1.5])  # undo the dilation's growth
    return boxes


def cluster_embeddings(e: np.ndarray, weight: np.ndarray, radius: float = 1.5, min_support: int = 20,
                       max_k: int = 16) -> np.ndarray:
    """Greedy mean-shift: seed at the strongest unassigned pixel, refine its centre, take its ball."""
    lab = np.full(len(e), -1, np.int32)
    k = 0
    order = np.argsort(-weight)
    while k < max_k:
        free = order[lab[order] < 0]
        if len(free) < min_support:
            break
        c = e[free[0]]
        for _ in range(5):
            d = np.linalg.norm(e[free] - c, axis=1)
            sel = free[d < radius]
            if len(sel) == 0:
                break
            c = np.average(e[sel], axis=0, weights=weight[sel] + 1e-6)
        d = np.linalg.norm(e[free] - c, axis=1)
        sel = free[d < radius]
        if len(sel) < min_support:
            lab[free[0]] = -2  # a lone seed: retire it and move on
            continue
        lab[sel] = k
        k += 1
    return lab


def extract(out: dict, M: np.ndarray, img: np.ndarray | None = None, line_thr: float = 0.25,
            marker_thr: float = 0.3) -> Extraction:
    heat, sem, emb = out["heat"], out["sem"], out["emb"]
    Mi = inv_affine(M)
    ex = Extraction(M=M, plot_area=None, raw=out)

    frame = plot_frame(heat)
    if frame is not None:
        p = apply(Mi, [[frame[0], frame[1]], [frame[2], frame[3]]])
        ex.plot_area = [p[0, 0], p[0, 1], p[1, 0], p[1, 1]]
    boxes = label_boxes(sem)
    for ch, key in ((H_XTICK, "xticks"), (H_YTICK, "yticks")):
        for x, y, s in peaks(heat[ch], 0.3, nms=3):
            src = apply(Mi, [[x, y]])[0]
            # The tick label nearest along the axis, on either side of it.
            best, bd = None, 1e9
            for b in boxes:
                cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
                if key == "xticks":
                    d = abs(cx - x) + 0.25 * abs(cy - y)
                    ok = abs(cy - y) < 80 and b[0] - 6 <= x <= b[2] + 6
                else:
                    d = abs(cy - y) + 0.25 * abs(cx - x)
                    ok = abs(cx - x) < 200 and b[1] - 6 <= y <= b[3] + 6
                if ok and d < bd:
                    best, bd = b, d
            lb = None
            if best is not None:
                q = apply(Mi, [[best[0], best[1]], [best[2], best[3]]])
                lb = [q[0, 0], q[0, 1], q[1, 0], q[1, 1]]
            getattr(ex, key).append(dict(pos=float(src[0] if key == "xticks" else src[1]), anchor=src.tolist(),
                                         score=s, label_box=lb))

    # --- series ---
    H, W = heat.shape[1:]
    lh = heat[H_LINE]
    mh = heat[H_MARKER]
    if frame is not None:
        fx0, fy0, fx1, fy1 = frame
        roi = np.zeros((H, W), bool)
        roi[max(0, int(fy0) - 1): int(fy1) + 3, max(0, int(fx0) - 1): int(fx1) + 3] = True
    else:
        roi = np.ones((H, W), bool)
    ink = (lh > line_thr) & roi
    mpk = [p for p in peaks(mh, marker_thr, nms=2) if roi[int(round(p[1])), int(round(p[0]))]]
    ys, xs = np.nonzero(ink)
    pts = np.column_stack([xs, ys])
    mp = np.array([[int(round(p[0])), int(round(p[1]))] for p in mpk], np.int64).reshape(-1, 2)
    # Marker regions vote too, through the data-ink class around each peak.
    data_ink = (sem[DATA] > 0.5) & roi & ~ink
    dys, dxs = np.nonzero(data_ink)
    allpts = np.vstack([pts, np.column_stack([dxs, dys]), mp]) if len(mp) or len(dxs) else pts
    if len(allpts) == 0:
        return ex
    e = emb[:, allpts[:, 1], allpts[:, 0]].T
    w = np.concatenate([lh[ys, xs], 0.5 * sem[DATA][dys, dxs], np.ones(len(mp)) * 2.0])
    lab = cluster_embeddings(e, w, min_support=15)
    n_line = len(pts)
    n_ink = len(dxs)
    line_lab = lab[:n_line]
    mk_lab = lab[n_line + n_ink:]

    for k in range(lab.max() + 1):
        sel = line_lab == k
        mk = np.array([[mpk[i][0], mpk[i][1]] for i in np.nonzero(mk_lab == k)[0]]).reshape(-1, 2)
        line_canvas = np.zeros((0, 2))
        if sel.sum() >= 15:
            mask = np.zeros((H, W), bool)
            mask[pts[sel, 1], pts[sel, 0]] = True
            # Grow into the faint shoulders of the ridge, so the parabola has its three samples.
            grown = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
            hm = np.where(grown, lh, 0)
            cols = np.nonzero(mask.any(0))[0]
            line = []
            for c in cols:
                col = hm[:, c]
                r = int(np.argmax(col))
                if col[r] < line_thr:
                    continue
                lg = np.log(np.clip(col[max(r - 1, 0): r + 2], 1e-6, 1))
                dy = _parabola_offset(*lg) if 0 < r < H - 1 and len(lg) == 3 else 0.0
                line.append((float(c), r + dy))
            line_canvas = np.array(line).reshape(-1, 2)
        is_line = len(line_canvas) >= 8 and len(line_canvas) > 2 * len(mk)
        if not is_line and len(mk) == 0:
            continue
        color = (0, 0, 0)
        if img is not None:
            src = apply(Mi, line_canvas if is_line else mk)
            xi = np.clip(np.round(src[:, 0]).astype(int), 0, img.shape[1] - 1)
            yi = np.clip(np.round(src[:, 1]).astype(int), 0, img.shape[0] - 1)
            color = tuple(int(v) for v in np.median(img[yi, xi], 0))
        ex.series.append(Series(kind="line" if is_line else "scatter",
                                line_px=apply(Mi, line_canvas) if is_line else np.zeros((0, 2)),
                                markers_px=apply(Mi, mk) if len(mk) else np.zeros((0, 2)),
                                color=color, support=int(sel.sum() + len(mk))))
    return ex


def _paper_colour(img: np.ndarray, area: list[float] | None) -> np.ndarray:
    h, w = img.shape[:2]
    if area is None:
        area = [0, 0, w - 1, h - 1]
    x0, y0 = max(0, int(area[0])), max(0, int(area[1]))
    x1, y1 = min(w, int(area[2]) + 1), min(h, int(area[3]) + 1)
    patch = img[y0:y1, x0:x1].reshape(-1, 3)
    if len(patch) == 0:
        patch = img.reshape(-1, 3)
    q = (patch // 8).astype(np.int32)
    key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    mode = np.bincount(key).argmax()
    return patch[key == mode].mean(0)


def refine_lines(img: np.ndarray, ex: Extraction, keep_vertex: float = 0.3) -> Extraction:
    """Re-measure each traced line on the source pixels, one sample per source column.

    The network says where a series runs and which ink is its; the exact centre
    is then the ink-weighted centroid of the source column, where a pixel's ink
    is how far along the paper-to-series-colour blend it lies. Pixels whose colour
    is off that segment belong to something else and weigh nothing. At vertices
    a column centroid is wrong by construction (it averages both flanks of a
    peak), so there the network's own centre-line estimate stands.
    """
    if not ex.series:
        return ex
    imf = img.astype(np.float32)
    H, W = img.shape[:2]
    paper = _paper_colour(img, ex.plot_area)
    Mi = inv_affine(ex.M)
    s = math.hypot(ex.M[0, 0], ex.M[1, 0])
    vh = ex.raw["heat"][H_VERTEX] if ex.raw is not None else None
    for se in ex.series:
        if se.kind != "line" or len(se.line_px) < 3:
            continue
        lp = se.line_px[np.argsort(se.line_px[:, 0])]
        ink = np.array(se.color, np.float32)
        d = ink - paper
        dd = float(d @ d)
        if dd < 400:  # ink indistinguishable from paper: nothing to refine against
            continue
        xs = np.arange(int(np.ceil(lp[0, 0])), int(np.floor(lp[-1, 0])) + 1)
        y0 = np.interp(xs, lp[:, 0], lp[:, 1])
        # Columns inside a gap of the trace stay out.
        gi = np.clip(np.searchsorted(lp[:, 0], xs), 1, len(lp) - 1)
        ok = (lp[gi, 0] - lp[gi - 1, 0]) <= 2.5 / s + 1
        R = int(max(3, round(2.5 / s)))
        out = []
        for x, yc, good in zip(xs, y0, ok):
            if not good or x < 0 or x >= W:
                continue
            ya, yb = max(0, int(round(yc)) - R - 4), min(H, int(round(yc)) + R + 5)
            col = imf[ya:yb, x]
            rel = col - paper
            t = (rel @ d) / dd
            off = np.linalg.norm(rel - t[:, None] * d[None], axis=1) / math.sqrt(dd)
            w = np.where((off < 0.3) & (t > 0.15), np.clip(t, 0, 1), 0.0)
            ys = np.arange(ya, yb, dtype=np.float32)
            # The run of ink nearest the network's estimate.
            on = w > 0.3
            if not on.any():
                out.append((x, yc))
                continue
            idx = np.nonzero(on)[0]
            near = idx[np.argmin(np.abs(ys[idx] - yc))]
            lo = hi = near
            while lo > 0 and w[lo - 1] > 0.05:
                lo -= 1
            while hi < len(w) - 1 and w[hi + 1] > 0.05:
                hi += 1
            if lo == 0 or hi == len(w) - 1:
                out.append((x, yc))  # the run continues past the window: steep or merged, trust the net
                continue
            ww = w[lo:hi + 1]
            yr = float((ww * ys[lo:hi + 1]).sum() / ww.sum())
            at_vertex = False
            if vh is not None:
                cx, cy = apply(ex.M, [[x, yc]])[0]
                ix, iy = int(round(cx)), int(round(cy))
                if 1 <= ix < vh.shape[1] - 1 and 1 <= iy < vh.shape[0] - 1:
                    at_vertex = vh[iy - 1:iy + 2, ix - 1:ix + 2].max() > keep_vertex
            if at_vertex or abs(yr - yc) > max(1.5, 1.0 / s):
                out.append((x, yc))
            else:
                out.append((x, yr))
        if out:
            se.line_px = np.array(out, float)
    return ex
