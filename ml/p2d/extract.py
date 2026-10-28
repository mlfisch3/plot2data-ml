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
from scipy.optimize import linear_sum_assignment
from scipy.spatial import cKDTree

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
    vertices_px: np.ndarray | None = None  # sharp corners found by the vertex head, kept exactly


@dataclass
class Extraction:
    M: np.ndarray
    plot_area: list[float] | None  # x0, y0, x1, y1 in source px
    xticks: list[dict] = field(default_factory=list)  # {pos, anchor, score, label_box}
    yticks: list[dict] = field(default_factory=list)
    series: list[Series] = field(default_factory=list)
    raw: dict | None = None
    loose_labels: list[list[float]] = field(default_factory=list)  # tick-label text no tick claimed, source px


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
    if "dir" in o:
        out["dir"] = o["dir"].float()[0].cpu().numpy()
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


# Tunables of the line tracker, in one place so that experiments can sweep them.
TRACE = dict(split_thr=1.2, gap_pen=0.5, skip_pen=0.3, emb_pen=1.0, emb_max=2.5, track_max=3.5, share_pen=0.5,
             max_skip=12, merge_emb_tol=4.0)


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
        pk = peaks(heat[ch], 0.3, nms=3)
        for (x, y, sc), lb in zip(pk, group_labels(pk, boxes, key == "xticks")):
            src = apply(Mi, [[x, y]])[0]
            if lb is not None:
                claimed.append(lb)
                q = apply(Mi, [[lb[0], lb[1]], [lb[2], lb[3]]])
                lb = [q[0, 0], q[0, 1], q[1, 0], q[1, 1]]
            getattr(ex, key).append(dict(pos=float(src[0] if key == "xticks" else src[1]), anchor=src.tolist(),
                                         score=sc, label_box=lb))

    # Label text no tick took: where an axis multiplier ("1e6") or offset is printed.
    for b in boxes:
        if not any(b[0] >= c[0] - 1 and b[2] <= c[2] + 1 and b[1] >= c[1] - 1 and b[3] <= c[3] + 1 for c in claimed):
            q = apply(Mi, [[b[0], b[1]], [b[2], b[3]]])
            ex.loose_labels.append([q[0, 0], q[0, 1], q[1, 0], q[1, 1]])

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
    mp = np.array([[int(round(p[0])), int(round(p[1]))] for p in mpk], np.int64).reshape(-1, 2)
    # Markers are grouped by embedding: marker peaks, and the data-ink class around them, vote.
    data_ink = (sem[DATA] > 0.5) & roi & ~ink
    dys, dxs = np.nonzero(data_ink)
    mk_lab = np.zeros(0, np.int32)
    if len(mp) or len(dxs):
        allpts = np.vstack([np.column_stack([dxs, dys]), mp])
        e = emb[:, allpts[:, 1], allpts[:, 0]].T
        w = np.concatenate([0.5 * sem[DATA][dys, dxs], np.ones(len(mp)) * 2.0])
        mk_lab = cluster_embeddings(e, w, min_support=15)[len(dxs):]
    if not ink.any() and not len(mp):
        return ex

    # Lines: chains of ridge runs through the whole plot, linked column to column by continuity
    # and by the embedding, which is what tells two series apart where they cross or touch.
    # The chains are then joined end to end where the ends meet.
    frags = []
    T = TRACE
    runs = column_runs(ink, lh, emb, split_thr=T["split_thr"])
    for chain in peel_chains(runs, gap_pen=T["gap_pen"], skip_pen=T["skip_pen"], emb_pen=T["emb_pen"],
                             emb_max=T["emb_max"], track_max=T["track_max"], share_pen=T["share_pen"],
                             max_skip=T["max_skip"]):
        cols = runs.col[chain].astype(float)
        ys = runs.y[chain]
        yi = np.round(ys).astype(int).clip(0, H - 1)
        frags.append({"cols": cols, "ys": ys, "embs": runs.e[chain], "q": float(lh[yi, cols.astype(int)].mean()),
                      "spans": list(zip(runs.a[chain].tolist(), runs.b[chain].tolist()))})
    lines = drop_duplicates(merge_fragments(frags, emb_tol=T["merge_emb_tol"]),
                            min_cols=max(12, int(0.04 * (frame[2] - frame[0])) if frame else 12))
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
    # Each marker goes to at most one line: one it sits on whose embedding there is its own.
    # The rest form scatter series, one per cluster.
    owner = np.full(len(mpk), -1)
    for li, f in enumerate(lines):
        for i in np.nonzero(owner < 0)[0]:
            x, y = mpk[i][0], mpk[i][1]
            if not (f["cols"][0] - 2 <= x <= f["cols"][-1] + 2 and abs(np.interp(x, f["cols"], f["ys"]) - y) < 4):
                continue
            j = int(np.argmin(np.abs(f["cols"] - x)))
            if np.linalg.norm(f["embs"][j] - emb[:, mp[i, 1], mp[i, 0]]) <= 3.0:
                owner[i] = li
    for li, f in enumerate(lines):
        mk = np.array([[mpk[i][0], mpk[i][1]] for i in np.nonzero(owner == li)[0]]).reshape(-1, 2)
        se = _make_series("line", np.column_stack([f["cols"], f["ys"]]), mk, Mi, img)
        if f.get("vertices"):
            se.vertices_px = apply(Mi, f["vertices"])
        ex.series.append(se)
    scatters = []
    for k in range(int(mk_lab.max()) + 1 if len(mk_lab) else 0):
        mk = np.array([[mpk[i][0], mpk[i][1]] for i in np.nonzero((mk_lab == k) & (owner < 0))[0]]).reshape(-1, 2)
        if len(mk) >= 2:
            scatters.append(_make_series("scatter", np.zeros((0, 2)), mk, Mi, img))
    ex.series += merge_by_colour(scatters, img)
    return ex


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


