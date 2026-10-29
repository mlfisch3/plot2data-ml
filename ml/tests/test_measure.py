"""The source-pixel line measurement, on strokes drawn by matplotlib with known geometry."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from p2d.measure import LineMeasure, ink_weights  # noqa: E402

PAPER = np.array([255, 255, 255], np.float32)
INK = (200, 60, 30)


def render(path, lw_px, W=300, H=200, join="round"):
    """A polyline in pixel coordinates (the centre of pixel i is i), as the synthetic charts draw them."""
    with plt.rc_context({"path.simplify": False}):
        fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
        canvas = FigureCanvasAgg(fig)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(-0.5, W - 0.5)
        ax.set_ylim(H - 0.5, -0.5)
        ax.axis("off")
        p = np.asarray(path, float)
        (ln,) = ax.plot(p[:, 0], p[:, 1], lw=lw_px * 72 / 100, color="#c83c1e", solid_joinstyle=join,
                        solid_capstyle="butt")
        ln.set_snap(False)
        canvas.draw()
        img = np.asarray(canvas.buffer_rgba())[..., :3].copy()
        plt.close(fig)
    return img.astype(np.float32)


def trace(xs, ys, noise=0.4, seed=0):
    """A network-like trace: one sample per 1.1 columns, off by a few tenths of a pixel."""
    rng = np.random.default_rng(seed)
    return np.column_stack([xs, ys + rng.normal(0, noise, len(xs))]), np.column_stack([xs, ys - 3, ys + 3])


def test_ink_weights_follow_the_blend():
    img = np.array([[[255, 255, 255], [200, 60, 30], [227.5, 157.5, 142.5], [0, 0, 255]]], np.float32)
    w = ink_weights(img, PAPER, np.array(INK, np.float32))
    assert w[0, 0] == 0 and w[0, 1] == pytest.approx(1.0) and w[0, 2] == pytest.approx(0.5, abs=1e-3) and w[0, 3] == 0


@pytest.mark.parametrize("lw", [1, 2, 4])
def test_flat_line_centroid_and_stroke_width(lw):
    img = render([(10, 100.3), (290, 100.3)], lw)
    xs = np.arange(10, 291, 1.1)
    # Trace is laid on the drawn line here, since the end columns fall through to the trace
    # when the butt cap's half mass drops the occlusion test. The strict 0.02 tolerance is on
    # the interior columns, where cen measures the stroke; the butt caps carry whatever the
    # network's trace said and are not expected to be sub-pixel.
    lp, ridge = trace(xs, np.full(len(xs), 100.3), noise=0.0)
    lm = LineMeasure(img, PAPER, INK, lp, np.zeros((0, 2)), 1.0, ridge)
    pts, verts, fb = lm.measure()
    assert np.abs(pts[:, 1] - 100.3).max() < 0.02
    assert lm.dbg["t"] == pytest.approx(lw, abs=0.05)
    assert fb.mean() < 0.1  # the butt caps at the two ends drop out of the clean set


@pytest.mark.parametrize("join", ["round", "miter"])
@pytest.mark.parametrize("lw", [1, 2, 4])
def test_sharp_polyline_vertices_are_recovered_by_flank_intersection(lw, join):
    vx = [50, 100, 150, 200, 250]
    vy = [150, 30, 150, 30, 150]
    img = render(list(zip(vx, vy)), lw, join=join)
    xs = np.arange(50, 251, 1.1)
    lp, ridge = trace(xs, np.interp(xs, vx, vy))
    lm = LineMeasure(img, PAPER, INK, lp, np.zeros((0, 2)), 1.0, ridge)
    pts, verts, fb = lm.measure()
    for x, y in ((100, 30), (150, 150), (200, 30)):
        j = int(np.argmin(np.abs(verts[:, 0] - x)))
        assert abs(verts[j, 0] - x) < 0.1 and abs(verts[j, 1] - y) < 0.1
    inner = (pts[:, 0] > 55) & (pts[:, 0] < 245)
    err = pts[inner, 1] - np.interp(pts[inner, 0], vx, vy)
    assert np.median(np.abs(err)) < 0.05
    assert np.abs(err).max() < 0.6


def test_kinks_between_flat_and_steep_stretches():
    vx = [20, 120, 140, 200, 280]
    vy = [100, 100, 40, 160, 100]
    img = render(list(zip(vx, vy)), 2)
    xs = np.arange(20, 281, 1.1)
    lp, ridge = trace(xs, np.interp(xs, vx, vy))
    pts, verts, fb = LineMeasure(img, PAPER, INK, lp, np.zeros((0, 2)), 1.0, ridge).measure()
    err = pts[:, 1] - np.interp(pts[:, 0], vx, vy)
    assert np.median(np.abs(err)) < 0.02
    assert any(abs(v[0] - 140) < 0.1 and abs(v[1] - 40) < 0.1 for v in verts)
    assert any(abs(v[0] - 200) < 0.1 and abs(v[1] - 160) < 0.1 for v in verts)


def test_one_sample_spikes_reach_the_tip():
    xs_t = np.linspace(20, 280, 300)
    ys_t = np.full(300, 120.0)
    ys_t[5::10] = 40
    img = render(list(zip(xs_t, ys_t)), 2)
    cols = np.arange(20, 281)
    yt = np.interp(cols, xs_t, ys_t)
    # A blunt trace, halfway up every spike, with a ridge extent that does reach the tip.
    lp = np.column_stack([cols, 0.5 * yt + 60])
    top = np.full(len(cols), np.inf)
    for x, y in zip(xs_t, ys_t):
        i = int(round(x)) - cols[0]
        if 0 <= i < len(cols):
            top[i] = min(top[i], y)
    ridge = np.column_stack([cols, np.where(np.isfinite(top), top, 120) - 3, np.full(len(cols), 123.0)])
    pts, verts, fb = LineMeasure(img, PAPER, INK, lp, np.zeros((0, 2)), 1.0, ridge).measure()
    tips = [x for x, y in zip(xs_t, ys_t) if y < 100]
    at_tip = np.interp(tips, pts[:, 0], pts[:, 1]) - 40
    assert np.median(at_tip) < 1.5
    base = pts[np.abs(pts[:, 1] - 120) < 10, 1]
    assert np.median(np.abs(base - 120)) < 0.05


def test_low_contrast_ink_is_left_to_the_network():
    img = render([(10, 100.3), (290, 100.3)], 2, )
    xs = np.arange(10, 291, 1.1)
    lp, ridge = trace(xs, np.full(len(xs), 100.0), noise=0.0)
    lm = LineMeasure(img, PAPER, (250, 250, 250), lp, np.zeros((0, 2)), 1.0, ridge)
    pts, verts, fb = lm.measure()
    assert fb.all() and np.allclose(pts[:, 1], 100.0)
