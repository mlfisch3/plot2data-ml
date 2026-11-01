"""From PlotNet outputs to geometry: plot frame, ticks, tick-label boxes, series.

Everything here works in canvas pixels and is mapped back to the source image
at the end through the inverse of the placement transform. Positions are
sub-pixel: peaks and ridges are refined by fitting a parabola to the log of the
heat around the maximum, which is exact for a Gaussian.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
import torch
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

from .data import (CANVAS_H, CANVAS_W, H_CORNER, H_LINE, H_MARKER, H_VERTEX, H_XTICK, H_YTICK, MEAN, STD, apply,
                   placement)
from .synth.mpl_render import DATA, GRID, LEGEND_SYMBOL, TEXT, TICK_LABEL


@dataclass
class Series:
    kind: str  # "line" or "scatter" ("line" may also carry markers)
    line_px: np.ndarray  # N x 2 (x, y) in source pixels, one per canvas column, NaN-free
    markers_px: np.ndarray  # M x 2 in source pixels
    color: tuple[int, int, int] = (0, 0, 0)
    support: int = 0
    vertices_px: np.ndarray | None = None  # sharp corners found by the vertex head, kept exactly
    fallback_frac: float = 1.0  # share of columns the source-pixel measurement left to the network
    ridge_px: np.ndarray | None = None  # N x 3 (x, top, bottom): the vertical extent of the network's ridge per canvas column, source px
    marker_info: object = None  # markers.SeriesMarkers once the markers were measured on the pixels


@dataclass
class Extraction:
    M: np.ndarray
    plot_area: list[float] | None  # x0, y0, x1, y1 in source px
    xticks: list[dict] = field(default_factory=list)  # {pos, anchor, score, label_box}
    yticks: list[dict] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    raw: dict | None = None
    loose_labels: list[list[float]] = field(default_factory=list)  # tick-label text no tick claimed, source px
    loose_markers: np.ndarray | None = None  # marker peaks no series took (unlabelled, singletons), source px


def prepare(img: np.ndarray, native: bool = True) -> tuple[torch.Tensor, np.ndarray]:
    """RGB uint8 image -> normalised canvas tensor and the placement transform."""
    h, w = img.shape[:2]
    M, (cw, ch) = placement(w, h, native)
    bg = np.full((ch, cw, 3), img[0, 0], np.float32)
    valid = cv2.warpAffine(np.ones((h, w), np.uint8), M, (cw, ch), flags=cv2.INTER_NEAREST)
    c = cv2.warpAffine(img, M, (cw, ch), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    c = np.where(valid[..., None] > 0, c, bg)
    x = (c - MEAN) / STD
    return torch.from_numpy(x.transpose(2, 0, 1).copy())[None], M


def run_net(net, img: np.ndarray, device="cuda", native: bool = True) -> tuple[dict, np.ndarray]:
    x, M = prepare(img, native)
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
        # Glyphs, not specks: the class bleeds onto tick marks next to the labels, and a
        # tick mark is a sliver (the dilation above adds 2 to the height and 4 to the width).
        if a < 12 or h < 6 or w < 6:
            continue
        boxes.append([x + 0.5, y + 0.5, x + w - 1.5, y + h - 1.5])  # undo the dilation's growth
    return boxes


def group_labels(ticks: list[tuple[float, float, float]], boxes: list[list[float]], horizontal: bool):
    """The label box of each tick: the union of the text pieces that belong to it.

    A label's glyphs can come apart into several pieces. Each piece goes to the
    tick nearest it along the axis (labels are centred on, or at least closest
    to, their own tick), provided it sits in that tick's label row or column;
    the union of a tick's pieces is its label. Pieces of one row are kept to the
    row of the piece nearest the tick, so an axis title below cannot join.
    """
    out: list[list[float] | None] = [None] * len(ticks)
    if not ticks or not boxes:
        return out
    along = np.array([t[0] if horizontal else t[1] for t in ticks])
    across = np.array([t[1] if horizontal else t[0] for t in ticks])
    members: dict[int, list[list[float]]] = {}
    for b in boxes:
        c_al = (b[0] + b[2]) / 2 if horizontal else (b[1] + b[3]) / 2
        c_ac = (b[1] + b[3]) / 2 if horizontal else (b[0] + b[2]) / 2
        i = int(np.argmin(np.abs(along - c_al)))
        if abs(c_ac - across[i]) > (60 if horizontal else 220):
            continue
        # A piece reaching the axis line is a tick mark the text class bled onto: labels sit a padding away.
        lo_ac, hi_ac = (b[1], b[3]) if horizontal else (b[0], b[2])
        if lo_ac - 1 <= across[i] <= hi_ac + 1:
            continue
        members.setdefault(i, []).append(b)
    # Specks much smaller than this axis's typical piece of text are bits of tick marks the
    # text class bled onto, not glyphs.
    areas = [(b[2] - b[0]) * (b[3] - b[1]) for bs in members.values() for b in bs]
    floor = 0.3 * float(np.median(areas)) if areas else 0.0
    for i, bs in members.items():
        bs = [b for b in bs if (b[2] - b[0]) * (b[3] - b[1]) >= floor] or bs
        # Start from the piece nearest the tick, then take the pieces in the same row.
        key = (lambda b: abs((b[0] + b[2]) / 2 - along[i]) + abs((b[1] + b[3]) / 2 - across[i])) if horizontal else \
              (lambda b: abs((b[1] + b[3]) / 2 - along[i]) + 0.2 * abs((b[0] + b[2]) / 2 - across[i]))
        bs = sorted(bs, key=key)
        a = list(bs[0])
        for b in bs[1:]:
            h = max(a[3] - a[1], b[3] - b[1])
            if horizontal:
                same_row = min(a[3], b[3]) - max(a[1], b[1]) > 0.4 * h
                near = b[0] - a[2] < 1.2 * h and a[0] - b[2] < 1.2 * h
            else:
                same_row = min(a[3], b[3]) - max(a[1], b[1]) > 0.4 * h
                near = b[0] - a[2] < 1.2 * h and a[0] - b[2] < 1.2 * h
            if same_row and near:
                a = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
        out[i] = a
    return out


def cluster_embeddings(e: np.ndarray, weight: np.ndarray, radius: float = 1.5, min_support: int = 20,
                       max_k: int = 16, sample: int = 6000, max_seeds: int = 200) -> np.ndarray:
    """Greedy mean-shift: seed at the strongest unassigned pixel, refine its centre, take its ball.

    Centres are found on a weighted subsample, so the cost does not grow with the
    image; a seed whose ball is too small is retired with its whole ball, so noise
    cannot make the search quadratic. Every pixel then joins its nearest centre,
    if one is within the radius.
    """
    n = len(e)
    rng = np.random.default_rng(0)
    if n > sample:
        p = weight + 1e-6
        idx = rng.choice(n, sample, replace=False, p=p / p.sum())
    else:
        idx = np.arange(n)
    es, ws = e[idx], weight[idx]
    scale = len(idx) / n
    support = max(3, int(round(min_support * scale)))
    taken = np.zeros(len(idx), bool)
    order = np.argsort(-ws)
    centres = []
    seeds = 0
    for s0 in order:
        if len(centres) >= max_k or seeds >= max_seeds:
            break
        if taken[s0]:
            continue
        seeds += 1
        free = ~taken
        c = es[s0]
        for _ in range(5):
            d = np.linalg.norm(es - c, axis=1)
            sel = free & (d < radius)
            if not sel.any():
                break
            c = np.average(es[sel], axis=0, weights=ws[sel] + 1e-6)
        d = np.linalg.norm(es - c, axis=1)
        sel = free & (d < radius)
        taken |= sel
        taken[s0] = True
        if sel.sum() >= support:
            centres.append(c)
    lab = np.full(n, -1, np.int32)
    if centres:
        C = np.array(centres)
        d = np.linalg.norm(e[:, None, :] - C[None], axis=2)
        k = d.argmin(1)
        ok = d[np.arange(n), k] < radius
        lab[ok] = k[ok]
        # A centre that ends up with too few pixels is dropped, and the labels renumbered.
        counts = np.bincount(lab[lab >= 0], minlength=len(C))
        keep = np.nonzero(counts >= min_support)[0]
        remap = np.full(len(C), -1, np.int32)
        remap[keep] = np.arange(len(keep))
        lab = np.where(lab >= 0, remap[np.maximum(lab, 0)], -1)
    return lab


def _axis_labels_in_strip(boxes: list[list[float]], frame: list[float] | None, horizontal: bool) -> list[list[float]]:
    """The subset of label boxes that sit in `axis`'s label strip (left of plot for y, below for x)."""
    if frame is None:
        return []
    fx0, fy0, fx1, fy1 = frame
    fw = max(1.0, fx1 - fx0)
    fh = max(1.0, fy1 - fy0)
    out = []
    for b in boxes:
        bx0, by0, bx1, by1 = b
        cx = 0.5 * (bx0 + bx1)
        cy = 0.5 * (by0 + by1)
        bw = bx1 - bx0
        bh = by1 - by0
        if horizontal:
            if cy <= fy1 - 1 or cy > fy1 + 0.2 * fh + 60:
                continue
            if by0 > fy1 + max(40, 3 * bh):
                continue
            if cx < fx0 - 2 or cx > fx1 + 2:
                continue
        else:
            if cx >= fx0 - 1 or cx < fx0 - 0.25 * fw - 60:
                continue
            if bx1 < fx0 - max(40, 3 * bw):
                continue
            if cy < fy0 - 2 or cy > fy1 + 2:
                continue
        out.append(b)
    return out