@dataclass
class Runs:
    """The vertical runs of ridge pixels, column by column: the pieces of series crossing each column.

    Arrays over runs, in column order: column, top and bottom row, sub-pixel
    centre, heat mass, and the heat-weighted mean embedding.
    """
    col: np.ndarray
    a: np.ndarray
    b: np.ndarray
    y: np.ndarray
    m: np.ndarray
    e: np.ndarray  # N x E
    et: np.ndarray  # N x E, over the top few rows: what a link from above meets
    eb: np.ndarray  # N x E, over the bottom few rows

    def __len__(self) -> int:
        return len(self.col)


def column_runs(mask: np.ndarray, heat: np.ndarray, emb: np.ndarray | None = None, split_thr: float = 1.2,
                min_piece: int = 2) -> Runs:
    """The vertical runs of a ridge mask, column by column.

    A short run is a crossing of a shallow stretch of line, and its centre is the
    sub-pixel ridge (a parabola through the log heat). A long run is a steep
    stretch passing through the whole column, and its centre is the middle of
    the heat it holds. Where two series touch or cross, their ridges fuse into one
    run, but the embedding does not: a run is cut where the embedding jumps from
    one pixel to the next, so each series keeps a run of its own.
    """
    H, W = mask.shape
    E = emb.shape[0] if emb is not None else 0
    m8 = mask.astype(np.int8)
    d = np.diff(np.concatenate([np.zeros((1, W), np.int8), m8, np.zeros((1, W), np.int8)]), axis=0)
    ya, xa = np.nonzero(d.T == 1)  # transposed: column-major order, so runs come out column by column
    yb, xb = np.nonzero(d.T == -1)
    cols, top, bot = ya, xa, xb - 1  # (ya == yb after the transpose: the column index)
    if emb is not None and len(cols):
        # Cut runs where the embedding jumps between neighbouring pixels, keeping pieces of min_piece rows.
        jump = np.linalg.norm(np.diff(emb, axis=1), axis=0) > split_thr  # (H-1) x W: between row r and r+1
        cut = jump & mask[:-1] & mask[1:]
        cy, cx = np.nonzero(cut.T)
        cx, cy = cy, cx  # back to (row, col) naming: row cy is the last row of the upper piece
        if len(cx):
            order = np.lexsort((cy, cx))
            cx, cy = cx[order], cy[order]
            run_of = np.searchsorted(cols * H + top, cx * H + cy, side="right") - 1
            new_top, new_bot, new_col = [], [], []
            k = 0
            for i in range(len(cols)):
                a, b, c = int(top[i]), int(bot[i]), int(cols[i])
                s0 = a
                while k < len(cx) and run_of[k] == i:
                    r = int(cy[k])
                    k += 1
                    if r + 1 - s0 >= min_piece and b - r >= min_piece:
                        new_top.append(s0)
                        new_bot.append(r)
                        new_col.append(c)
                        s0 = r + 1
                new_top.append(s0)
                new_bot.append(b)
                new_col.append(c)
            cols, top, bot = np.array(new_col), np.array(new_top), np.array(new_bot)
    if not len(cols):
        z = np.zeros((0, E))
        return Runs(cols, top, bot, np.zeros(0), np.zeros(0), z, z, z)
    # Mass, centroid and mean embedding from column-wise cumulative sums.
    hp = np.concatenate([np.zeros((1, W), np.float64), heat.astype(np.float64)])
    cs = np.cumsum(hp, axis=0)
    rows = np.arange(H, dtype=np.float64)[:, None]
    cys = np.cumsum(hp[1:] * rows, axis=0)
    cys = np.concatenate([np.zeros((1, W)), cys])
    mass = cs[bot + 1, cols] - cs[top, cols]
    y = (cys[bot + 1, cols] - cys[top, cols]) / np.maximum(mass, 1e-9)
    if emb is not None:
        ces = np.cumsum(emb.astype(np.float64) * hp[1:][None], axis=1)
        ces = np.concatenate([np.zeros((E, 1, W)), ces], axis=1)

        def mean_emb(r0, r1):
            return ((ces[:, r1 + 1, cols] - ces[:, r0, cols]) / np.maximum(cs[r1 + 1, cols] - cs[r0, cols], 1e-9)).T

        e = mean_emb(top, bot)
        et = mean_emb(top, np.minimum(top + 2, bot))
        eb = mean_emb(np.maximum(bot - 2, top), bot)
    else:
        e = et = eb = np.zeros((len(cols), 0))
    # Short runs: the sub-pixel ridge from a parabola through the log heat around the maximum.
    short = (bot - top) <= 5
    if short.any():
        si = np.nonzero(short)[0]
        win = np.stack([np.where(top[si] + k <= bot[si], heat[np.minimum(top[si] + k, H - 1), cols[si]], -1.0)
                        for k in range(6)], 1)
        r = top[si] + win.argmax(1)
        ok = (r > 0) & (r < H - 1)
        lg = np.log(np.clip(np.stack([heat[np.clip(r - 1, 0, H - 1), cols[si]], heat[r, cols[si]],
                                      heat[np.clip(r + 1, 0, H - 1), cols[si]]], 1), 1e-6, 1))
        den = lg[:, 0] - 2 * lg[:, 1] + lg[:, 2]
        off = np.where(ok & (den < -1e-9), np.clip(0.5 * (lg[:, 0] - lg[:, 2]) / np.where(den < -1e-9, den, -1), -0.5, 0.5), 0.0)
        y[si] = r + off
    return Runs(cols.astype(np.int64), top.astype(np.int64), bot.astype(np.int64), y, mass, e, et, eb)


