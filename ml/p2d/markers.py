"""Markers measured on the source pixels: size, centre, convention, and what is not a marker.

The network says roughly where the markers are (a heat peak each) and which
series they belong to. Everything after that is measured on the pixels:

- The ink of a series is the set of pixels whose colour lies on the blend
  segment from the paper colour to the series colour (`ink_weight`); other
  series, grid, text and axis ink weigh nothing.
- The marker size is read off the isolated blobs of that ink (one heat peak,
  touching nothing). With the size known, each centre is re-measured as the
  centroid of its own share of the ink: a Gaussian mixture with one component
  per peak and a width set by the size, so touching markers split their shared
  pixels instead of pulling each other, and two peaks on one big marker end up
  at the same centre and are merged.
- Drawing conventions are read off the image rather than assumed. matplotlib's
  Agg stamps every marker at a whole pixel, so the recorded data point is on
  average half a pixel up and left of the ink; such a series is recognised by
  its isolated centroids sitting on exact pixel centres, and corrected. Plotly
  and browser renderers draw at the exact position and are left alone. A
  triangle's data point is its bounding-box centre in matplotlib and its
  centroid in Plotly; the orientation is read off the blob.
- A peak on a traced line whose ink is no wider than the line's stroke is a
  dash or a spike of that line, not a marker. A series whose isolated blobs are
  long and thin is the dashes of a dashed line.

Coordinates are source pixels, centre of pixel i at i, throughout.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy.spatial import cKDTree

from .data import apply


@dataclass
class SeriesMarkers:
    """What was measured for one series' markers; kept on the Series for reports and tests."""
    size: float = 0.0  # marker extent in source px
    n_isolated: int = 0
    snapped: bool = False  # Agg-stamped: data point = pixel centre - 0.5
    shape: str = ""  # "tri" when the blobs are triangles, else ""
    stroke: float = 0.0  # stroke width of the owning line, if any
    dropped: int = 0  # peaks judged not to be markers
    merged: int = 0  # peaks that converged onto another
    added: int = 0  # seeds added for markers the heat merged
    notes: list[str] = field(default_factory=list)


def paper_colour(img: np.ndarray, area: list[float] | None) -> np.ndarray:
    """The dominant colour inside the plot area (or the image): the paper markers are drawn on."""
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
    return patch[key == mode].mean(0).astype(np.float32)


def ink_weight(imf: np.ndarray, paper: np.ndarray, colour: np.ndarray, off_tol: float = 0.3) -> np.ndarray:
    """How far along the paper-to-colour blend each pixel lies (0 off the segment)."""
    d = colour - paper
    dd = float(d @ d)
    if dd < 1e-6:
        return np.zeros(imf.shape[:2], np.float32)
    rel = imf - paper
    t = (rel @ d) / dd
    off = np.linalg.norm(rel - t[..., None] * d, axis=-1) / math.sqrt(dd)
    return np.where(off < off_tol, np.clip(t, 0, 1), 0.0).astype(np.float32)


def _half_runs(mask: np.ndarray, x: int, y: int, limit: int = 60) -> np.ndarray:
    """Lengths of the runs of `mask` leaving (x, y) to the left, right, up and down (excluding the pixel)."""
    H, W = mask.shape
    out = np.zeros(4)
    if not (0 <= x < W and 0 <= y < H):
        return out
    for k, (dx, dy) in enumerate(((-1, 0), (1, 0), (0, -1), (0, 1))):
        n = 0
        cx, cy = x + dx, y + dy
        while 0 <= cx < W and 0 <= cy < H and mask[cy, cx] and n < limit:
            n += 1
            cx += dx
            cy += dy
        out[k] = n
    return out


def size_at(mask: np.ndarray, x: float, y: float) -> float:
    """Marker extent through a point, as twice the second-smallest half run: a line through the marker
    lengthens at most two opposite runs, the other two still end at the marker's edge."""
    xi, yi = int(round(x)), int(round(y))
    H, W = mask.shape
    if not (0 <= xi < W and 0 <= yi < H):
        return 0.0
    if not mask[yi, xi]:
        # The estimate is on the rim or in a hole: use the nearest ink pixel within 2 px.
        best = None
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if 0 <= xi + dx < W and 0 <= yi + dy < H and mask[yi + dy, xi + dx]:
                    d = dx * dx + dy * dy
                    if best is None or d < best[0]:
                        best = (d, xi + dx, yi + dy)
        if best is None:
            return 0.0
        xi, yi = best[1], best[2]
    r = np.sort(_half_runs(mask, xi, yi))
    return float(2 * r[1] + 1)