def _needs_axis_fallback(frame: list[float] | None, boxes: list[list[float]],
                         pk_strong: list[tuple[float, float, float]], horizontal: bool) -> bool:
    """Would the strong peaks claim all the axis-strip label boxes? If not, run the weak pass."""
    strip = _axis_labels_in_strip(boxes, frame, horizontal)
    if not strip:
        return False
    unclaimed = 0
    for b in strip:
        c = 0.5 * (b[0] + b[2]) if horizontal else 0.5 * (b[1] + b[3])
        if not any(abs((px if horizontal else py) - c) < 6 for px, py, _ in pk_strong):
            unclaimed += 1
    # Fire when at least 2 label boxes have no strong peak at their position: a run-of-the-mill
    # chart whose heat already caught every label stays with the strong-only path.
    return unclaimed >= 2


def _peak_has_label(x: float, y: float, boxes: list[list[float]], horizontal: bool,
                    frame: list[float] | None) -> bool:
    """A tick peak is kept at the lower threshold only when it aligns with a label in the axis strip."""
    strip = _axis_labels_in_strip(boxes, frame, horizontal)
    for b in strip:
        if horizontal:
            if b[0] - 3 <= x <= b[2] + 3 and y >= b[1] - 20 and y <= b[1] + 10:
                return True
        else:
            if b[1] - 3 <= y <= b[3] + 3 and x >= b[2] - 10 and x <= b[2] + 20:
                return True
    return False