def peel_chains(runs: Runs, gap_pen: float = 0.5, skip_pen: float = 0.3, emb_pen: float = 1.0,
                emb_max: float = 2.5, track_max: float = 3.5, max_skip: int = 12, min_cols: int = 8,
                max_chains: int = 64, gap_base: float = 2.0, ema: float = 0.3, share_pen: float = 0.5) -> list[np.ndarray]:
    """Best chains of runs, one run per column, by dynamic programming; repeated on what is left.

    A chain's score is the heat it collects, minus `gap_pen` per pixel of vertical
    gap between consecutive runs (touching runs cost nothing, as a continuous
    curve's do), `skip_pen` per empty column jumped over, and `emb_pen` per unit
    of embedding distance between consecutive runs, measured where they meet:
    the bottom rows of the upper run against the top rows of the lower one,
    since a steep run averages many pixels and its neighbours' where series
    fuse. Two links are not allowed at all, whatever heat they would collect,
    because a penalty is bounded and the heat of a wrong continuation is not: a
    link whose embeddings differ by more than `emb_max` (or than `track_max`
    from the chain's running mean, which remembers the series through a fused
    stretch), and a vertical gap larger than a continuous curve could leave
    (`gap_base`, plus the taller run's height per skipped column, since a steep
    curve drops a run's height per column).

    The best chain is taken and its runs become owned: a later chain may still
    pass through them, for `share_pen` a column and no heat, which is how a
    series gets across a stretch where it is fused with another and the two
    ridges are one run. The search ends when no chain of `min_cols` runs of its
    own is left.
    """
    if not len(runs):
        return []
    col, top, bot, mass = runs.col, runs.a.astype(float), runs.b.astype(float), runs.m
    E, Et, Eb, Y = runs.e, runs.et, runs.eb, runs.y
    h = bot - top + 1
    owned = np.zeros(len(runs), bool)
    chains: list[np.ndarray] = []
    ucols, starts = np.unique(col, return_index=True)
    ends = np.append(starts[1:], len(runs))
    while len(chains) < max_chains:
        m = np.where(owned, 0.0, mass)
        score = m.copy()
        track = E.copy()  # running mean of the embedding along the best chain into each run
        back = np.full(len(runs), -1)
        for g in range(len(ucols)):
            c = int(ucols[g])
            g0 = int(np.searchsorted(ucols, c - max_skip))
            if g0 == g:
                continue
            p0, p1 = starts[g0], starts[g]
            s, t = starts[g], ends[g]
            gap = np.maximum(0, np.maximum(top[None, s:t] - bot[p0:p1, None] - 1, top[p0:p1, None] - bot[None, s:t] - 1))
            skip = (c - col[p0:p1] - 1)[:, None]
            below = Y[None, s:t] >= Y[p0:p1, None]
            de = np.where(below, np.linalg.norm(Eb[p0:p1, None, :] - Et[None, s:t, :], axis=2),
                          np.linalg.norm(Et[p0:p1, None, :] - Eb[None, s:t, :], axis=2))
            dt = np.linalg.norm(track[p0:p1, None, :] - E[None, s:t, :], axis=2)
            cand = (score[p0:p1, None] + m[None, s:t] - gap_pen * gap - skip_pen * skip - emb_pen * de
                    - share_pen * owned[None, s:t])
            gap_max = gap_base + skip * (2.0 + np.maximum(h[p0:p1, None], h[None, s:t]))
            cand[(de > emb_max) | (dt > track_max) | (gap > gap_max)] = -np.inf
            j = cand.argmax(0)
            best = cand[j, np.arange(t - s)]
            better = best > score[s:t]
            score[s:t] = np.where(better, best, score[s:t])
            back[s:t] = np.where(better, p0 + j, back[s:t])
            track[s:t] = np.where(better[:, None], (1 - ema) * track[p0 + j] + ema * E[s:t], track[s:t])
        # Take every chain whose own runs are untouched by the chains taken before it, best first;
        # the rest are re-solved in the next pass, on what is then owned.
        taken = owned.copy()
        skipped, new = False, 0
        for node0 in np.argsort(-score):
            if score[node0] <= 0 or taken[node0]:
                continue
            path, node, valid = [], int(node0), True
            while node >= 0:
                if taken[node] and not owned[node]:
                    valid = False
                    break
                path.append(node)
                node = int(back[node])
            if not valid:
                skipped = True
                continue
            own = [n for n in path if not owned[n]]
            taken[path] = True
            if len(own) >= min_cols:
                path.reverse()
                chains.append(np.array(path))
                new += 1
                if len(chains) >= max_chains:
                    break
        owned[taken] = True
        if not skipped or new == 0:
            break
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
    if "embs" in f:
        near_i = [int(np.argmin(np.abs(cols - vx))) for vx in add_x]
        f["embs"] = np.concatenate([f["embs"][keep], f["embs"][near_i]])[o]
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
    """Slope of a line through the last (or first) k samples of a trace."""
    sel = slice(0, k) if head else slice(-k, None)
    x, y = cols[sel], ys[sel]
    if len(x) < 2 or x[-1] == x[0]:
        return 0.0
    A = np.column_stack([x - x.mean(), np.ones(len(x))])
    return float(np.linalg.lstsq(A, y, rcond=None)[0][0])