def _frac_cluster(vals: np.ndarray) -> tuple[float, float]:
    """Circular mean and resultant length of the fractional parts of `vals` (1 = all the same phase)."""
    a = 2 * np.pi * (vals - np.floor(vals))
    c, s = np.cos(a).mean(), np.sin(a).mean()
    return float(math.atan2(s, c) / (2 * np.pi)), float(math.hypot(c, s))


def triangle_apex(w: np.ndarray) -> tuple[float, float] | None:
    """If the weighted blob is a triangle, the unit direction from its centroid to the apex, else None.

    A triangle fills about half its bounding box, like a diamond, but unlike a
    diamond it is not symmetric under a half turn, and the apex side of the box
    holds far less ink than the base side.
    """
    s = float(w.sum())
    if s < 4:
        return None
    ys, xs = np.nonzero(w > 0.3)
    if len(xs) < 4:
        return None
    bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    fill = s / (bw * bh)
    if not 0.35 <= fill <= 0.62:
        return None
    yy, xx = np.mgrid[0:w.shape[0], 0:w.shape[1]]
    cx, cy = (w * xx).sum() / s, (w * yy).sum() / s
    M = cv2.getRotationMatrix2D((float(cx), float(cy)), 180, 1.0)
    rot = cv2.warpAffine(w.astype(np.float32), M, (w.shape[1], w.shape[0]), flags=cv2.INTER_LINEAR)
    if float(np.abs(rot - w).sum() / (2 * s)) < 0.12:
        return None  # symmetric: a diamond, not a triangle
    q = 0.3
    top = w[ys.min(): ys.min() + max(1, int(round(q * bh)))].sum()
    bot = w[ys.max() + 1 - max(1, int(round(q * bh))): ys.max() + 1].sum()
    left = w[:, xs.min(): xs.min() + max(1, int(round(q * bw)))].sum()
    right = w[:, xs.max() + 1 - max(1, int(round(q * bw))): xs.max() + 1].sum()
    v = abs(top - bot) / max(top + bot, 1e-6)
    h = abs(left - right) / max(left + right, 1e-6)
    if max(v, h) < 0.3:
        return None
    if v >= h:
        return (0.0, -1.0) if top < bot else (0.0, 1.0)
    return (-1.0, 0.0) if left < right else (1.0, 0.0)


def elongation(w: np.ndarray) -> float:
    """Ratio of the blob's principal extents (1 for anything round or square, large for a dash), tilt-invariant."""
    m = cv2.moments(w.astype(np.float32))
    if m["m00"] < 1e-6:
        return 1.0
    a, b, c = m["mu20"] / m["m00"], m["mu11"] / m["m00"], m["mu02"] / m["m00"]
    d = math.sqrt(max(0.0, ((a - c) / 2) ** 2 + b * b))
    lo = max((a + c) / 2 - d, 1e-6)
    return float(math.sqrt(((a + c) / 2 + d) / lo))


def weighted_bbox_centre(w: np.ndarray) -> tuple[float, float]:
    """Centre of the extent of the ink: first and last row and column holding at least half a pixel of ink."""
    rows = np.nonzero(w.sum(1) > 0.5)[0]
    cols = np.nonzero(w.sum(0) > 0.5)[0]
    if len(rows) == 0 or len(cols) == 0:
        return 0.0, 0.0
    return float((cols[0] + cols[-1]) / 2), float((rows[0] + rows[-1]) / 2)


def snap_phase(cen: np.ndarray, min_n: int = 5, min_r: float = 0.45):
    """If the centres sit on one sub-pixel phase in both axes they were stamped on the pixel grid.

    Returns the phase (px, py) or None. A series drawn at exact positions has
    uniformly spread fractional parts (resultant length near 0). The phase is
    whatever constant the measurement adds (half a pixel for a shape whose
    extent is an even number of rows), and is taken out before quantising.
    Both axes must agree: evenly spaced x values can share one phase by
    themselves, the y values of a real series do not.
    """
    n = len(cen)
    if n < min_n:
        return None
    # Uniform phases give a resultant of about sqrt(-ln(alpha) / n); this is alpha = 0.7% per axis.
    need = max(min_r, math.sqrt(5.0 / n))
    mx, rx = _frac_cluster(cen[:, 0])
    my, ry = _frac_cluster(cen[:, 1])
    if rx > need and ry > need:
        return mx, my
    return None