def _promote_label_only_ticks(ex: Extraction, boxes: list[list[float]], claimed: list[list[float]],
                              frame: list[float] | None, Mi: np.ndarray) -> None:
    """Add virtual ticks at label-box centres where the tick heatmap missed them.

    FRED and other web renderers draw axis labels without visible tick marks, which
    starves the YTICK / XTICK heat on real-world screenshots: it crosses the 0.3 peak
    threshold at only one or two of the labels and the rest are lost. The semantic
    tick-label layer still sees them, so an unclaimed label box positioned where an
    axis label belongs (left of the plot for a y label, below the plot for an x label)
    becomes a tick at its own centre. refine_labels then re-measures the label on
    the source pixels; the OCR reads it; the axis decoder picks it up.

    All inputs are in canvas coordinates; `Mi` maps canvas back to source for the
    stored tick anchor and label box.
    """
    if frame is None:
        return
    fx0, fy0, fx1, fy1 = frame
    fw = max(1.0, fx1 - fx0)
    fh = max(1.0, fy1 - fy0)
    for key, horizontal in (("xticks", True), ("yticks", False)):
        existing_pos = [t["pos"] for t in getattr(ex, key)]
        promoted: list[tuple[float, list[float]]] = []  # (pos_src, canvas_box)
        for b in boxes:
            if any(b[0] >= c[0] - 1 and b[2] <= c[2] + 1 and b[1] >= c[1] - 1 and b[3] <= c[3] + 1 for c in claimed):
                continue
            bx0, by0, bx1, by1 = b
            cx = 0.5 * (bx0 + bx1)
            cy = 0.5 * (by0 + by1)
            bw = bx1 - bx0
            bh = by1 - by0
            if horizontal:
                # x label: sits below the plot, horizontally inside it, close to the axis line.
                if cy <= fy1 - 1 or cy > fy1 + 0.2 * fh + 60:
                    continue
                if by0 > fy1 + max(40, 3 * bh):
                    continue
                if cx < fx0 - 2 or cx > fx1 + 2:
                    continue
                anchor_cv = (cx, fy1)
                pos_cv = cx
            else:
                # y label: sits left of the plot, vertically inside it, not deep enough to be a title.
                if cx >= fx0 - 1 or cx < fx0 - 0.25 * fw - 60:
                    continue
                if bx1 < fx0 - max(40, 3 * bw):
                    continue
                if cy < fy0 - 2 or cy > fy1 + 2:
                    continue
                anchor_cv = (fx0, cy)
                pos_cv = cy
            # Deduplicate: if another promoted box shares a row/column, keep the one closer to the
            # axis (its box sits in the real label strip, not an axis title piece further out).
            dup = None
            for i, (p, bc) in enumerate(promoted):
                if abs(p - pos_cv) < 4:
                    dup = i
                    break
            if dup is not None:
                p, bc = promoted[dup]
                if horizontal:
                    # Prefer the box closer to the axis line (smaller cy).
                    bc_cy = 0.5 * (bc[1] + bc[3])
                    if cy < bc_cy:
                        promoted[dup] = (pos_cv, b)
                else:
                    bc_cx = 0.5 * (bc[0] + bc[2])
                    # Prefer the box closer to the axis line (larger cx; axis is on the left).
                    if cx > bc_cx:
                        promoted[dup] = (pos_cv, b)
                continue
            promoted.append((pos_cv, b))
        for pos_cv, b in promoted:
            # Dedupe against ticks that already came from the heat.
            src = apply(Mi, [[0.5 * (b[0] + b[2]) if horizontal else fx0,
                              fy1 if horizontal else 0.5 * (b[1] + b[3])]])[0]
            pos_src = float(src[0] if horizontal else src[1])
            if any(abs(pos_src - p) < 4 for p in existing_pos):
                continue
            q = apply(Mi, [[b[0], b[1]], [b[2], b[3]]])
            lb_src = [q[0, 0], q[0, 1], q[1, 0], q[1, 1]]
            getattr(ex, key).append(dict(pos=pos_src, anchor=src.tolist(), score=0.0, label_box=lb_src))
            existing_pos.append(pos_src)
            claimed.append(b)


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
    claimed: list[list[float]] = []
    for ch, key in ((H_XTICK, "xticks"), (H_YTICK, "yticks")):
        # Primary peaks (strong detections). FRED-style web renderers draw labels without
        # visible tick marks, so a lower threshold is tried as a secondary pass, with each
        # weak peak kept only if it lines up with a tick-label box.
        pk_strong = peaks(heat[ch], 0.3, nms=3)
        pk = list(pk_strong)
        if _needs_axis_fallback(frame, boxes, pk_strong, key == "xticks"):
            weak = peaks(heat[ch], 0.1, nms=3)
            for (x, y, sc) in weak:
                if sc >= 0.3:
                    continue  # already in pk_strong
                if any(abs(x - sx) < 4 and abs(y - sy) < 4 for sx, sy, _ in pk_strong):
                    continue
                if _peak_has_label(x, y, boxes, key == "xticks", frame):
                    pk.append((x, y, sc))
        for (x, y, sc), lb in zip(pk, group_labels(pk, boxes, key == "xticks")):
            src = apply(Mi, [[x, y]])[0]
            if lb is not None:
                claimed.append(lb)
                q = apply(Mi, [[lb[0], lb[1]], [lb[2], lb[3]]])
                lb = [q[0, 0], q[0, 1], q[1, 0], q[1, 1]]
            getattr(ex, key).append(dict(pos=float(src[0] if key == "xticks" else src[1]), anchor=src.tolist(),
                                         score=sc, label_box=lb))

    # Final fallback: promote unclaimed label boxes positioned like axis labels to virtual
    # ticks. Covers charts where even the weak-peak pass found nothing on an axis (no tick
    # marks drawn and the heatmap collapses to noise).
    _promote_label_only_ticks(ex, boxes, claimed, frame, Mi)

    # Label text no tick took: where an axis multiplier ("1e6") or offset is printed.
    for b in boxes:
        if not any(b[0] >= c[0] - 1 and b[2] <= c[2] + 1 and b[1] >= c[1] - 1 and b[3] <= c[3] + 1 for c in claimed):
            q = apply(Mi, [[b[0], b[1]], [b[2], b[3]]])
            ex.loose_labels.append([q[0, 0], q[0, 1], q[1, 0], q[1, 1]])

    # --- series ---
    H, W = heat.shape[1:]
    lh = heat[H_LINE]
    mh = heat[H_MARKER]
    # Where data can be: around the frame, with a margin, since on a chart without axis lines
    # the frame is a guess that is often 5 to 25 px off and a tight window clips the series at
    # its edges. What the margin lets in (legend symbols, text, tick labels) is kept out by
    # the class the network gives those pixels, not by where they are.
    if frame is not None:
        fx0, fy0, fx1, fy1 = frame
        m = max(3, int(round(0.05 * max(fx1 - fx0, fy1 - fy0))))
        roi = np.zeros((H, W), bool)
        roi[max(0, int(fy0) - m): int(fy1) + m + 1, max(0, int(fx0) - m): int(fx1) + m + 1] = True
    else:
        roi = np.ones((H, W), bool)
    furniture = (sem[LEGEND_SYMBOL] > 0.5) | (sem[TICK_LABEL] > 0.5) | (sem[TEXT] > 0.5)
    roi &= ~furniture
    ink = (lh > line_thr) & roi
    # A marker peak that lands on a pixel the network classes as text more strongly than data
    # (sem[TEXT] >= sem[DATA]) is almost certainly a glyph the heat triggered on: digits of value
    # labels, the printed end values on real charts, text annotations. The curator's measurement on
    # mpl-val GT sem maps gave a 0.02% false-veto rate for this condition (3 of 15,781 markers),
    # against 1.26% if we also include LEGEND_SYMBOL/TICK_LABEL, so we keep the condition to TEXT.
    mpk = [p for p in peaks(mh, marker_thr, nms=2)
           if roi[int(round(p[1])), int(round(p[0]))]
           and sem[TEXT, int(round(p[1])), int(round(p[0]))] < sem[DATA, int(round(p[1])), int(round(p[0]))]]
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

    # Lines: within each embedding cluster, follow continuous chains of ridge runs;
    # then join chains end to end across clusters where the ends meet.
    frags = []
    for k in range(lab.max() + 1):
        sel = line_lab == k
        if sel.sum() < 15:
            continue
        mask = np.zeros((H, W), bool)
        mask[pts[sel, 1], pts[sel, 0]] = True
        for chain in peel_chains(column_runs(mask, lh)):
            cols = np.array([c for c, _, _, _ in chain], float)
            ys = np.array([y for _, y, _, _ in chain], float)
            yi = np.round(ys).astype(int).clip(0, H - 1)
            e_mean = emb[:, yi, cols.astype(int)].mean(1)
            frags.append({"cols": cols, "ys": ys, "emb": e_mean, "k": k, "q": float(lh[yi, cols.astype(int)].mean()),
                          "spans": [(a, b) for _, _, a, b in chain]})
    lines = drop_duplicates(merge_fragments(frags), min_cols=max(12, int(0.04 * (frame[2] - frame[0])) if frame else 12))
    # A gridline (the minor decades of a log axis, say) can carry a ridge too; the class says what it is.
    lines = [f for f in lines if not _mostly(f, sem[GRID] > 0.5)]
    # A row of markers drawn touching looks like a line. A real line also runs between its markers.
    if mpk:
        mxy = np.array([[p[0], p[1]] for p in mpk])
        tree = cKDTree(mxy)
        keep_lines = []
        for f in lines:
            d, _ = tree.query(np.column_stack([f["cols"], f["ys"]]))
            # Only a weak ridge can be a row of markers: a drawn line through markers has a strong one.
            if (d > 6.0).mean() >= 0.2 or f.get("q", 1.0) >= 0.6:
                keep_lines.append(f)
        lines = keep_lines
    vpk = [p for p in peaks(heat[H_VERTEX], 0.3, nms=2) if roi[int(round(p[1])), int(round(p[0]))]]
    for f in lines:
        snap_vertices(f, vpk)
    # Each marker goes to at most one line: one of its own cluster that it sits on.
    # The rest form scatter series, one per cluster.
    owner = np.full(len(mpk), -1)
    for li, f in enumerate(lines):
        for i in np.nonzero(np.isin(mk_lab, f["ks"]) & (owner < 0))[0]:
            x, y = mpk[i][0], mpk[i][1]
            if f["cols"][0] - 2 <= x <= f["cols"][-1] + 2 and abs(np.interp(x, f["cols"], f["ys"]) - y) < 4:
                owner[i] = li
    for li, f in enumerate(lines):
        mk = np.array([[mpk[i][0], mpk[i][1]] for i in np.nonzero(owner == li)[0]]).reshape(-1, 2)
        se = _make_series("line", np.column_stack([f["cols"], f["ys"]]), mk, Mi, img)
        if f.get("vertices"):
            se.vertices_px = apply(Mi, f["vertices"])
        sp = np.array(f["spans"], float).reshape(-1, 2)
        top = apply(Mi, np.column_stack([f["cols"], sp[:, 0] - 0.5]))
        bot = apply(Mi, np.column_stack([f["cols"], sp[:, 1] + 0.5]))
        se.ridge_px = np.column_stack([top[:, 0], top[:, 1], bot[:, 1]])
        ex.series.append(se)
    scatters = []
    taken = owner >= 0
    for k in range(lab.max() + 1):
        sel = np.nonzero((mk_lab == k) & (owner < 0))[0]
        mk = np.array([[mpk[i][0], mpk[i][1]] for i in sel]).reshape(-1, 2)
        if len(mk) >= 2:
            scatters.append(_make_series("scatter", np.zeros((0, 2)), mk, Mi, img))
            taken[sel] = True
    ex.series += merge_by_colour(scatters, img)
    loose = np.array([[mpk[i][0], mpk[i][1]] for i in np.nonzero(~taken)[0]]).reshape(-1, 2)
    ex.loose_markers = apply(Mi, loose) if len(loose) else np.zeros((0, 2))
    return ex


def _mostly(f: dict, mask: np.ndarray, frac: float = 0.5) -> bool:
    """Whether more than `frac` of a traced line's pixels fall where `mask` is set."""
    H, W = mask.shape
    xi = np.clip(np.round(f["cols"]).astype(int), 0, W - 1)
    yi = np.clip(np.round(f["ys"]).astype(int), 0, H - 1)
    return float(mask[yi, xi].mean()) > frac


def _make_series(kind: str, line_canvas: np.ndarray, mk: np.ndarray, Mi: np.ndarray, img) -> Series:
    color = (0, 0, 0)
    pts = line_canvas if len(line_canvas) else mk
    if img is not None and len(pts):
        src = apply(Mi, pts)
        xi = np.clip(np.round(src[:, 0]).astype(int), 0, img.shape[1] - 1)
        yi = np.clip(np.round(src[:, 1]).astype(int), 0, img.shape[0] - 1)
        color = tuple(int(v) for v in np.median(img[yi, xi], 0))
    return Series(kind=kind, line_px=apply(Mi, line_canvas) if len(line_canvas) else np.zeros((0, 2)),
                  markers_px=apply(Mi, mk) if len(mk) else np.zeros((0, 2)), color=color,
                  support=int(len(line_canvas) + len(mk)))