def join_cost(A: dict, B: dict, end: int = 10, overlap: int = 8, max_dx: int = 80, emb_tol: float = 4.0) -> float | None:
    """The cost of B continuing A, or None when it cannot: ends that do not meet, or embeddings that disagree.

    Over a gap of dx columns, A's end is carried forward along its slope and B's
    start carried back along its own; the nearer of the two misses is the
    geometric error, allowed up to a tolerance that grows with the gap and the
    slope, as the curvature of a continuous curve would let it.
    """
    dx = B["cols"][0] - A["cols"][-1]
    if dx > max_dx or dx < -overlap or B["cols"][-1] <= A["cols"][-1]:
        return None
    if dx <= 0:
        ov = A["cols"] >= B["cols"][0]
        if np.abs(A["ys"][ov] - np.interp(A["cols"][ov], B["cols"], B["ys"])).max() > 2.5:
            return None
        geo, tol = 0.0, 1.0
    else:
        sA = _end_slope(A["cols"], A["ys"], min(end, len(A["cols"])), False)
        sB = _end_slope(B["cols"], B["ys"], min(end, len(B["cols"])), True)
        geo = min(abs(A["ys"][-1] + sA * dx - B["ys"][0]), abs(B["ys"][0] - sB * dx - A["ys"][-1]))
        tol = 2.5 + 0.25 * dx * (1.0 + min(abs(sA), abs(sB)))
        if geo > tol:
            return None
    de = float(np.linalg.norm(A["embs"][-end:].mean(0) - B["embs"][:end].mean(0)))
    if de > emb_tol:
        return None
    return 6.0 * geo / tol + de + 0.03 * max(dx, 0)