def mixture_centres(w: np.ndarray, seeds: np.ndarray, sigma: float, radius: float, iters: int = 6) -> tuple[np.ndarray, np.ndarray]:
    """Centres of a Gaussian mixture with one component per seed fitted to the ink weights.

    Every ink pixel within `radius` of a seed is shared between the nearby
    components in proportion to a Gaussian of width `sigma` (E step); each
    centre moves to the weighted mean of its share (M step). Returns the
    centres and the ink mass each one holds.
    """
    H, W = w.shape
    c = seeds.astype(np.float64).copy()
    n = len(c)
    if n == 0:
        return c, np.zeros(0)
    r = int(math.ceil(radius))
    x0, y0 = max(0, int(np.floor(c[:, 0].min())) - r), max(0, int(np.floor(c[:, 1].min())) - r)
    x1, y1 = min(W, int(np.ceil(c[:, 0].max())) + r + 1), min(H, int(np.ceil(c[:, 1].max())) + r + 1)
    sub = w[y0:y1, x0:x1]
    ys, xs = np.nonzero(sub > 0.05)
    if len(xs) == 0:
        return c, np.zeros(n)
    pts = np.column_stack([xs + x0, ys + y0]).astype(np.float64)
    wt = sub[ys, xs].astype(np.float64)
    mass = np.zeros(n)
    for _ in range(iters):
        tree = cKDTree(c)
        near = tree.query_ball_point(pts, radius)
        rows, cols, g = [], [], []
        for i, js in enumerate(near):
            if not js:
                continue
            d2 = ((c[js] - pts[i]) ** 2).sum(1)
            e = np.exp(-0.5 * d2 / (sigma * sigma))
            rows += [i] * len(js)
            cols += list(js)
            g += list(e)
        if not rows:
            break
        rows, cols, g = np.array(rows), np.array(cols), np.array(g)
        tot = np.zeros(len(pts))
        np.add.at(tot, rows, g)
        resp = g / np.maximum(tot[rows], 1e-12) * wt[rows]
        mass = np.zeros(n)
        np.add.at(mass, cols, resp)
        sx = np.zeros(n)
        sy = np.zeros(n)
        np.add.at(sx, cols, resp * pts[rows, 0])
        np.add.at(sy, cols, resp * pts[rows, 1])
        ok = mass > 1e-6
        new = c.copy()
        new[ok, 0] = sx[ok] / mass[ok]
        new[ok, 1] = sy[ok] / mass[ok]
        if np.abs(new - c).max() < 0.01:
            c = new
            break
        c = new
    return c, mass


