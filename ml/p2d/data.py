"""Training samples: a chart placed on a fixed canvas, with dense targets.

Geometry is kept as vectors until the very end: the image and label maps are
warped by one affine transform, the same transform is applied to every path,
marker, tick and corner, and only then are the heat maps rasterised. That keeps
the targets sub-pixel exact however the image was scaled or shifted.
"""

from __future__ import annotations

import glob
import json
import math
import os

import cv2
import numpy as np
import torch
from scipy.spatial import cKDTree
from torch.utils.data import Dataset

cv2.setNumThreads(1)

CANVAS_H, CANVAS_W = 512, 768

# Heat map channels.
H_LINE, H_MARKER, H_VERTEX, H_XTICK, H_YTICK, H_CORNER = range(6)
N_HEAT = 6
N_SEM = 7
MAX_SERIES = 16

SIGMA = {H_LINE: 1.0, H_MARKER: 1.5, H_VERTEX: 1.5, H_XTICK: 1.5, H_YTICK: 1.5, H_CORNER: 2.0}

MEAN = np.array([0.485, 0.456, 0.406], np.float32) * 255
STD = np.array([0.229, 0.224, 0.225], np.float32) * 255


def fit_transform(w: int, h: int, scale_jitter: float = 1.0, shift: tuple[float, float] = (0, 0)) -> np.ndarray:
    """2x3 affine placing a w x h image on the canvas (pixel centres map to pixel centres)."""
    s = min(CANVAS_W / w, CANVAS_H / h, 2.0) * scale_jitter
    return np.array([[s, 0, 0.5 * s - 0.5 + shift[0]], [0, s, 0.5 * s - 0.5 + shift[1]]], np.float64)


def apply(M: np.ndarray, pts) -> np.ndarray:
    p = np.asarray(pts, np.float64).reshape(-1, 2)
    return p @ M[:, :2].T + M[:, 2]


def densify(path: np.ndarray, step: float = 0.25) -> np.ndarray:
    if len(path) < 2:
        return path
    seg = np.diff(path, axis=0)
    ln = np.hypot(seg[:, 0], seg[:, 1])
    n = np.maximum(1, np.ceil(ln / step).astype(int))
    t = np.concatenate([np.arange(k) / k for k in n])
    idx = np.repeat(np.arange(len(seg)), n)
    out = path[idx] + seg[idx] * t[:, None]
    return np.vstack([out, path[-1:]])


def splat_min_dist(points: np.ndarray, H: int, W: int, radius: int) -> np.ndarray:
    """Exact distance from each pixel centre to the nearest point, within `radius` (inf beyond)."""
    d = np.full((H, W), np.inf, np.float32)
    if len(points) == 0:
        return d
    q = np.round(points).astype(np.int64)
    ok = (q[:, 0] >= -radius) & (q[:, 0] < W + radius) & (q[:, 1] >= -radius) & (q[:, 1] < H + radius)
    points, q = points[ok], q[ok]
    if len(points) == 0:
        return d
    mask = np.zeros((H + 2 * radius, W + 2 * radius), np.uint8)
    mask[q[:, 1] + radius, q[:, 0] + radius] = 1
    mask = cv2.dilate(mask, np.ones((2 * radius + 1, 2 * radius + 1), np.uint8))[radius:-radius, radius:-radius]
    ys, xs = np.nonzero(mask)
    dist, _ = cKDTree(points).query(np.column_stack([xs, ys]), distance_upper_bound=radius + 1.5)
    d[ys, xs] = dist
    return d


def turning_vertices(path: np.ndarray, min_len: float = 2.5, min_angle_deg: float = 25.0) -> np.ndarray:
    """Polyline vertices that are visible corners at this resolution."""
    if len(path) < 3:
        return np.zeros((0, 2))
    a = path[1:-1] - path[:-2]
    b = path[2:] - path[1:-1]
    la = np.hypot(a[:, 0], a[:, 1])
    lb = np.hypot(b[:, 0], b[:, 1])
    cos = (a * b).sum(1) / np.maximum(la * lb, 1e-9)
    ang = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    keep = (la >= min_len) & (lb >= min_len) & (ang >= min_angle_deg)
    return path[1:-1][keep]