def merge_fragments(frags: list[dict], emb_tol: float = 4.0, end: int = 10, no_join: float = 8.0) -> list[dict]:
    """Join chains end to end into series, as one assignment of ends to starts.

    A chain ends where a link was refused (an embedding jump, a gap, a crossing
    it could not pass) and the series goes on in another chain. Each end may
    continue into at most one start and each start from at most one end, chosen
    together by least total cost, so two series cannot both claim one
    continuation. The cost is the geometric miss of `join_cost` plus the
    embedding distance between the ends; a join dearer than `no_join` is not made.
    """
    items = [{"cols": f["cols"], "ys": f["ys"], "embs": f["embs"], "spans": f["spans"], "q": f["q"],
              "n": len(f["cols"])} for f in frags]
    n = len(items)
    if n < 2:
        return items
    C = np.full((n, n), 1e6)
    for i in range(n):
        for j in range(n):
            if i != j:
                c = join_cost(items[i], items[j], end=end, emb_tol=emb_tol)
                if c is not None:
                    C[i, j] = c
    big = np.full((2 * n, 2 * n), 1e6)
    big[:n, :n] = C
    big[:n, n:] = np.where(np.eye(n, dtype=bool), no_join, 1e6)
    big[n:, :n] = np.where(np.eye(n, dtype=bool), no_join, 1e6)
    big[n:, n:] = 0.0
    ri, cj = linear_sum_assignment(big)
    nxt = {int(i): int(j) for i, j in zip(ri, cj) if i < n and j < n and C[i, j] < 1e6}
    has_prev = set(nxt.values())
    out = []
    for i in range(n):
        if i in has_prev:
            continue
        A = dict(items[i])
        j = nxt.get(i)
        while j is not None:
            B = items[j]
            keep = B["cols"] > A["cols"][-1]
            w = A["n"] / (A["n"] + B["n"])
            A["cols"] = np.concatenate([A["cols"], B["cols"][keep]])
            A["ys"] = np.concatenate([A["ys"], B["ys"][keep]])
            A["spans"] = A["spans"] + [sp for sp, k in zip(B["spans"], keep) if k]
            A["embs"] = np.concatenate([A["embs"], B["embs"][keep]])
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
            pts = np.array(out, float)
            if se.vertices_px is not None and len(se.vertices_px):
                # The exact corners stay; the column samples within a pixel of them go.
                v = se.vertices_px
                far = np.min(np.abs(pts[:, 0][:, None] - v[None, :, 0]), axis=1) > 1.0
                pts = np.vstack([pts[far], v])
                pts = pts[np.argsort(pts[:, 0], kind="stable")]
            se.line_px = pts
    return ex


