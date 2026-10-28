"""Measuring a traced line on the source pixels, every column of it.

The network says where a series runs and which ink is its. Its centre line is
good to about a third of a canvas pixel, and the canvas is the chart scaled to
768 x 512, so on a large screenshot that is a source pixel or more. The exact
value of each column has to come from the source pixels, and this module takes
it from there in every column, including the ones a column centroid gets wrong:

- A column through a flat stretch holds one stroke; its ink-weighted centroid
  is the value, good to a few hundredths of a pixel. Ink weight is position
  along the paper-to-series-colour blend, so antialiasing carries the sub-pixel
  position and other colours weigh nothing.
- A column through a steep stretch holds a tall run; its centroid is still the
  value, because a straight stroke is symmetric about its centre line, however
  steep. The run is simply taken whole, not cut by a window.
- A column through a turning point holds both flanks, and the centroid lands
  halfway down the spike. There the plotted value is half a stroke in from the
  outermost ink (`top + t/2` at a maximum), unless the join is mitred, which
  the cross-section half a stroke below the tip gives away: a sliver, not a
  stroke. That rule is the classical engine's, and it needs the stroke width
  `t`, which is the ink area over the path length.
- Where the two flanks of a vertex are straight (a polyline of sparse data,
  which is what most charts are), two line fits and their intersection beat
  the outermost-ink rule: the vertex comes back with sub-pixel x and y, and
  the join columns, where the ink of both flanks overlaps, take the polyline's
  own values.

Columns the ink cannot settle stay with the network: gaps in a dashed line,
columns under a marker, columns where the run is merged with other ink of the
same colour or occluded by another series.
"""

from __future__ import annotations

import math

import numpy as np

from .data import apply

W_MIN = 0.08  # blend position below which a pixel is paper
OFF_MAX = 0.3  # distance from the blend segment, relative to its length, beyond which a pixel is other ink
EDGE_TOL = 0.35  # px: outer edges within this of each other are level (a plateau, or antialiasing noise)


def smoothstep(lo: float, hi: float, v: float) -> float:
    if not hi > lo:
        return 1.0 if v >= hi else 0.0
    u = min(1.0, max(0.0, (v - lo) / (hi - lo)))
    return u * u * (3 - 2 * u)


def ink_weights(imf: np.ndarray, paper: np.ndarray, ink: np.ndarray) -> np.ndarray:
    """Coverage of each pixel by the series' ink: its position along the paper-to-ink blend,
    zero for pixels whose colour is off that segment."""
    d = ink - paper
    dd = float(d @ d)
    rel = imf - paper
    t = (rel @ d) / dd
    off = np.linalg.norm(rel - t[..., None] * d, axis=-1) / math.sqrt(dd)
    return np.where((off < OFF_MAX) & (t > W_MIN), np.clip(t, 0, 1), 0.0).astype(np.float32)


def _column_runs(w: np.ndarray, y_off: int):
    """Runs of ink down one weight column: (top, bottom, centroid, mass, lo, hi), sub-pixel edges from coverage."""
    on = w > 0
    if not on.any():
        return []
    d = np.diff(np.concatenate([[0], on.view(np.int8), [0]]))
    starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0] - 1
    out = []
    ys = np.arange(len(w), dtype=np.float64)
    for a, b in zip(starts, ends):
        ww = w[a:b + 1]
        m = float(ww.sum())
        c = float((ww * ys[a:b + 1]).sum() / m)
        out.append((y_off + a + 0.5 - float(min(1.0, w[a])), y_off + b - 0.5 + float(min(1.0, w[b])),
                    y_off + c, m, y_off + int(a), y_off + int(b)))
    return out


def _row_width(W: np.ndarray, y: int, x: int) -> float:
    """Ink across row `y` of the weight map, within the contiguous run holding column `x`."""
    if y < 0 or y >= W.shape[0] or x < 0 or x >= W.shape[1] or W[y, x] <= 0:
        return 0.0
    row = W[y]
    width = float(row[x])
    i = x - 1
    while i >= 0 and row[i] > 0:
        width += row[i]
        i -= 1
    i = x + 1
    while i < len(row) and row[i] > 0:
        width += row[i]
        i += 1
    return width