def column_runs(mask: np.ndarray, heat: np.ndarray) -> dict[int, list[tuple[int, int, float, float]]]:
    """Per column, the vertical runs of a series mask: (top, bottom, centre y, heat mass).

    A short run is a crossing of a shallow stretch of line, and its centre is the
    sub-pixel ridge (a parabola through the log heat). A long run is a steep
    stretch passing through the whole column, and its centre is the middle of
    the heat it holds.
    """
    out: dict[int, list] = {}
    H = mask.shape[0]
    for c in np.nonzero(mask.any(0))[0]:
        col = mask[:, c]
        d = np.diff(np.concatenate([[0], col.view(np.int8), [0]]))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
        runs = []
        for a, b in zip(starts, ends):
            h = heat[a:b + 1, c]
            if b - a <= 5:
                r = a + int(np.argmax(h))
                y = float(r)
                if 0 < r < H - 1:
                    lg = np.log(np.clip(heat[r - 1:r + 2, c], 1e-6, 1))
                    y += _parabola_offset(*lg)
            else:
                y = float((h * np.arange(a, b + 1)).sum() / max(h.sum(), 1e-9))
            runs.append((int(a), int(b), y, float(h.sum())))
        out[int(c)] = runs
    return out


def peel_chains(runs: dict, gap_pen: float = 0.5, skip_pen: float = 0.3, max_skip: int = 12,
                min_cols: int = 8) -> list[list[tuple[int, float, int, int]]]:
    """Best chains of runs, one run per column, by dynamic programming; repeated on what is left.

    A chain's score is the heat it collects, minus `gap_pen` per pixel of vertical
    gap between consecutive runs (touching runs cost nothing, as a continuous
    curve's do) and `skip_pen` per empty column jumped over.
    """
    runs = {c: list(r) for c, r in runs.items() if r}
    chains = []
    while runs:
        cols = sorted(runs)
        best: dict[tuple[int, int], tuple[float, tuple[int, int] | None]] = {}
        top = (-1.0, None)
        for ci, c in enumerate(cols):
            for i, (a, b, y, m) in enumerate(runs[c]):
                score, back = m, None
                for pj in range(ci - 1, -1, -1):
                    pc = cols[pj]
                    if c - pc - 1 > max_skip:
                        break
                    for j, (pa, pb, py, pm) in enumerate(runs[pc]):
                        prev = best.get((pc, j))
                        if prev is None:
                            continue
                        gap = max(0, a - pb - 1, pa - b - 1)
                        cand = prev[0] + m - gap_pen * gap - skip_pen * (c - pc - 1)
                        if cand > score:
                            score, back = cand, (pc, j)
                best[(c, i)] = (score, back)
                if score > top[0]:
                    top = (score, (c, i))
        if top[1] is None:
            break
        chain = []
        node = top[1]
        while node is not None:
            c, i = node
            a, b, y, m = runs[c][i]
            chain.append((c, y, a, b))
            node = best[node][1]
        chain.reverse()
        if len(chain) < min_cols:
            break
        chains.append(chain)
        for c, _, a, _b in chain:
            runs[c] = [r for r in runs[c] if r[0] != a]
            if not runs[c]:
                del runs[c]
    return chains


def snap_vertices(f: dict, vpk: list[tuple[float, float, float]]) -> None:
    """Put each detected polyline vertex lying on this line into it, exactly.

    In the column through a sharp peak the ridge run spans both flanks, and any
    single number taken from it lands short of the tip. The vertex head marks
    the tip itself; the samples it makes ambiguous (the long runs within a
    column of it) are replaced by it.
    """
    if not vpk or len(f["cols"]) < 3:
        return
    cols, ys = f["cols"], f["ys"]
    spans = f["spans"]
    add_x, add_y, drop = [], [], np.zeros(len(cols), bool)
    for vx, vy, _ in vpk:
        i = int(np.argmin(np.abs(cols - vx)))
        if abs(cols[i] - vx) > 1.0:
            continue
        a, b = spans[i]
        if not (a - 2 <= vy <= b + 2):
            continue
        add_x.append(vx)
        add_y.append(vy)
        near = np.abs(cols - vx) <= 1.0
        long_run = np.array([sb - sa > 3 for sa, sb in spans])
        drop |= near & long_run
    if not add_x:
        return
    keep = ~drop
    x = np.concatenate([cols[keep], add_x])
    y = np.concatenate([ys[keep], add_y])
    sp = [sp for sp, k in zip(spans, keep) if k] + [(int(np.floor(v)), int(np.ceil(v))) for v in add_y]
    o = np.argsort(x, kind="stable")
    f["cols"], f["ys"] = x[o], y[o]
    f["vertices"] = list(zip(add_x, add_y))
    f["spans"] = [sp[i] for i in o]


def drop_duplicates(lines: list[dict], min_cols: int = 12, tol: float = 3.0, min_q: float = 0.35,
                    window: int = 4) -> list[dict]:
    """Drop traces that are too short or too faint to be a series, or that run inside a longer one.

    A thick or jagged stroke leaves runs beside the chain that took it - the far
    flank of every spike - and they chain up into a ghost trace through the
    valleys. Such a trace stays inside the envelope of the longer trace (its
    extent over a few neighbouring columns), so that is the test. Text beside a
    line can chain up into a scrap, which the ridge confidence gives away.
    """
    lines = [f for f in lines if len(f["cols"]) >= min_cols and f.get("q", 1.0) >= min_q]
    lines.sort(key=lambda f: -len(f["cols"]))
    kept: list[dict] = []
    for f in lines:
        dup = False
        for g in kept:
            inside = (f["cols"] >= g["cols"][0]) & (f["cols"] <= g["cols"][-1])
            if inside.mean() < 0.6:
                continue
            gi = np.searchsorted(g["cols"], f["cols"][inside])
            lo = np.array([g["ys"][max(0, i - window): i + window + 1].min() for i in gi])
            hi = np.array([g["ys"][max(0, i - window): i + window + 1].max() for i in gi])
            y = f["ys"][inside]
            if ((y >= lo - tol) & (y <= hi + tol)).mean() >= 0.7:
                dup = True
                break
        if not dup:
            kept.append(f)
    return kept


def merge_by_colour(series: list[Series], img, tol: float = 45.0) -> list[Series]:
    """Scatter clusters drawn in the same colour are one series.

    Embeddings separate series well where they are drawn close together, but a
    marker cloud spread over the whole plot can come apart into several clusters;
    the colour it was drawn in does not.
    """
    if img is None or len(series) < 2:
        return series
    out: list[Series] = []
    for s in sorted(series, key=lambda s: -len(s.markers_px)):
        c = np.array(s.color, float)
        for o in out:
            if np.linalg.norm(np.array(o.color, float) - c) < tol:
                o.markers_px = np.vstack([o.markers_px, s.markers_px])
                o.support += s.support
                break
        else:
            out.append(s)
    return out


def _end_slope(cols: np.ndarray, ys: np.ndarray, k: int, head: bool) -> float:
    """Least-squares slope through the first (or last) k samples of a chain."""
    sel = slice(0, k) if head else slice(-k, None)
    x, y = cols[sel], ys[sel]
    if len(x) < 2 or x[-1] == x[0]:
        return 0.0
    A = np.column_stack([x - x.mean(), np.ones(len(x))])
    return float(np.linalg.lstsq(A, y, rcond=None)[0][0])