def line_stroke(w: np.ndarray, line_px: np.ndarray) -> float:
    """Stroke width of a traced line on its own ink, in px, from the run across the line per column."""
    if len(line_px) < 3:
        return 0.0
    lp = line_px[np.argsort(line_px[:, 0], kind="stable")]
    H, W = w.shape
    runs = []
    step = max(1, len(lp) // 60)
    for i in range(0, len(lp), step):
        x, y = int(round(lp[i, 0])), int(round(lp[i, 1]))
        if not (0 <= x < W and 1 <= y < H - 1):
            continue
        j0, j1 = max(0, i - 2), min(len(lp) - 1, i + 2)
        slope = (lp[j1, 1] - lp[j0, 1]) / max(lp[j1, 0] - lp[j0, 0], 1e-6)
        col = w[:, x] > 0.5
        if not col[y]:
            # The trace may sit a pixel off the ink: look one pixel either side.
            if col[y - 1]:
                y -= 1
            elif col[y + 1]:
                y += 1
            else:
                continue
        a = b = y
        while a > 0 and col[a - 1]:
            a -= 1
        while b < H - 1 and col[b + 1]:
            b += 1
        runs.append((b - a + 1) / math.sqrt(1 + slope * slope))
    return float(np.median(runs)) if len(runs) >= 3 else 0.0


def measure_series(img_f: np.ndarray, paper: np.ndarray, colour, peaks: np.ndarray, roi: tuple[int, int, int, int],
                   line_px: np.ndarray | None = None, add_seeds: bool = True) -> tuple[np.ndarray, SeriesMarkers]:
    """Re-measure one series' marker centres from its peaks. Returns the kept centres and the record."""
    rec = SeriesMarkers()
    if len(peaks) == 0:
        return peaks, rec
    x0, y0, x1, y1 = roi
    sub = img_f[y0:y1, x0:x1]
    w = ink_weight(sub, paper, np.asarray(colour, np.float32))
    pk = peaks - [x0, y0]
    mask = w > 0.5
    n_cc, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    H, W = mask.shape

    # The component under each peak (or the nearest within 2 px).
    comp = np.zeros(len(pk), np.int32)
    for i, (x, y) in enumerate(pk):
        xi, yi = int(round(x)), int(round(y))
        best = 0
        bd = 1e9
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                xx, yy = xi + dx, yi + dy
                if 0 <= xx < W and 0 <= yy < H and lab[yy, xx] > 0 and dx * dx + dy * dy < bd:
                    best, bd = lab[yy, xx], dx * dx + dy * dy
        comp[i] = best
    counts = np.bincount(comp, minlength=n_cc)

    # Isolated blobs: one peak, not touching the window edge, a few pixels at least.
    # A blob whose principal extents are very elongated is a line fragment, not a candidate
    # marker (500021 line's components misread as isolated); drop it from the measurement.
    iso = []
    for i, c in enumerate(comp):
        if c == 0 or counts[c] != 1:
            continue
        bx, by, bw, bh, area = stats[c]
        if bx <= 0 or by <= 0 or bx + bw >= W or by + bh >= H or area < 3:
            continue
        patch_i = np.where(lab[by:by + bh, bx:bx + bw] == c, w[by:by + bh, bx:bx + bw], 0.0)
        if elongation(patch_i) > 4.0:
            continue
        iso.append((i, c, max(bw, bh), area, bw, bh))
    rec.n_isolated = len(iso)
    if len(iso) >= 3:
        size = float(np.median([e for _, _, e, _, _, _ in iso]))
        area1 = float(np.median([a for _, _, _, a, _, _ in iso]))
    else:
        sz = [size_at(mask, x, y) for x, y in pk]
        sz = [s for s in sz if s > 0]
        size = float(np.median(sz)) if sz else 6.0
        area1 = 0.0
    size = max(size, 2.0)
    rec.size = size

    def blob_patch(c):
        bx, by, bw, bh = stats[c, 0], stats[c, 1], stats[c, 2], stats[c, 3]
        return bx, by, np.where(lab[by:by + bh, bx:bx + bw] == c, w[by:by + bh, bx:bx + bw], 0.0)

    # Dashes of a dashed line misclassified as scatter: isolated blobs are long and thin. Only fire
    # the veto on scatter series (no owning line): a line+markers series's isolated blobs often
    # include marker+dash merged shapes that look elongated (500134, 500021). The line_stroke
    # per-peak veto below handles dashes on line+markers.
    if line_px is None and len(iso) >= 3:
        el = np.array([elongation(blob_patch(c)[2]) for _, c, _, _, _, _ in iso])
        if np.median(el) > 2.0:
            rec.notes.append("dashes")
            rec.dropped = len(pk)
            return np.zeros((0, 2)), rec

    keep = np.ones(len(pk), bool)
    # A peak on the owning line that is no wider than the line's stroke is the line itself.
    # The per-peak veto only informs when markers are confusable with the stroke: when there are
    # isolated markers to measure a size against (`iso` >= 3) AND that size is close to the stroke.
    # If the series' isolated markers are visibly bigger than the stroke, trust the heat peaks on
    # the line - size_at measures cardinal half-runs and fails on sparse shapes like X, x, *, +.
    if line_px is not None and len(line_px) >= 3:
        stroke = line_stroke(w, line_px - [x0, y0])
        rec.stroke = stroke
        if stroke > 0 and len(iso) >= 3 and size <= stroke + 2.0:
            need = max(1.5 * stroke, stroke + 2.0)
            for i, (x, y) in enumerate(pk):
                if size_at(mask, x, y) < need:
                    keep[i] = False
            rec.dropped += int((~keep).sum())
    pk = pk[keep]
    comp = comp[keep]
    if len(pk) == 0:
        return np.zeros((0, 2)), rec

    # Fall back to raw heat peaks when no isolated markers are available: without a size and shape
    # confirmed on isolated blobs, the mixture centroid may be far from the drawn centre for
    # asymmetric shapes (triangle: size/6 off), and the line-stroke test above has been skipped on
    # the same grounds. The raw peaks come from the network trained on the drawn centre.
    if len(iso) < 3:
        rec.notes.append("no_iso")
        return pk + [x0, y0], rec

    # Markers the heat merged: a blob holding more ink than its peaks account for gets extra seeds.
    # Only trusted when area1 is measured from enough isolated blobs; the extras are also capped per
    # blob so a huge merged component can't flood the mixture with arbitrary seeds (14000064).
    seeds = pk.copy()
    if add_seeds and len(iso) >= 5 and area1 > 0 and line_px is None:
        extra = []
        max_extras_per_blob = 3
        for c in np.unique(comp):
            if c == 0:
                continue
            k = int((comp == c).sum())
            area = stats[c, cv2.CC_STAT_AREA]
            m = int(math.floor(area / area1 + 0.35))
            if m <= k or m - k > 12:
                continue
            ys, xs = np.nonzero(lab == c)
            cand = np.column_stack([xs, ys]).astype(np.float64)
            cur = list(seeds[comp == c]) + extra
            added_here = 0
            for _ in range(m - k):
                if added_here >= max_extras_per_blob:
                    break
                d = np.min(np.linalg.norm(cand[:, None, :] - np.array(cur)[None], axis=2), axis=1) if cur else np.full(len(cand), 1e9)
                j = int(np.argmax(d))
                if d[j] < 0.5 * size:
                    break
                cur.append(cand[j])
                extra.append(cand[j])
                added_here += 1
        if extra:
            seeds = np.vstack([seeds, np.array(extra)])
            rec.added = len(extra)

    # The window covers the marker and little else: a line through it is straight that far, and a
    # neighbour's ink only enters where the two overlap.
    sigma = max(1.0, 0.3 * size)
    radius = max(2.5, 0.62 * size)
    cen, mass = mixture_centres(w, seeds, sigma, radius)
    # Two seeds on one marker converge together: keep the heavier.
    order = np.argsort(-mass)
    kept = []
    for i in order:
        if mass[i] <= 0.5:
            continue
        if any(np.hypot(*(cen[i] - cen[j])) < 0.45 * size for j in kept):
            rec.merged += 1
            continue
        kept.append(i)
    cen = cen[kept]
    if len(cen) == 0:
        return np.zeros((0, 2)), rec

    # Conventions, read off the isolated blobs. The data point of a marker is the origin of its path:
    # the centroid for every shape but the triangles, whose origin (in matplotlib) is the bounding-box
    # centre. The offset from centroid to bbox centre is measured on the isolated blobs and applied to all.
    # Without isolated blobs we cannot see which shape the series uses, so the centroid risks being
    # several pixels off the drawn centre for anything asymmetric (triangles, stars). In that case we
    # fall back to the heat peaks the network gave us - its training targets the drawn centre on the
    # synthetic charts, and the raw peak is closer than the centroid for asymmetric shapes.
    apex, offs = [], []
    for i, c, e, area, bw, bh in iso:
        bx, by, patch = blob_patch(c)
        s_ = patch.sum()
        yy, xx = np.mgrid[0:bh, 0:bw]
        cx, cy = (patch * xx).sum() / s_, (patch * yy).sum() / s_
        qx, qy = weighted_bbox_centre(patch)
        a = triangle_apex(patch)
        if a is not None:
            apex.append(a)
            offs.append((qx - cx, qy - cy))
    if len(apex) >= max(3, 0.6 * len(iso)):
        rec.shape = "tri"
        off = np.median(np.array(offs), 0)
        corr = cen + off[None]
        # matplotlib's triangles are stamped on the grid at the bbox centre; Plotly's are centred on the centroid.
        ph = snap_phase(corr)
        if ph is not None:
            rec.snapped = True
            cen = corr
    else:
        ph = snap_phase(cen)
        rec.snapped = ph is not None
    if rec.snapped:
        # Stamped at a whole pixel: the recorded data point lies within the pixel below and to the right
        # of the stamp, so its best estimate is the stamp minus half a pixel.
        cen = np.round(cen - np.array(ph)[None]) - 0.5
    return cen + [x0, y0], rec


def _colour_at(img: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """The median colour of the 3x3 patch around each point."""
    H, W = img.shape[:2]
    out = np.zeros((len(pts), 3), np.float32)
    for i, (x, y) in enumerate(pts):
        xi, yi = int(round(x)), int(round(y))
        patch = img[max(0, yi - 1): yi + 2, max(0, xi - 1): xi + 2].reshape(-1, 3)
        out[i] = np.median(patch, 0) if len(patch) else 0
    return out


def attach_loose(img: np.ndarray, ex, paper: np.ndarray, tol: float = 45.0, line_tol: float = 4.0):
    """Peaks no series took (embedding label -1, singleton clusters) join a series of their colour.

    A peak of a line's colour sitting on that line joins the line; one of a
    scatter series' colour joins it; the rest form new scatter series by
    colour, two or more to a series. Paper-coloured peaks are dropped.
    """
    loose = ex.loose_markers
    if loose is None or len(loose) == 0:
        return
    cols = _colour_at(img, loose)
    used = np.zeros(len(loose), bool)
    for i, (p, c) in enumerate(zip(loose, cols)):
        if float(((c - paper) ** 2).sum()) < 400:
            used[i] = True  # paper: a peak on nothing
            continue
        best = None
        for s in ex.series:
            if not (len(s.markers_px) or s.kind == "line"):
                continue
            dc = float(np.linalg.norm(np.array(s.color, np.float32) - c))
            if dc >= tol:
                continue
            if s.kind == "line":
                lp = s.line_px
                if len(lp) < 2 or not (lp[:, 0].min() - 2 <= p[0] <= lp[:, 0].max() + 2):
                    continue
                o = np.argsort(lp[:, 0], kind="stable")
                if abs(np.interp(p[0], lp[o, 0], lp[o, 1]) - p[1]) > line_tol:
                    continue
            if best is None or dc < best[0]:
                best = (dc, s)
        if best is not None:
            s = best[1]
            s.markers_px = np.vstack([s.markers_px, p[None]]) if len(s.markers_px) else p[None].copy()
            s.support += 1
            used[i] = True
    # The rest: new scatter series by colour.
    rest = np.nonzero(~used)[0]
    groups: list[list[int]] = []
    for i in rest:
        for g in groups:
            if np.linalg.norm(cols[g[0]] - cols[i]) < tol:
                g.append(i)
                break
        else:
            groups.append([i])
    from .extract import Series

    for g in groups:
        if len(g) < 2:
            continue
        pts = loose[g]
        colour = tuple(int(v) for v in np.median(cols[g], 0))
        ex.series.append(Series(kind="scatter", line_px=np.zeros((0, 2)), markers_px=pts, color=colour, support=len(g)))
    ex.loose_markers = np.zeros((0, 2))


def refine_markers(img: np.ndarray, ex, add_seeds: bool = True, attach: bool = True):
    """Re-measure every series' markers on the source pixels (see the module docstring)."""
    if img is None:
        return ex
    paper = paper_colour(img, ex.plot_area)
    if attach:
        attach_loose(img, ex, paper)
    if not any(len(s.markers_px) for s in ex.series):
        return ex
    imf = img.astype(np.float32)
    H, W = img.shape[:2]
    if ex.plot_area is not None:
        pa = ex.plot_area
        roi = (max(0, int(pa[0]) - 4), max(0, int(pa[1]) - 4), min(W, int(pa[2]) + 5), min(H, int(pa[3]) + 5))
    else:
        roi = (0, 0, W, H)
    if roi[2] - roi[0] < 4 or roi[3] - roi[1] < 4:
        return ex
    for se in ex.series:
        if not len(se.markers_px):
            continue
        d = np.array(se.color, np.float32) - paper
        if float(d @ d) < 400:
            continue  # ink indistinguishable from paper: nothing to measure against
        mk = se.markers_px
        inside = (mk[:, 0] >= roi[0]) & (mk[:, 0] < roi[2]) & (mk[:, 1] >= roi[1]) & (mk[:, 1] < roi[3])
        cen, rec = measure_series(imf, paper, se.color, mk[inside], roi,
                                  line_px=se.line_px if se.kind == "line" and len(se.line_px) >= 3 else None,
                                  add_seeds=add_seeds)
        se.markers_px = np.vstack([cen, mk[~inside]]) if (~inside).any() else cen
        se.marker_info = rec
    ex.series = [s for s in ex.series if s.kind == "line" or len(s.markers_px) >= 1]
    return ex