def augment_photometric(img: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    out = img
    if rng.random() < 0.3:
        # Down- then up-sample: the softness of a video frame or a resized screenshot.
        f = rng.uniform(0.45, 0.9)
        h, w = out.shape[:2]
        small = cv2.resize(out, (max(8, int(w * f)), max(8, int(h * f))), interpolation=cv2.INTER_AREA)
        out = cv2.resize(small, (w, h), interpolation=rng.choice([cv2.INTER_LINEAR, cv2.INTER_CUBIC]))
    if rng.random() < 0.15:
        out = cv2.GaussianBlur(out, (0, 0), rng.uniform(0.3, 0.9))
    if rng.random() < 0.4:
        q = int(rng.uniform(25, 95))
        ok, enc = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, q])
        out = cv2.imdecode(enc, cv2.IMREAD_UNCHANGED)
    out = out.astype(np.float32)
    if rng.random() < 0.3:
        out = out * rng.uniform(0.8, 1.15) + rng.uniform(-20, 20)
    if rng.random() < 0.2:
        out = out + rng.normal(0, rng.uniform(1, 6), out.shape)
    if rng.random() < 0.05:
        g = out.mean(-1, keepdims=True)
        out = np.repeat(g, 3, -1)
    return np.clip(out, 0, 255).astype(np.uint8)


def _background(rng: np.random.Generator, img: np.ndarray) -> np.ndarray:
    kind = rng.random()
    if kind < 0.45:
        c = img[0, 0].astype(np.float32)
        return np.full((CANVAS_H, CANVAS_W, 3), c, np.float32)
    if kind < 0.75:
        return np.full((CANVAS_H, CANVAS_W, 3), rng.uniform(0, 255, 3), np.float32)
    # Clutter: smooth colour noise, like a video frame or an app around the chart.
    small = rng.uniform(0, 255, (int(rng.integers(2, 12)), int(rng.integers(2, 12)), 3)).astype(np.float32)
    return cv2.resize(small, (CANVAS_W, CANVAS_H), interpolation=cv2.INTER_CUBIC)