def _join_cost(A: dict, B: dict, emb_tol: float = 3.0, max_dx: int = 90) -> float | None:
    """Cost of B continuing A, or None if the pair cannot be one series.

    Fragmentation shows up in two shapes:

    - A short gap between an A that ends before B starts (dx > 0). The frozen
      rule is right here: the pixel ranges of A's last run and B's first run
      must meet (``gap <= 3 + 2 dx``). The endpoint y positions are what the
      test should see; the endpoint slope at a turning point does not help.
      The rule is extended beyond ``dx = 60`` with a slope-extrapolation gate,
      which catches legend-occlusion stretches where the frozen rule would
      otherwise forbid the join only because of the length.

    - A long overlap where A and B span the same columns because an embedding
      cluster boundary ran through a continuous ridge. There both chains are
      halves of one ridge, so the y gap is nearly CONSTANT along the overlap
      (the two cluster labels pick the top and the bottom of the ridge, 1-6 px
      apart); a crossing has a y gap that varies with the local slopes. The
      median absolute deviation and the linear drift of the gap separate the
      two cases. The frozen rule's 8-column overlap stays as-is for short
      overlaps.

    Both branches use the embedding mean distance as a hard reject (same ridge
    sits in one embedding cluster of the discriminative loss) and no cost is
    returned for a pair that fails any threshold.
    """
    if B["cols"][-1] <= A["cols"][-1]:
        return None  # B does not extend beyond A
    if A["cols"][0] > B["cols"][0]:
        return None  # A does not start first
    de = float(np.linalg.norm(A["emb"] - B["emb"]))
    if de > emb_tol:
        return None
    if B["cols"][0] <= A["cols"][-1]:
        lo = int(np.ceil(B["cols"][0]))
        hi = int(np.floor(A["cols"][-1]))
        nov = hi - lo + 1
        if nov < 1:
            return None
        ov = np.arange(lo, hi + 1)
        diff = np.interp(ov, A["cols"], A["ys"]) - np.interp(ov, B["cols"], B["ys"])
        if nov <= 8:
            # Short overlap: frozen's max |diff| <= 2.5 is the test, unchanged.
            if np.abs(diff).max() > 2.5:
                return None
            return float(np.abs(diff).mean()) + de + 0.1
        # Long overlap: evidence that these are two halves of one ridge.
        if not set(A.get("ks", [])).isdisjoint(B.get("ks", [])):
            return None  # same-cluster overlap means two different series kept apart on purpose
        if A.get("q", 0.0) < 0.3 or B.get("q", 0.0) < 0.3:
            return None
        if A.get("n", len(A["cols"])) < 50 or B.get("n", len(B["cols"])) < 50:
            return None
        med = float(np.median(diff))
        mad = float(np.median(np.abs(diff - med)))
        a_lin, _ = np.polyfit(ov.astype(float), diff, 1)
        drift = float(abs(a_lin * (ov[-1] - ov[0])))
        if abs(med) > 6.0 or mad > 1.2 or drift > 2.5:
            return None
        return abs(med) + 2.0 * mad + 0.5 * drift + de + 0.0005 * nov
    # No overlap: B's start sits past A's end.
    dx = int(B["cols"][0] - A["cols"][-1])
    if dx > max_dx:
        return None
    a0, a1 = A["spans"][-1]
    b0, b1 = B["spans"][0]
    gap = max(0, b0 - a1 - 1, a0 - b1 - 1)
    if gap > 3 + 2.0 * dx:
        return None
    if dx > 60:
        sA = _end_slope(A["cols"], A["ys"], min(10, len(A["cols"])), head=False)
        sB = _end_slope(B["cols"], B["ys"], min(10, len(B["cols"])), head=True)
        geo = min(abs(A["ys"][-1] + sA * dx - B["ys"][0]),
                  abs(B["ys"][0] - sB * dx - A["ys"][-1]))
        tol = 2.5 + 0.25 * dx * (1.0 + min(abs(sA), abs(sB)))
        if geo > tol:
            return None
    # Normalise so a good join sits well under the no_join threshold.
    return 0.03 * (gap + dx) + de


def merge_fragments(frags: list[dict], emb_tol: float = 3.0, no_join: float = 5.0) -> list[dict]:
    """Join chain fragments that belong to one series.

    Pairs can meet at a small gap or share columns outright; `_join_cost`
    tests both. The joins are picked globally by linear assignment so one
    chain is not two series' continuation and two chains do not both claim
    the same successor.
    """
    items = [{"cols": f["cols"], "ys": f["ys"], "emb": f["emb"], "ks": [f["k"]], "n": len(f["cols"]),
              "spans": f["spans"], "q": f["q"]} for f in frags]
    n = len(items)
    if n < 2:
        return items
    C = np.full((n, n), np.inf)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            c = _join_cost(items[i], items[j], emb_tol=emb_tol)
            if c is not None:
                C[i, j] = c
    # 2n x 2n assignment: either continue into another chain or into one's own ghost.
    big = np.full((2 * n, 2 * n), 1e9)
    big[:n, :n] = C
    diag_no = np.where(np.eye(n, dtype=bool), no_join, 1e9)
    big[:n, n:] = diag_no  # row i's own "end here" ghost column
    big[n:, :n] = diag_no  # col j's own "start here" ghost row
    big[n:, n:] = 0.0
    ri, cj = linear_sum_assignment(big)
    nxt = {int(i): int(j) for i, j in zip(ri, cj) if i < n and j < n and C[i, j] < no_join}
    has_prev = set(nxt.values())
    out, seen = [], set()
    for i in range(n):
        if i in has_prev or i in seen:
            continue
        A = dict(items[i])
        seen.add(i)
        j = nxt.get(i)
        while j is not None and j not in seen:
            seen.add(j)
            B = items[j]
            keep = B["cols"] > A["cols"][-1]
            w = A["n"] / (A["n"] + B["n"])
            A["cols"] = np.concatenate([A["cols"], B["cols"][keep]])
            A["ys"] = np.concatenate([A["ys"], B["ys"][keep]])
            A["spans"] = A["spans"] + [sp for sp, k in zip(B["spans"], keep) if k]
            A["emb"] = w * A["emb"] + (1 - w) * B["emb"]
            A["ks"] = A["ks"] + B["ks"]
            A["q"] = w * A["q"] + (1 - w) * B["q"]
            A["n"] += int(keep.sum())
            j = nxt.get(j)
        out.append(A)
    return out


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


def refine_lines(img: np.ndarray, ex: Extraction) -> Extraction:
    """Re-measure each traced line on the source pixels, every column (see `measure.py`)."""
    from .measure import refine_lines as _refine

    return _refine(img, ex)


