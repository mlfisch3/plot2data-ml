"""A second look at the markers at a higher scale.

PlotNet sees the whole chart on a 768 x 512 canvas, so a wide chart is scaled
down and two markers a few source pixels apart land within the resolution of
the marker heat (about 3 canvas px: a Gaussian of sigma 1.5 per marker, peaks
2 px apart suppressed). Here the plot area is covered with tiles at a scale
chosen from the marker size measured on the source pixels, each tile is run
through the network as a chart of its own, and the marker peaks of all tiles
are merged. Only the marker heat of this pass is used; series membership comes
from the first pass.
"""

from __future__ import annotations

import math

import cv2
import numpy as np
import torch
from scipy.spatial import cKDTree

from .data import CANVAS_H, CANVAS_W, H_MARKER, MEAN, STD
from .extract import peaks

MAX_TILES = 16


def zoom_scale(size_src: float, scale0: float, target: float = 7.0, max_scale: float = 2.0) -> float | None:
    """The scale at which markers of `size_src` px would be about `target` canvas px, if that is a real zoom."""
    if size_src <= 0:
        return None
    s = min(max_scale, target / size_src)
    if s < 1.3 * scale0:
        return None
    return float(s)


def _run_tile(net, crop: np.ndarray, s: float, device: str) -> np.ndarray:
    h, w = crop.shape[:2]
    M = np.array([[s, 0, 0.5 * s - 0.5], [0, s, 0.5 * s - 0.5]], np.float64)
    valid = cv2.warpAffine(np.ones((h, w), np.uint8), M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_NEAREST)
    bg = np.full((CANVAS_H, CANVAS_W, 3), crop[0, 0], np.float32)
    c = cv2.warpAffine(crop, M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR,
                       borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
    c = np.where(valid[..., None] > 0, c, bg)
    x = torch.from_numpy(((c - MEAN) / STD).transpose(2, 0, 1).copy())[None].to(device)
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.bfloat16, enabled=device == "cuda"):
        o = net(x)
    return torch.sigmoid(o["heat"].float())[0, H_MARKER].cpu().numpy()


def _starts(lo: int, hi: int, tile: int, margin: int) -> list[int]:
    """Tile origins covering [lo, hi): stepping by the tile minus twice the margin, the last one flush with hi."""
    if hi - lo <= tile:
        return [lo]
    step = max(1, tile - 2 * margin)
    out = list(range(lo, hi - tile, step))
    out.append(hi - tile)
    return sorted(set(out))


def zoomed_marker_peaks(net, img: np.ndarray, plot_area, s: float, thr: float = 0.3, nms: int = 2,
                        margin_px: int = 24, device: str = "cuda") -> tuple[np.ndarray, np.ndarray, int]:
    """Marker peaks over the plot area from tiles at scale `s`: (N x 2 source px, scores, number of tiles)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = [int(round(v)) for v in plot_area]
    x0, y0 = max(0, x0 - 3), max(0, y0 - 3)
    x1, y1 = min(W, x1 + 4), min(H, y1 + 4)
    tw, th = int(CANVAS_W / s), int(CANVAS_H / s)
    margin = int(math.ceil(margin_px / s))
    xs, ys = _starts(x0, x1, tw, margin), _starts(y0, y1, th, margin)
    if len(xs) * len(ys) > MAX_TILES:
        return np.zeros((0, 2)), np.zeros(0), 0
    pts, scores = [], []
    for ty in ys:
        for tx in xs:
            crop = img[ty:ty + th, tx:tx + tw]
            if crop.size == 0:
                continue
            h = _run_tile(net, crop, s, device)
            ch, cw = crop.shape[:2]
            # Only the inner part of a tile counts, unless the tile sits at the plot's own edge.
            lo_x = margin if tx > x0 else 0
            lo_y = margin if ty > y0 else 0
            hi_x = cw - margin if tx + tw < x1 else cw
            hi_y = ch - margin if ty + th < y1 else ch
            for px, py, sc in peaks(h, thr, nms=nms):
                sx, sy = (px + 0.5) / s - 0.5 + tx, (py + 0.5) / s - 0.5 + ty
                if lo_x - tx <= sx - tx < hi_x and lo_y <= sy - ty < hi_y and x0 <= sx < x1 and y0 <= sy < y1:
                    pts.append((sx, sy))
                    scores.append(sc)
    if not pts:
        return np.zeros((0, 2)), np.zeros(0), len(xs) * len(ys)
    pts, scores = np.array(pts), np.array(scores)
    # Overlapping tiles see the same marker twice: keep the stronger of any two within a canvas pixel and a half.
    tree = cKDTree(pts)
    keep = np.ones(len(pts), bool)
    for i in np.argsort(-scores):
        if not keep[i]:
            continue
        for j in tree.query_ball_point(pts[i], 1.5 / s):
            if j != i and scores[j] <= scores[i]:
                keep[j] = False
    return pts[keep], scores[keep], len(xs) * len(ys)