def _turn_depth(W: np.ndarray, x: int, run, t: float, downward: bool) -> float:
    """How far in from the outermost ink the plotted value sits at a turning point (classical rule)."""
    top, bottom, cen = run[0], run[1], run[2]
    frm = top if downward else bottom
    half = t / 2
    step = 1 if downward else -1
    if _row_width(W, int(round(frm + step * half)), x) >= t * 0.5:
        return half
    limit = max(half, min(6 * t, abs(cen - frm)))
    prev_y, prev_w = frm, 0.0
    for k in range(int(math.ceil(limit)) + 2):
        y = int(round(frm)) + k * step
        if y < 0 or y >= W.shape[0]:
            break
        width = _row_width(W, y, x)
        if width >= t:
            share = (t - prev_w) / (width - prev_w) if width > prev_w else 1.0
            at = prev_y + (y - prev_y) * min(1.0, max(0.0, share))
            return min(limit, max(half, abs(at - frm)))
        prev_y, prev_w = y, width
    return half


def _fit_line(xs: np.ndarray, ys: np.ndarray):
    """Least squares y = a + b x; returns (a, b, max |residual|)."""
    A = np.column_stack([np.ones(len(xs)), xs])
    (a, b), *_ = np.linalg.lstsq(A, ys, rcond=None)
    return float(a), float(b), float(np.max(np.abs(ys - (a + b * xs))))