def refine_lines_v1(img: np.ndarray, ex: Extraction, keep_vertex: float = 0.3) -> Extraction:
    """The first refinement, kept for comparison: one centroid per source column within a window.

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
            pts = np.array(out, float)
            if se.vertices_px is not None and len(se.vertices_px):
                # The exact corners stay; the column samples within a pixel of them go.
                v = se.vertices_px
                far = np.min(np.abs(pts[:, 0][:, None] - v[None, :, 0]), axis=1) > 1.0
                pts = np.vstack([pts[far], v])
                pts = pts[np.argsort(pts[:, 0], kind="stable")]
            se.line_px = pts
    return ex


def _affine_from_marks(pos_net: np.ndarray, marks: np.ndarray, weights: np.ndarray,
                       slope_tol: float, resid_tol: float):
    """Fit `mark = a + b * pos_net` by iteratively reweighted least squares.

    Returns (a, b, inliers_mask, resid_mad). `b` is 1 for a pure-shift fit
    (always safe), returned when the data cannot pin a slope. Otherwise the full
    affine fit is returned, with outliers dropped at 2.5 * MAD or 0.5 px,
    whichever is larger. If fewer than 3 inliers remain or the residual MAD
    exceeds `resid_tol`, returns (None, None, None, None).

    `slope_tol` is the half-width of the trusted-slope window around 1.0:
    a fitted `|b - 1| > slope_tol` is taken as a sign that the data cannot
    identify the slope and the function returns a pure-shift fit instead.
    """
    n = len(pos_net)
    if n < 3:
        return None, None, None, None

    def _shift_only(mask):
        if mask.sum() < 3:
            return None
        d = marks[mask] - pos_net[mask]
        w = weights[mask]
        wsum = float(w.sum()) or 1.0
        a = float((d * w).sum() / wsum)
        resid = marks - (a + pos_net)
        mad = float(np.median(np.abs(resid[mask])))
        return a, 1.0, mask, mad

    inliers = np.ones(n, bool)
    full = None
    for _ in range(3):
        if inliers.sum() < 3:
            break
        p = pos_net[inliers]
        m = marks[inliers]
        w = weights[inliers]
        A = np.column_stack([np.ones(len(p)), p])
        try:
            WA = A * w[:, None]
            AtWA = WA.T @ A
            AtWm = WA.T @ m
            a, b = np.linalg.solve(AtWA, AtWm)
        except np.linalg.LinAlgError:
            break
        resid = marks - (float(a) + float(b) * pos_net)
        mad = float(np.median(np.abs(resid[inliers]))) if inliers.any() else 0.0
        tol = max(2.5 * mad, 0.5)
        new_in = np.abs(resid) <= tol
        full = (float(a), float(b), inliers.copy(), mad)
        if np.array_equal(new_in, inliers):
            break
        if new_in.sum() < 3:
            break
        inliers = new_in

    if full is None:
        return _shift_only(inliers) or (None, None, None, None)
    a, b, mask, mad = full
    # A fitted slope outside the identifiability window is noise; fall back to
    # the (always safe) pure-shift fit over the same inliers.
    if abs(b - 1.0) > slope_tol or mad > resid_tol:
        shifted = _shift_only(mask)
        if shifted is None:
            return None, None, None, None
        a_s, b_s, m_s, mad_s = shifted
        if mad_s > resid_tol:
            return None, None, None, None
        return a_s, b_s, m_s, mad_s
    return a, b, mask, mad


def refine_ticks(img: np.ndarray, ex: Extraction, search: float = 2.0, min_shift: float = 0.45,
                 max_spread: float = 0.45, resid_tol: float = 0.35, affine_min_marks: int | None = None) -> Extraction:
    """Correct an axis's ticks by one affine map fit to all drawn marks or gridlines on the axis.

    The network places a tick from everything around it, labels included, and
    the drawn tick mark or gridline is one more observation of where that tick
    actually sits. For a sparse axis with three or four marks the slope of
    network-against-mark is poorly identified; the fit then degenerates to a
    pure median shift and every tick moves by that shift, as before. For five
    or more marks the full affine `mark = a + b * pos_net` is fitted by
    iteratively reweighted least squares, outliers rejected at 2.5 * MAD or
    0.5 px (whichever is larger), and the slope accepted only when `|b - 1|`
    stays within an identifiability window that tightens with sqrt(N). When
    the slope leaves that window, the fit falls back to shift-only on the
    same inliers; nothing is applied when the residual MAD exceeds the
    tolerance (`resid_tol`) after either branch.

    Why joint fitting helps: a single pixel-snapped mark is good to about half
    a pixel. Averaging N marks' positions brings the shift down toward
    `0.5 / sqrt(N)` px; a scale correction, when the network's tick spacing
    drifts across the axis (a per-chart artefact of heatmap decoding at low
    resolution), is only visible to the joint fit.

    Two places are searched for a line: a narrow band hugging the axis on the
    outside, where a tick mark is and a label's padding keeps glyphs out, and
    the whole extent of the plot, where a gridline runs. A line must darken most
    of the band (the profile is a low percentile across it), so a glyph, or a
    data line crossing the band, cannot pass for one.

    None of this needs the plot frame: the axis is where the tick anchors are,
    the outside is the side the label sits on, and a gridline runs across the
    span of the other axis's ticks. The frame, when found, only widens that span.
    """
    # The slope term of the joint fit is the b-DOF. On data where the network
    # already matches the ticks up to the pixel-snap floor it has nothing to
    # fit and absorbs noise; the T3R2_SHIFT_ONLY env var pins the fit to b=1
    # so the ablation can be measured without rebuilding the branch.
    if affine_min_marks is None:
        affine_min_marks = 10**9 if int(os.environ.get("T3R2_SHIFT_ONLY", "0")) else 5
    g = img.astype(np.float32).mean(-1)
    H, W = g.shape
    if ex.plot_area is not None:
        x0, y0, x1, y1 = ex.plot_area
        paper = float(np.median(g[int(max(0, y0)):int(min(H, y1)), int(max(0, x0)):int(min(W, x1))]))
    else:
        x0 = y0 = x1 = y1 = None
        paper = float(_paper_colour(img, None).mean())

    def span(ticks, i, lo_frame, hi_frame):
        """The extent of the plot along an axis: the frame, else the other axis's ticks."""
        if lo_frame is not None:
            return lo_frame, hi_frame
        v = [t["anchor"][i] for t in ticks]
        return (min(v), max(v)) if len(v) >= 2 else (None, None)

    for key in ("xticks", "yticks"):
        ticks = getattr(ex, key)
        marks_data = []  # (pos_net, mark_pos, strength) over ticks with a drawn mark
        for t in ticks:
            p = t["pos"]
            lo, hi = int(np.floor(p - search - 1)), int(np.ceil(p + search + 1))
            best = None
            lb = t.get("label_box")
            if key == "yticks":
                if lo < 0 or hi >= H:
                    continue
                side = t["anchor"][0]
                if lb is not None:
                    left = (lb[0] + lb[2]) / 2 < side
                elif x0 is not None:
                    left = abs(side - x0) <= abs(side - x1)
                else:
                    left = None
                bands = []
                if left is not None:
                    bands.append(((int(side) - 4, int(side)) if left else (int(side) + 1, int(side) + 5)) + (20,))
                a0, a1 = span(ex.xticks, 0, x0, x1)
                if a0 is not None:
                    bands.append((int(a0) + 2, int(a1) - 1, 35))
                for a, b, q in bands:
                    a, b = max(0, a), min(W, b)
                    if b - a < 4:
                        continue
                    prof = np.percentile(np.abs(g[lo:hi + 1, a:b] - paper), q, axis=1)
                    best = _pick_line(prof, lo, p, search, best)
            else:
                if lo < 0 or hi >= W:
                    continue
                side = t["anchor"][1]
                if lb is not None:
                    below = (lb[1] + lb[3]) / 2 > side
                elif y0 is not None:
                    below = abs(side - y1) <= abs(side - y0)
                else:
                    below = None
                bands = []
                if below is not None:
                    bands.append(((int(side) + 1, int(side) + 5) if below else (int(side) - 4, int(side))) + (20,))
                a0, a1 = span(ex.yticks, 1, y0, y1)
                if a0 is not None:
                    bands.append((int(a0) + 2, int(a1) - 1, 35))
                for a, b, q in bands:
                    a, b = max(0, a), min(H, b)
                    if b - a < 4:
                        continue
                    prof = np.percentile(np.abs(g[a:b, lo:hi + 1] - paper), q, axis=0)
                    best = _pick_line(prof, lo, p, search, best)
            if best is not None:
                t["mark"] = best[1]
                t["mark_strength"] = best[0]
                marks_data.append((p, best[1], best[0]))
        if len(marks_data) < 3:
            continue
        pos_net = np.array([d[0] for d in marks_data], float)
        marks = np.array([d[1] for d in marks_data], float)
        strength = np.array([d[2] for d in marks_data], float)
        a_fit = b_fit = None
        # Slope identifiability tightens with sqrt(N): a 3-4 mark axis cannot
        # pin a slope at all, so b is forced to 1 and only the shift is read;
        # a 5+ mark axis is given a slope window that scales as 1/sqrt(N).
        n_marks = len(marks_data)
        if n_marks >= affine_min_marks:
            slope_tol = max(0.004, min(0.015, 0.015 * math.sqrt(5.0 / n_marks)))
            a_fit, b_fit, inliers, mad = _affine_from_marks(
                pos_net, marks, strength, slope_tol=slope_tol, resid_tol=resid_tol)
        else:
            a_fit, b_fit, inliers, mad = _affine_from_marks(
                pos_net, marks, strength, slope_tol=0.0, resid_tol=resid_tol)
        if a_fit is None:
            continue
        pos_all = np.array([t["pos"] for t in ticks], float)
        implied = np.abs((a_fit + b_fit * pos_all) - pos_all)
        if float(np.max(implied)) < min_shift:
            # The fitted correction is within sub-pixel noise; leave the
            # network's placement untouched, as before.
            continue
        # One last spread check preserves the behaviour that an axis whose
        # drawn marks disagree past the pixel-snap noise cannot be trusted
        # to pull every tick by one map.
        resid = marks - (a_fit + b_fit * pos_net)
        if float(np.median(np.abs(resid[inliers]))) > max_spread:
            continue
        for t in ticks:
            t["pos_net"] = t["pos"]
            t["pos"] = float(a_fit + b_fit * t["pos"])
            if key == "yticks":
                t["anchor"] = [t["anchor"][0], t["pos"]]
            else:
                t["anchor"] = [t["pos"], t["anchor"][1]]
    return ex