def refine_ticks(img: np.ndarray, ex: Extraction, search: float = 2.0) -> Extraction:
    """Move each tick onto the tick mark or gridline drawn at it, when one is there.

    The network places a tick from everything around it, labels included, and a
    label's offset from its tick is a house style that differs between charting
    libraries. The mark itself does not: where a short line is drawn across the
    axis within a couple of pixels of the estimate, its centre is the tick.

    Two places are searched: a narrow band hugging the axis on the outside,
    where a tick mark is and a label's padding keeps glyphs out, and the whole
    extent of the plot, where a gridline runs. A line must darken most of the
    band (the profile is a low percentile across it), so a glyph, or a data
    line crossing the band, cannot pass for one. With no clear line (a
    labels-only axis) the estimate stands.
    """
    if ex.plot_area is None:
        return ex
    g = img.astype(np.float32).mean(-1)
    H, W = g.shape
    paper = float(np.median(g[int(max(0, ex.plot_area[1])):int(min(H, ex.plot_area[3])),
                              int(max(0, ex.plot_area[0])):int(min(W, ex.plot_area[2]))]))
    x0, y0, x1, y1 = ex.plot_area
    for key in ("xticks", "yticks"):
        for t in getattr(ex, key):
            p = t["pos"]
            lo, hi = int(np.floor(p - search - 1)), int(np.ceil(p + search + 1))
            best = None
            if key == "yticks":
                if lo < 0 or hi >= H:
                    continue
                side = t["anchor"][0]
                out = (int(side) - 4, int(side)) if abs(side - x0) <= abs(side - x1) else (int(side) + 1, int(side) + 5)
                for a, b, q in (out + (20,), (int(x0) + 2, int(x1) - 1, 35)):
                    a, b = max(0, a), min(W, b)
                    if b - a < 4:
                        continue
                    prof = np.percentile(np.abs(g[lo:hi + 1, a:b] - paper), q, axis=1)
                    best = _pick_line(prof, lo, p, search, best)
            else:
                if lo < 0 or hi >= W:
                    continue
                side = t["anchor"][1]
                out = (int(side) + 1, int(side) + 5) if abs(side - y1) <= abs(side - y0) else (int(side) - 4, int(side))
                for a, b, q in (out + (20,), (int(y0) + 2, int(y1) - 1, 35)):
                    a, b = max(0, a), min(H, b)
                    if b - a < 4:
                        continue
                    prof = np.percentile(np.abs(g[a:b, lo:hi + 1] - paper), q, axis=0)
                    best = _pick_line(prof, lo, p, search, best)
            if best is not None:
                t["pos_net"] = p
                t["pos"] = best[1]
                if key == "yticks":
                    t["anchor"] = [t["anchor"][0], best[1]]
                else:
                    t["anchor"] = [best[1], t["anchor"][1]]
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