class LineMeasure:
    """One traced line measured on the source pixels."""

    def __init__(self, img_f: np.ndarray, paper: np.ndarray, color, line_px: np.ndarray, markers_px: np.ndarray,
                 canvas_scale: float, ridge_px: np.ndarray | None = None, net_vertices_x=None):
        self.H, self.W_img = img_f.shape[:2]
        self.s = canvas_scale
        self.net_vx = np.asarray(net_vertices_x, float) if net_vertices_x is not None else np.zeros(0)
        lp = line_px[np.argsort(line_px[:, 0], kind="stable")]
        self.lp = lp
        self.paper = paper
        self.markers = markers_px
        x0, x1 = int(np.ceil(lp[0, 0])), int(np.floor(lp[-1, 0]))
        x0, x1 = max(0, x0), min(self.W_img - 1, x1)
        self.xs = np.arange(x0, x1 + 1)
        self.yc = np.interp(self.xs, lp[:, 0], lp[:, 1])
        # The vertical extent of the network's ridge at each column: what a clean run may span.
        if ridge_px is not None and len(ridge_px) >= 2:
            rp = ridge_px[np.argsort(ridge_px[:, 0], kind="stable")]
            i1 = np.clip(np.searchsorted(rp[:, 0], self.xs), 1, len(rp) - 1)
            i0 = i1 - 1
            r_top = np.minimum(rp[i0, 1], rp[i1, 1])
            r_bot = np.maximum(rp[i0, 2], rp[i1, 2])
            self.ridge_ext = np.maximum(0.0, r_bot - r_top)
        else:
            self.ridge_ext = np.zeros(len(self.xs))
        gi = np.clip(np.searchsorted(lp[:, 0], self.xs), 1, len(lp) - 1)
        self.in_gap = (lp[gi, 0] - lp[gi - 1, 0]) > 2.5 / self.s + 1
        margin = int(12 + 4 / self.s)
        y_lo, y_hi = float(self.yc.min()), float(self.yc.max())
        if ridge_px is not None and len(ridge_px):
            y_lo, y_hi = min(y_lo, float(np.nanmin(ridge_px[:, 1]))), max(y_hi, float(np.nanmax(ridge_px[:, 2])))
        self.y_off = max(0, int(np.floor(y_lo)) - margin)
        y_end = min(self.H, int(np.ceil(y_hi)) + margin + 1)
        band = img_f[self.y_off:y_end, x0:x1 + 1]
        self.x_off = x0
        ink = np.array(color, np.float32)
        d = ink - paper
        if float(d @ d) < 400:
            self.Wm = None
            return
        Wm = ink_weights(band, paper, ink)
        # The series colour was the median pixel on the trace, a blend for a thin line: the darkest
        # pixels on the trace say how far the true ink lies along the segment.
        rows = np.clip(np.round(self.yc).astype(int) - self.y_off, 0, Wm.shape[0] - 1)
        near = np.zeros_like(Wm, dtype=bool)
        for dy in range(-2, 3):
            near[np.clip(rows + dy, 0, Wm.shape[0] - 1), np.arange(Wm.shape[1])] = True
        rel = band - paper
        t_raw = (rel @ d) / float(d @ d)
        sel = near & (Wm > 0.5)
        if sel.sum() >= 10:
            tq = float(np.percentile(t_raw[sel], 97))
            if 1.05 < tq < 4.0:
                Wm = ink_weights(band, paper, paper + tq * d)
        self.Wm = Wm

    def measure(self):
        """Returns (points N x 2 in source px, vertices M x 2, fallback mask over self.xs)."""
        xs, yc = self.xs, self.yc
        n = len(xs)
        fb = np.ones(n, bool)
        if self.Wm is None:
            keep = ~self.in_gap
            return np.column_stack([xs[keep], yc[keep]]), np.zeros((0, 2)), fb
        Wm = self.Wm
        runs = [None] * n
        d_sel = max(3.0, 2.0 / self.s)
        for i in range(n):
            if self.in_gap[i]:
                continue
            rr = _column_runs(Wm[:, i], self.y_off)
            if not rr:
                continue
            best, bd = None, 1e9
            for r in rr:
                dist = 0.0 if r[0] <= yc[i] <= r[1] else min(abs(yc[i] - r[0]), abs(yc[i] - r[1]))
                if dist < bd:
                    best, bd = r, dist
            if bd <= d_sel:
                runs[i] = best
        have = np.array([r is not None for r in runs])
        if have.sum() < 3:
            keep = ~self.in_gap
            return np.column_stack([xs[keep], yc[keep]]), np.zeros((0, 2)), fb
        cen = np.array([r[2] if r else np.nan for r in runs])
        mass = np.array([r[3] if r else np.nan for r in runs])
        span = np.array([r[1] - r[0] if r else np.nan for r in runs])
        # Stroke width: ink area over path length, column by column (a straight stroke of width t
        # at slope m puts t * sqrt(1 + m^2) of ink into a column), the median over the columns.
        # The network's trace is the slope reference: a bad cen pick (fill, swatch, label) would
        # distort the slope seen at that column and let its own neighbours slip through the
        # merged-with-something check.
        slope_yc = np.gradient(yc, xs.astype(float))
        slope = np.gradient(np.where(have, cen, yc), xs.astype(float))
        with np.errstate(invalid="ignore"):
            t_col = mass / np.sqrt(1 + slope_yc ** 2)
        t = float(np.nanmedian(t_col[have])) if have.any() else 1.0
        t = max(t, 0.6)
        # The network's ridge bounds a clean run: its mask spans the whole of a spike even where
        # its centre line is blunt. A run far longer than that plus the stroke is merged with
        # other ink of this colour.
        ext = np.zeros(n)
        for i in range(n):
            lo, hi = max(0, i - 2), min(n, i + 3)
            ext[i] = max(yc[lo:hi].max() - yc[lo:hi].min(), self.ridge_ext[max(0, i - 1):i + 2].max())
        clean = have.copy()
        for i in np.nonzero(have)[0]:
            if span[i] > ext[i] + t * math.sqrt(1 + slope_yc[i] ** 2) + max(3.0, 3 / self.s) + 2:
                clean[i] = False  # merged with something
            elif abs(slope_yc[i]) < 2.0 and t_col[i] < 0.55 * t:
                clean[i] = False  # occluded, under a glyph, a butt cap, or the stroke's end
        # Columns under a marker are the marker's, not the line's.
        under_marker = np.zeros(n, bool)
        if len(self.markers):
            mx = self.markers[:, 0]
            for i in np.nonzero(have)[0]:
                if span[i] > 1.5 * (t * math.sqrt(1 + slope[i] ** 2) + abs(slope[i])) + 2 and np.min(np.abs(mx - xs[i])) < 14 / self.s:
                    under_marker[i] = True
                    clean[i] = False
        # At occluded or end columns (clean=False) the ink centroid is pulled by whatever ink
        # happens to sit in the column: a crossing series, a gridline, a legend swatch at the
        # right edge, or just a half-mass butt cap on a steep stroke. The network's trace is
        # less precise there but it does not blow up, so it stands in.
        values = np.where(clean, cen, yc)
        reach = max(3, int(round(t * 2)))
        turn = np.zeros(n)
        dbg_turn = []
        for i in np.nonzero(clean)[0]:
            r = runs[i]
            steep = smoothstep(1.25, 2.0, span[i] / t)
            if steep <= 0:
                continue
            # How far the outer edge of the ink falls away from this column on each side within
            # reach (a genuine extremum falls away on both sides; the weaker side counts), and
            # whether any column within reach is beyond this one: then this is a flank column
            # next to the apex, not the apex, however far the far side falls away.
            left_up = right_up = left_dn = right_dn = -np.inf
            over_up = over_dn = 0.0
            for dd in range(1, reach + 1):
                if i - dd >= 0 and runs[i - dd] is not None:
                    l = runs[i - dd]
                    left_up = max(left_up, l[0] - r[0])
                    left_dn = max(left_dn, r[1] - l[1])
                    over_up = max(over_up, r[0] - l[0])
                    over_dn = max(over_dn, l[1] - r[1])
                if i + dd < n and runs[i + dd] is not None:
                    q = runs[i + dd]
                    right_up = max(right_up, q[0] - r[0])
                    right_dn = max(right_dn, r[1] - q[1])
                    over_up = max(over_up, r[0] - q[0])
                    over_dn = max(over_dn, q[1] - r[1])
            # A side with no reach (the trace's edge, or a long gap) returns 0, not inf: an
            # apex must have ink falling away on BOTH sides, so a run at the end of a trace
            # that is only unopposed on one side is not an apex and does not insert a vertex.
            sided = lambda v: 0.0 if v == -np.inf else v  # noqa: E731
            peak = min(1.0, max(0.0, min(sided(left_up), sided(right_up)) / t)) if over_up <= EDGE_TOL else 0.0
            trough = min(1.0, max(0.0, min(sided(left_dn), sided(right_dn)) / t)) if over_dn <= EDGE_TOL else 0.0
            # Less than a quarter of a stroke is antialiasing, not a turn; it must not eat into the other sign.
            peak = peak if peak >= 0.25 else 0.0
            trough = trough if trough >= 0.25 else 0.0
            tn = max(-1.0, min(1.0, peak - trough))
            dbg_turn.append((i, peak, trough, over_up, over_dn, steep))
            turn[i] = tn
            if tn == 0:
                continue  # a steep stretch, not a turn: the centroid of a straight stroke is its centre line
            if tn > 0:
                extreme = r[0] + _turn_depth(Wm, i, (r[0] - self.y_off, r[1] - self.y_off, r[2] - self.y_off), t, True)
            else:
                extreme = r[1] - _turn_depth(Wm, i, (r[0] - self.y_off, r[1] - self.y_off, r[2] - self.y_off), t, False)
            values[i] = cen[i] + steep * abs(tn) * (extreme - cen[i])
        # Vertices: the extremum columns of the ink, and the network's corners, refined by flank fits.
        verts = self._vertices(xs, values, cen, clean, runs, turn, t, slope)
        # Short stretches the ink could not settle (dash gaps, a marker, a crossing) between measured
        # columns are bridged straight, unless the network put a corner inside them.
        bridged = np.zeros(n, bool)
        max_gap = int(max(12, 12 / self.s))
        i = 0
        while i < n:
            if clean[i]:
                i += 1
                continue
            j = i
            while j + 1 < n and not clean[j + 1]:
                j += 1
            if i > 0 and j < n - 1 and clean[i - 1] and clean[j + 1] and j - i + 1 <= max_gap and \
                    not np.any((self.net_vx >= xs[i] - 1) & (self.net_vx <= xs[j] + 1)):
                xa, xb = xs[i - 1], xs[j + 1]
                ya, yb = values[i - 1], values[j + 1]
                for q in range(i, j + 1):
                    values[q] = ya + (yb - ya) * (xs[q] - xa) / (xb - xa)
                bridged[i:j + 1] = True
            i = j + 1
        self.bridged = bridged
        self.dbg = dict(cen=cen, values=values.copy(), turn=turn, clean=clean, t=t, span=span, mass=mass, slope=slope, runs=runs, turn_parts=dbg_turn)
        # Bridge columns under markers and short unclean stretches between clean neighbours.
        fb = ~clean
        out_x = list(xs.astype(float))
        out_y = list(values)
        keep = ~self.in_gap
        pts = np.column_stack([np.array(out_x)[keep], np.array(out_y)[keep]])
        if len(verts):
            # The measured vertices go into the trace beside the column samples: at a spike narrower
            # than a pixel the column's own value lies well down the flank from the tip.
            v = np.array([(vx, vy) for vx, vy, _ in verts], float)
            pts = np.vstack([pts, v])
            pts = pts[np.argsort(pts[:, 0], kind="stable")]
        else:
            v = np.zeros((0, 2))
        self.vertex_kinds = [k for _, _, k in verts]
        return pts, v, fb

    def _vertices(self, xs, values, cen, clean, runs, turn, t, slope):
        """Sub-pixel vertices: flank intersection where the flanks are straight, else the apex column."""
        n = len(xs)
        cands = []
        strong = np.abs(turn) > 0.5
        i = 0
        while i < n:
            if strong[i]:
                j = i
                while j + 1 < n and strong[j + 1]:
                    j += 1
                # The apex of a plateau: the column whose outer edge reaches furthest.
                if turn[i] > 0:
                    k = i + int(np.argmin([runs[q][0] for q in range(i, j + 1)]))
                else:
                    k = i + int(np.argmax([runs[q][1] for q in range(i, j + 1)]))
                cands.append(k)
                i = j + 1
            else:
                i += 1
        verts = []
        e = int(math.ceil(0.75 * t + 1))
        K = max(5, int(3 * t) + 3)
        for k in cands:
            got = None
            # Flank fits on clean, non-turning columns beyond the join region.
            li = [q for q in range(max(0, k - e - K), k - e + 1) if clean[q] and abs(turn[q]) < 0.3]
            ri = [q for q in range(k + e, min(n, k + e + K + 1)) if clean[q] and abs(turn[q]) < 0.3]
            if len(li) >= 4 and len(ri) >= 4:
                a1, b1, r1 = _fit_line(xs[li].astype(float), cen[li])
                a2, b2, r2 = _fit_line(xs[ri].astype(float), cen[ri])
                tol1, tol2 = 0.3 + 0.05 * abs(b1), 0.3 + 0.05 * abs(b2)
                ang = abs(math.degrees(math.atan(b1) - math.atan(b2)))
                # A real polyline peak has flanks that bend AWAY from the apex: for an up-apex
                # (smaller y is higher on screen), the left flank's cen decreases with x and the
                # right flank's cen increases. The opposite for a down-apex. When the fits are
                # on the same side of flat (both nearly horizontal, or both tilted the same way)
                # the intersection sits at infinity or on the wrong side of the apex and the
                # columns around a narrow spike are not join columns at all.
                dir_ok = (turn[k] > 0 and b1 < -0.05 and b2 > 0.05) or (turn[k] < 0 and b1 > 0.05 and b2 < -0.05)
                if r1 < tol1 and r2 < tol2 and ang >= 8 and dir_ok and abs(b1 - b2) > 1e-6:
                    xi = (a2 - a1) / (b1 - b2)
                    yi = a1 + b1 * xi
                    r = runs[k]
                    if abs(xi - xs[k]) <= e + 1.5 and r[0] - 0.75 * t <= yi <= r[1] + 0.75 * t:
                        got = (xi, yi, "flank")
                        # The join: the two strokes overlap out to t / (2 tan(theta / 2)) from the vertex
                        # along each flank, and the columns there take the polyline's own values.
                        half_angle = math.radians(max(4.0, min(176.0, 180.0 - ang))) / 2
                        e2 = int(math.ceil(max(e, 0.5 * t / math.tan(half_angle) + 1)))
                        e2 = min(e2, e + K)
                        ki = int(round(xi)) - int(xs[0])  # index of the column holding the vertex
                        for q in range(max(0, ki - e2), min(n, ki + e2 + 1)):
                            values[q] = (a1 + b1 * xs[q]) if xs[q] < xi else (a2 + b2 * xs[q])
                            clean[q] = True
            if got is None:
                # The apex column itself; the tip's x is the horizontal centroid of the ink in the
                # outermost stroke's worth of rows, over the join columns.
                r = runs[k]
                up = turn[k] > 0
                Wm = self.Wm
                if up:
                    ya, yb = int(math.floor(r[0] - self.y_off)), int(math.ceil(r[0] - self.y_off + t))
                else:
                    ya, yb = int(math.floor(r[1] - self.y_off - t)), int(math.ceil(r[1] - self.y_off))
                ya, yb = max(0, ya), min(Wm.shape[0], yb + 1)
                xa, xb = max(0, k - e), min(n, k + e + 1)
                patch = Wm[ya:yb, xa:xb]
                m = float(patch.sum())
                dx = 0.0
                if m > 0:
                    cx = float((patch.sum(0) * np.arange(xa, xb)).sum() / m)
                    dx = float(np.clip(cx - k, -e, e))
                got = (xs[k] + dx, values[k], "apex")
                # Earlier the spike-triangle fill overwrote every neighbour column of a narrow
                # apex with a linear ramp from the first "small-span" baseline column to the tip.
                # On narrow-peaks the walk crossed the whole spike before finding a baseline run
                # and then painted every flank column with the baseline value, turning the chart
                # into a flat line punctuated by one tip (corpus 0.211% -> 6.104%). The vertex is
                # inserted as its own point in the trace; the flank columns' own centroids, even
                # when biased by a tall merged run, track the spike far better than a flat fill.
            verts.append(got)
        return verts