def _runs(idx: np.ndarray, gap: int) -> list[tuple[int, int]]:
    """Maximal runs of sorted indices, joined across gaps of at most `gap`."""
    out = []
    s = prev = int(idx[0])
    for c in idx[1:]:
        if c - prev - 1 > gap:
            out.append((s, prev))
            s = int(c)
        prev = int(c)
    out.append((s, prev))
    return out


def _nearest_run(runs: list[tuple[int, int]], rel: float) -> tuple[int, int]:
    return min(runs, key=lambda ge: 0 if ge[0] <= rel <= ge[1] else min(abs(ge[0] - rel), abs(ge[1] - rel)))


def _mask_tick_marks(ink: np.ndarray, max_h: int = 15, max_w: int = 6, isolate: int = 12) -> np.ndarray:
    """Remove narrow vertical streaks starting near the axis side (tick marks).

    An x-axis tick mark is one or two columns wide, extends a handful of rows outward
    from the axis, and does not reach the label text. If two tick marks appear at
    different `along` positions in the window, the per-row width used by `_row_shapes`
    sees them as one wide band (ink from leftmost to rightmost in the row) and the
    band finder takes it for the label. The band finder breaks that way on log axes
    where the tick marks sit between the axis and the text.

    Line rows (plot borders, grid, offset spines) are blanked first so tick marks that
    touch them become components of their own; a line is still a line in the per-row
    logic that _label_band uses. A narrow component is masked only when there is no
    ink in the same row range within `isolate` columns on either side, so narrow
    glyphs on either end of a label (the "1" of "1000", a trailing digit) are kept.
    """
    n, m = ink.shape
    # Rows made entirely of ink across the window are the plot border or a drawn line.
    # Zero them before the component walk so tick marks hanging off the border become
    # components of their own; the per-row logic still sees the lines later.
    row_count = ink.sum(1)
    cleaned = ink.copy()
    cleaned[row_count >= max(4, int(0.8 * m))] = False
    nlab, labels = cv2.connectedComponents(cleaned.astype(np.uint8))
    out = ink.copy()
    for i in range(1, nlab):
        where = labels == i
        rows, cols = np.where(where)
        if rows.size == 0:
            continue
        r0, r1 = int(rows.min()), int(rows.max())
        c0, c1 = int(cols.min()), int(cols.max())
        if r0 > 4 or (r1 - r0 + 1) > max_h or (c1 - c0 + 1) > max_w:
            continue
        # Does the component stand alone? A tick mark has empty space on both sides
        # at its own rows; a text glyph has its neighbours in the same row range.
        rs, re = r0, r1 + 1
        left_lo, left_hi = max(0, c0 - isolate), c0
        right_lo, right_hi = c1 + 1, min(m, c1 + 1 + isolate)
        if left_hi > left_lo and ink[rs:re, left_lo:left_hi].any():
            continue
        if right_hi > right_lo and ink[rs:re, right_lo:right_hi].any():
            continue
        out[where] = False
    return out


def _row_shapes(ink: np.ndarray, lo: int, hi: int) -> tuple[np.ndarray, np.ndarray]:
    """Per row of an [across, along] ink window: is it a drawn line (one continuous run of ink over at least
    80% of the along-extent [lo, hi], the plot's), and is it narrow (ink within 4 px, a tick mark's width)."""
    n, m = ink.shape
    line = np.zeros(n, bool)
    narrow = np.zeros(n, bool)
    span_ref = max(4, hi - lo + 1)
    for k in range(n):
        idx = np.nonzero(ink[k])[0]
        if len(idx) == 0:
            continue
        narrow[k] = idx[-1] - idx[0] + 1 <= 4
        if len(idx) >= 0.8 * span_ref:
            sub = idx[(idx >= lo) & (idx <= hi)]
            if len(sub) >= 2:
                # Lengths of the continuous runs of ink: the longest decides.
                breaks = np.nonzero(np.diff(sub) > 1)[0]
                longest = int(np.diff(np.concatenate([[-1], breaks, [len(sub) - 1]])).max())
                line[k] = longest >= 0.8 * span_ref
    return line, narrow


def _label_band(ink: np.ndarray, line: np.ndarray, narrow: np.ndarray, horizontal: bool, max_h: int) -> tuple[int, int] | None:
    """The across-extent [r0, r1] of the label band in an ink window indexed [across, along]."""
    count = ink.sum(1)
    n = len(count)
    k = 0
    # The plot edge can round to a row other than the spine's: an initial gap of up to 2 rows is still the axis.
    while k < min(n, 3) and count[k] == 0:
        k += 1
    # Attached to the axis: tick marks (narrow rows) and a spine. They end where the ink widens past a tick
    # mark's width, so a label touching its tick mark (a superscript rising into it) is not consumed.
    if k <= 2:
        while k < n and count[k] > 0 and (narrow[k] or line[k]):
            k += 1
    # The first run of ink after the gap starts the band; a drawn line there is an offset spine: past it and its ticks.
    while True:
        while k < n and count[k] == 0:
            k += 1
        if k >= n:
            return None
        if line[k]:
            while k < n and count[k] > 0 and (narrow[k] or line[k]):
                k += 1
            continue
        break
    r0 = r1 = k
    while r1 + 1 < n and count[r1 + 1] > 0 and not line[r1 + 1]:
        r1 += 1

    def along_extent(lo: int, hi: int) -> int:
        cols = np.nonzero(ink[lo:hi + 1].any(0))[0]
        return int(np.ptp(cols)) + 1 if len(cols) else 0

    # Widen the band across small gaps: between the glyphs of a y label or of a rotated x label (the text
    # height is the along-extent seen so far), or the dot of a "%" and the like in a horizontal x label.
    while r1 + 1 < n:
        w = along_extent(r0, r1)
        if horizontal and w > 1.3 * (r1 - r0 + 1):
            h_est = r1 - r0 + 1
            gap_max = max(1, int(0.3 * h_est))
        else:
            h_est = max(4, w)
            gap_max = max(2, int(round(0.6 * h_est)))
        nxt = r1 + 1
        while nxt < n and count[nxt] == 0 and nxt - r1 - 1 < gap_max:
            nxt += 1
        if nxt >= n or count[nxt] == 0 or line[nxt]:
            break
        e = nxt
        while e + 1 < n and count[e + 1] > 0 and not line[e + 1]:
            e += 1
        if not horizontal:
            # A run much taller along the axis than the text, or filling the window along the axis, is a
            # rotated axis title, not a glyph of the label.
            rows_along = np.nonzero(ink[nxt:e + 1].any(0))[0]
            if len(rows_along) and (np.ptp(rows_along) + 1 > 2.5 * h_est or
                                    (rows_along[0] == 0 and rows_along[-1] == ink.shape[1] - 1)):
                break
        r1 = e
        if r1 - r0 + 1 > max_h:
            break
    return r0, r1