class PlotDataset(Dataset):
    def __init__(self, roots: list[str] | str, train: bool, limit: int | None = None):
        roots = [roots] if isinstance(roots, str) else roots
        files = []
        for r in roots:
            files += sorted(glob.glob(os.path.join(r, "*.json")))
        if limit:
            files = files[:limit]
        self.files = files
        self.train = train

    def __len__(self) -> int:
        return len(self.files)

    def load(self, i: int):
        stem = self.files[i][:-5]
        meta = json.load(open(self.files[i]))
        img = cv2.imread(stem + ".png", cv2.IMREAD_COLOR)[..., ::-1]
        sem = cv2.imread(stem + ".sem.png", cv2.IMREAD_UNCHANGED)
        inst = cv2.imread(stem + ".inst.png", cv2.IMREAD_UNCHANGED)
        return meta, img, sem, inst

    def __getitem__(self, i: int):
        rng = np.random.default_rng(None if self.train else i)
        meta, img, sem, inst = self.load(i)
        h, w = img.shape[:2]
        if self.train:
            jitter = rng.uniform(0.55, 1.0) if rng.random() < 0.6 else 1.0
            M = fit_transform(w, h, jitter)
            used_w, used_h = apply(M, [[w - 0.5, h - 0.5]])[0] + 0.5
            sx = rng.uniform(0, max(0.0, CANVAS_W - used_w))
            sy = rng.uniform(0, max(0.0, CANVAS_H - used_h))
            M[:, 2] += [sx, sy]
            if rng.random() < 0.2:
                # A slight rotation about the canvas centre.
                ang = rng.uniform(-1.5, 1.5)
                R = cv2.getRotationMatrix2D((CANVAS_W / 2, CANVAS_H / 2), ang, 1.0)
                M = np.vstack([R, [0, 0, 1]]) @ np.vstack([M, [0, 0, 1]])
                M = M[:2]
            img = augment_photometric(img, rng)
            bg = _background(rng, img)
        else:
            M = fit_transform(w, h)
            bg = np.full((CANVAS_H, CANVAS_W, 3), img[0, 0], np.float32)

        # Warp. Pixel-centre convention matches cv2.warpAffine's.
        valid = cv2.warpAffine(np.ones((h, w), np.uint8), M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_NEAREST)
        cimg = cv2.warpAffine(img, M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_AREA if M[0, 0] < 1 else cv2.INTER_LINEAR,
                              borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
        cimg = np.where(valid[..., None] > 0, cimg, bg)
        csem = cv2.warpAffine(sem, M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_NEAREST)
        cinst = cv2.warpAffine(inst, M, (CANVAS_W, CANVAS_H), flags=cv2.INTER_NEAREST)
        cimg = np.clip(cimg, 0, 255)

        heat, region, aux = self.targets(meta, M)
        # Embedding targets: the region around each series' true path, else its ink.
        emb_id = np.where(region > 0, region, cinst).astype(np.int64)
        x = (cimg - MEAN) / STD
        return {
            "image": torch.from_numpy(x.transpose(2, 0, 1).copy()),
            "sem": torch.from_numpy(csem.astype(np.int64)),
            "heat": torch.from_numpy(heat),
            "emb_id": torch.from_numpy(emb_id),
            "index": i,
        }

    def targets(self, meta: dict, M: np.ndarray):
        H, W = CANVAS_H, CANVAS_W
        heat = np.zeros((N_HEAT, H, W), np.float32)
        region = np.zeros((H, W), np.uint8)
        region_d = np.full((H, W), np.inf, np.float32)
        s = math.hypot(M[0, 0], M[1, 0])
        pa = apply(M, [[meta["plot_area"][0], meta["plot_area"][1]], [meta["plot_area"][2], meta["plot_area"][3]]])
        x0, y0 = pa.min(0) - 1.0
        x1, y1 = pa.max(0) + 1.0
        yy, xx = np.mgrid[0:H, 0:W]
        inside = (xx >= x0) & (xx <= x1) & (yy >= y0) & (yy <= y1)

        def gauss(d, sigma):
            return np.exp(-0.5 * (d / sigma) ** 2)

        line_d = np.full((H, W), np.inf, np.float32)
        mark_pts, vert_pts = [], []
        for k, sr in enumerate(meta["series"][: MAX_SERIES - 1]):
            sid = k + 1
            path = apply(M, sr["path_px"]) if sr["path_px"] else np.zeros((0, 2))
            mk = apply(M, sr["markers_px"]) if sr["markers_px"] else np.zeros((0, 2))
            if len(path) >= 2:
                d = splat_min_dist(densify(path), H, W, 4)
                line_d = np.minimum(line_d, d)
                band = max(2.0, 0.5 * sr["linewidth_px"] * s + 0.5)
                take = (d <= band) & (d < region_d)
                region[take] = sid
                region_d[take] = d[take]
                vert_pts.append(turning_vertices(path))
            if len(mk):
                mk = mk[(mk[:, 0] >= x0) & (mk[:, 0] <= x1) & (mk[:, 1] >= y0) & (mk[:, 1] <= y1)]
                mark_pts.append(mk)
                d = splat_min_dist(mk, H, W, max(2, int(round(0.4 * sr["markersize_px"] * s))))
                rad = max(1.5, 0.4 * sr["markersize_px"] * s)
                take = (d <= rad) & (d < region_d)
                region[take] = sid
                region_d[take] = d[take]
        heat[H_LINE] = np.where(inside, gauss(line_d, SIGMA[H_LINE]), 0)
        region[~inside] = 0

        def points_heat(pts, sigma, radius=5):
            if len(pts) == 0:
                return np.zeros((H, W), np.float32)
            return gauss(splat_min_dist(np.asarray(pts, np.float64), H, W, radius), sigma)

        mk_all = np.vstack(mark_pts) if mark_pts else np.zeros((0, 2))
        heat[H_MARKER] = points_heat(mk_all, SIGMA[H_MARKER])
        vt = np.vstack(vert_pts) if vert_pts else np.zeros((0, 2))
        if len(vt):
            vt = vt[(vt[:, 0] >= x0) & (vt[:, 0] <= x1) & (vt[:, 1] >= y0) & (vt[:, 1] <= y1)]
        heat[H_VERTEX] = points_heat(vt, SIGMA[H_VERTEX])
        heat[H_XTICK] = points_heat(apply(M, [t["anchor"] for t in meta["xticks"]]) if meta["xticks"] else [], SIGMA[H_XTICK])
        heat[H_YTICK] = points_heat(apply(M, [t["anchor"] for t in meta["yticks"]]) if meta["yticks"] else [], SIGMA[H_YTICK])
        a = meta["plot_area"]
        heat[H_CORNER] = points_heat(apply(M, [[a[0], a[1]], [a[2], a[1]], [a[0], a[3]], [a[2], a[3]]]), SIGMA[H_CORNER], 7)
        return heat, region, None