def refine_lines(img: np.ndarray, ex, paper: np.ndarray | None = None):
    """Re-measure each traced line on the source pixels (see the module docstring)."""
    from .extract import _paper_colour

    if not ex.series:
        return ex
    imf = img.astype(np.float32)
    if paper is None:
        paper = _paper_colour(img, ex.plot_area).astype(np.float32)
    s = math.hypot(ex.M[0, 0], ex.M[1, 0])
    for se in ex.series:
        if se.kind != "line" or len(se.line_px) < 3:
            continue
        lm = LineMeasure(imf, paper, se.color, se.line_px, se.markers_px, s, se.ridge_px,
                         se.vertices_px[:, 0] if se.vertices_px is not None and len(se.vertices_px) else None)
        pts, verts, fb = lm.measure()
        if len(pts) < 3:
            continue
        # The network's own corners stay only where the column under them could not be measured.
        if se.vertices_px is not None and len(se.vertices_px):
            keep = []
            for vx, vy in se.vertices_px:
                i = int(round(vx)) - lm.x_off
                if 0 <= i < len(fb) and fb[i]:
                    keep.append((vx, vy))
            if keep:
                v = np.array(keep)
                far = np.min(np.abs(pts[:, 0][:, None] - v[None, :, 0]), axis=1) > 1.0
                pts = np.vstack([pts[far], v])
                pts = pts[np.argsort(pts[:, 0], kind="stable")]
                verts = np.vstack([verts, v]) if len(verts) else v
        se.line_px = pts
        se.vertices_px = verts if len(verts) else None
        se.fallback_frac = float(fb.mean())
    return ex