def label_from_source(img: np.ndarray, pos: float, axis_at: float, outward: int, horizontal: bool, half: float,
                      depth: int | None = None, max_h: int | None = None,
                      extent: tuple[float, float] | None = None) -> list[float] | None:
    """The box of the label of one tick, measured on the source image at full resolution.

    The network says where the tick is; the label is the first row of ink
    outside the axis near it, after the pad that separates it from the tick
    mark. Walking outward from the axis line, rows (columns, for a y axis)
    attached to the axis line or to any drawn line are the tick marks and the
    spine, and are skipped; the first run of ink after a gap is the label's
    band. Along the axis the label is the group of glyphs nearest the tick,
    glyphs being joined while the gaps between them are small against the text
    height. The labels of an axis share one ink colour, so once the first glyph
    is found only ink on the paper-to-that-colour blend counts: a series name
    printed in its colour beside the axis, or a data line running past, does
    not join the label. `img` is float32 RGB. Returns [x0, y0, x1, y1] in
    source pixels, or None.
    """
    if img.ndim == 2:
        img = np.repeat(img[..., None], 3, axis=-1)
    H, W = img.shape[:2]
    if depth is None:
        depth = 250 if horizontal else 220  # a rotated x label is tall; a y label can be "1,000,000,000"
    if max_h is None:
        max_h = 250 if horizontal else 200
    a0 = int(np.floor(pos - half))
    a1 = int(np.ceil(pos + half))
    c0 = int(round(axis_at)) + (1 if outward > 0 else -1)
    c1 = c0 + outward * depth
    if horizontal:
        a0, a1 = max(0, a0), min(W - 1, a1)
        c0, c1 = (max(0, min(c0, c1)), min(H - 1, max(c0, c1)))
        win = img[c0:c1 + 1, a0:a1 + 1]
    else:
        a0, a1 = max(0, a0), min(H - 1, a1)
        c0, c1 = (max(0, min(c0, c1)), min(W - 1, max(c0, c1)))
        win = img[a0:a1 + 1, c0:c1 + 1].transpose(1, 0, 2)
    if outward < 0:
        win = win[::-1]
    # win[k, j]: k steps outward from the axis, j along the axis.
    if win.shape[0] < 4 or win.shape[1] < 3:
        return None
    paper = np.median(win.reshape(-1, 3), axis=0)
    rel = win - paper
    contrast = np.abs(rel).max(-1)
    peak = float(contrast.max())
    if peak < 30:
        return None
    ink = contrast > max(20.0, 0.25 * peak)
    ink = _mask_tick_marks(ink)

    # A line is judged over the plot's own extent along the axis: an offset spine ends with the plot, and
    # the window of an end tick reaches past it.
    lo, hi = 0, win.shape[1] - 1
    if extent is not None:
        lo = max(0, int(np.floor(extent[0] - 2)) - a0)
        hi = min(win.shape[1] - 1, int(np.ceil(extent[1] + 2)) - a0)
        if hi - lo < 4:
            lo, hi = 0, win.shape[1] - 1

    band = _label_band(ink, *_row_shapes(ink, lo, hi), horizontal, max_h)
    if band is None:
        return None
    r0, r1 = band
    # The ink colour of the label, from the darkest pixels of its first glyph run; then only that
    # ink counts. The colour filter decides which ROWS to keep for the band; the along-axis extent
    # still uses the raw ink, so anti-aliased glyph edges on a small label do not get stripped
    # from the leading or trailing digit.
    raw_ink = ink
    first = ink[r0:r1 + 1] & (contrast[r0:r1 + 1] >= 0.7 * contrast[r0:r1 + 1].max())
    if first.sum() >= 2:
        colour = np.median(win[r0:r1 + 1][first], axis=0)
        d = colour - paper
        dd = float(d @ d)
        if dd > 400:
            t = (rel @ d) / dd
            off = np.linalg.norm(rel - t[..., None] * d, axis=-1) / math.sqrt(dd)
            ink2 = ink & (off < 0.35) & (t > 0.2)
            band = _label_band(ink2, *_row_shapes(ink2, lo, hi), horizontal, max_h)
            if band is not None:
                ink, (r0, r1) = ink2, band
    band_ink = raw_ink[r0:r1 + 1]
    along = np.nonzero(band_ink.any(0))[0]
    if len(along) == 0:
        return None
    rel_pos = pos - a0
    if horizontal:
        # Groups of glyphs along the axis; the one nearest the tick is its label, and a label is centred on
        # its tick (or ends at it, when rotated), so it must reach the tick's position.
        hgt = r1 - r0 + 1
        s, e = _nearest_run(_runs(along, max(3, int(round(0.8 * hgt)))), rel_pos)
        if e - s + 1 < 2 or hgt < 3 or not (s - max(3, 0.3 * hgt) <= rel_pos <= e + max(3, 0.3 * hgt)):
            return None
        y0, y1 = (c0 + r0, c0 + r1) if outward > 0 else (c1 - r1, c1 - r0)
        return [float(a0 + s), float(y0), float(a0 + e), float(y1)]
    # A y label: its rows are the ink rows of the band nearest the tick, and it is centred on the tick.
    s, e = _nearest_run(_runs(along, 2), rel_pos)
    if e - s + 1 < 3 or r1 - r0 + 1 < 2 or not (s - 3 <= rel_pos <= e + 3):
        return None
    x0, x1 = (c0 + r0, c0 + r1) if outward > 0 else (c1 - r1, c1 - r0)
    return [float(x0), float(a0 + s), float(x1), float(a0 + e)]


def refine_labels(img: np.ndarray, ex: Extraction) -> Extraction:
    """Re-measure every tick's label box on the source pixels.

    The canvas the network sees is at most 768 x 512, and a label of a large
    screenshot is a 4-pixel blob on it: its class map misses it or cuts a
    digit off. The tick position itself is exact, so the label is found from
    it on the source image. A box measured there replaces the network's; where
    nothing is found, the network's box stands.

    The x axis goes first: its label band (the rows the x labels occupy) is
    masked out while the y labels are measured, so the y label at the corner
    does not run into the x label below it.
    """
    imf = img.astype(np.float32)
    H, W = imf.shape[:2]
    pa = ex.plot_area
    masked = imf
    for key in ("xticks", "yticks"):
        ticks = getattr(ex, key)
        if not ticks:
            continue
        horizontal = key == "xticks"
        # Duplicate ticks (two heat peaks on one tick, two sem components for one tick) collapse
        # the median spacing to zero and shrink the along-axis window below one glyph. Measure the
        # spacing from unique positions, rounded to the pixel, before computing the window.
        uniq = np.unique(np.round([t["pos"] for t in ticks]).astype(int))
        d = np.diff(np.sort(uniq)) if len(uniq) > 1 else np.array([60.0])
        d = d[d > 0]
        spacing = float(np.median(d)) if len(d) else 60.0
        half = max(6.0, 0.48 * spacing)
        bands: list[tuple[int, int]] = []
        for t in ticks:
            ax_, ay = t["anchor"]
            if horizontal:
                mid = (pa[1] + pa[3]) / 2 if pa else H / 2
                outward = 1 if ay >= mid else -1
                box = label_from_source(imf, t["pos"], ay, outward, True, half, extent=(pa[0], pa[2]) if pa else None)
            else:
                mid = (pa[0] + pa[2]) / 2 if pa else W / 2
                outward = -1 if ax_ <= mid else 1
                box = label_from_source(masked, t["pos"], ax_, outward, False, half, extent=(pa[1], pa[3]) if pa else None)
            if box is not None:
                if t["label_box"] is not None:
                    t["label_box_net"] = t["label_box"]
                t["label_box"] = box
                if horizontal:
                    bands.append((int(np.floor(box[1])), int(np.ceil(box[3]))))
        if horizontal and bands:
            masked = imf.copy()
            paper = np.median(imf[0], axis=0)
            for lo, hi in bands:
                masked[max(0, lo - 1):min(H, hi + 2)] = paper
    return ex


def _pick_line(prof: np.ndarray, lo: int, p: float, search: float, best):
    """The centre of the strongest thin line in a 1-D contrast profile, if it is clear and near `p`."""
    if len(prof) < 3:
        return best
    base = float(np.min(prof))
    peak = int(np.argmax(prof))
    strength = float(prof[peak] - base)
    if strength < 12:  # grey levels: too faint to be a drawn line
        return best
    w = np.clip(prof - base - 0.25 * strength, 0, None)
    # Only the run of the peak itself: one line, not a line and a neighbour.
    a = peak
    while a > 0 and w[a - 1] > 0:
        a -= 1
    b = peak
    while b < len(w) - 1 and w[b + 1] > 0:
        b += 1
    if b - a > 3:  # a thick band, not a line
        return best
    c = lo + float((w[a:b + 1] * np.arange(a, b + 1)).sum() / w[a:b + 1].sum())
    if abs(c - p) > search:
        return best
    if best is None or strength > best[0]:
        return (strength, c)
    return best


def refine_markers(img: np.ndarray, ex: Extraction, **kw) -> Extraction:
    """Re-measure markers on the source pixels: size, centre, convention, and what is not a marker (markers.py)."""
    from .markers import refine_markers as _refine

    return _refine(img, ex, **kw)