def refine_markers(img: np.ndarray, ex: Extraction, max_shift: float = 1.5, max_asym: float = 0.2) -> Extraction:
    """Re-measure markers on the source pixels, where the shape makes the centre unambiguous.

    For a shape symmetric under a half turn - circle, square, diamond, cross -
    every charting library puts the data point at the centroid, so the
    ink-weighted centroid of the blob is the measurement. For anything else (a
    triangle, whose data point is the bounding-box centre in matplotlib and the
    circumcentre in Chart.js) the network's estimate, learned from the drawing
    conventions themselves, stands. Ink weight is position along the paper-to-
    series-colour blend, so neighbouring markers of other colours weigh nothing.
    """
    paper = _paper_colour(img, ex.plot_area).astype(np.float32)
    imf = img.astype(np.float32)
    H, W = img.shape[:2]
    for se in ex.series:
        if not len(se.markers_px):
            continue
        d = np.array(se.color, np.float32) - paper
        dd = float(d @ d)
        if dd < 400:
            continue
        out = []
        for mx, my in se.markers_px:
            r = 9
            x0, y0 = int(round(mx)) - r, int(round(my)) - r
            if x0 < 0 or y0 < 0 or x0 + 2 * r + 1 > W or y0 + 2 * r + 1 > H:
                out.append((mx, my))
                continue
            patch = imf[y0:y0 + 2 * r + 1, x0:x0 + 2 * r + 1] - paper
            t = (patch @ d) / dd
            off = np.linalg.norm(patch - t[..., None] * d, axis=-1) / math.sqrt(dd)
            w = np.where(off < 0.3, np.clip(t, 0, 1), 0.0)
            n, lab = cv2.connectedComponents((w > 0.5).astype(np.uint8), connectivity=8)
            c0 = lab[r, r]
            if c0 == 0:
                # The estimate is between pixels of the blob: take the component nearest it.
                ys, xs = np.nonzero(lab)
                if not len(xs):
                    out.append((mx, my))
                    continue
                c0 = lab[ys[np.argmin((xs - r) ** 2 + (ys - r) ** 2)], xs[np.argmin((xs - r) ** 2 + (ys - r) ** 2)]]
            blob = cv2.dilate((lab == c0).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0  # keep the antialiased rim
            if blob[0].any() or blob[-1].any() or blob[:, 0].any() or blob[:, -1].any():
                out.append((mx, my))  # runs out of the window: touching other ink
                continue
            ww = np.where(blob, w, 0.0)
            yy, xx = np.mgrid[0:2 * r + 1, 0:2 * r + 1]
            s = ww.sum()
            cx, cy = (ww * xx).sum() / s, (ww * yy).sum() / s
            # Half-turn symmetry about the centroid.
            M = cv2.getRotationMatrix2D((float(cx), float(cy)), 180, 1.0)
            rot = cv2.warpAffine(ww.astype(np.float32), M, (2 * r + 1, 2 * r + 1), flags=cv2.INTER_LINEAR)
            asym = float(np.abs(rot - ww).sum() / (2 * s))
            nx, ny = x0 + cx, y0 + cy
            if asym <= max_asym and math.hypot(nx - mx, ny - my) <= max_shift:
                out.append((nx, ny))
            else:
                out.append((mx, my))
        se.markers_px = np.array(out, float)
    return ex
