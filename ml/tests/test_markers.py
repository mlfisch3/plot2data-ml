"""Markers measured on the pixels: size, centres of touching markers, conventions, dashes."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from p2d.extract import Extraction, Series  # noqa: E402
from p2d.markers import (_frac_cluster, ink_weight, line_stroke, measure_series, mixture_centres, paper_colour,  # noqa: E402
                         refine_markers, size_at, triangle_apex)


def _render(marker, ms, x, y, line=False, colour="k", dpi=100, size=(5, 4)):
    """An Agg-rendered scatter (or line+markers) and the recorded data positions in source px."""
    fig = plt.figure(figsize=size, dpi=dpi)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    if line:
        (art,) = ax.plot(x, y, ls="-", lw=1.5, marker=marker, markersize=ms, color=colour)
    else:
        art = ax.scatter(x, y, s=ms ** 2, marker=marker, color=colour)
    art.set_snap(False)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    canvas.draw()
    rgba = np.asarray(canvas.buffer_rgba())
    H = rgba.shape[0]
    pts = ax.transData.transform(np.column_stack([x, y]))
    gt = np.column_stack([pts[:, 0] - 0.5, H - pts[:, 1] - 0.5])
    plt.close(fig)
    return rgba[..., :3].copy(), gt


def _disc(cx, cy, r, H=40, W=40):
    yy, xx = np.mgrid[0:H, 0:W]
    return np.clip(r + 0.5 - np.hypot(xx - cx, yy - cy), 0, 1).astype(np.float32)


def test_ink_weight_is_blend_position():
    paper = np.array([255, 255, 255], np.float32)
    colour = np.array([255, 0, 0], np.float32)
    img = np.array([[[255, 255, 255], [255, 128, 128], [255, 0, 0], [0, 0, 255]]], np.float32)
    w = ink_weight(img, paper, colour)
    assert w[0, 0] == pytest.approx(0.0)
    assert w[0, 1] == pytest.approx(0.5, abs=0.01)
    assert w[0, 2] == pytest.approx(1.0)
    assert w[0, 3] == 0.0  # blue is off the white-to-red segment


def test_mixture_splits_touching_discs():
    w = np.maximum(_disc(15.3, 20.2, 5), _disc(22.1, 20.6, 5))  # overlapping discs, 6.8 px apart
    seeds = np.array([[14.0, 21.0], [23.0, 19.0]])
    c, mass = mixture_centres(w, seeds, sigma=3.5, radius=8)
    assert c[0] == pytest.approx([15.3, 20.2], abs=0.35)
    assert c[1] == pytest.approx([22.1, 20.6], abs=0.35)
    assert mass.min() > 20


def test_mixture_two_seeds_on_one_disc_end_within_the_merge_distance():
    w = _disc(20.4, 19.7, 7)
    c, _ = mixture_centres(w, np.array([[17.0, 19.0], [24.0, 21.0]]), sigma=4.0, radius=10)
    assert np.hypot(*(c[0] - c[1])) < 0.45 * 14  # measure_series merges centres closer than 0.45 of the size
    assert c.mean(0) == pytest.approx([20.4, 19.7], abs=0.15)


def test_size_through_a_line():
    mask = np.zeros((30, 60), bool)
    mask[14:17, :] = True  # a 3 px horizontal line
    yy, xx = np.mgrid[0:30, 0:60]
    mask |= np.hypot(xx - 30, yy - 15) <= 5.2  # an 11 px marker on it
    assert size_at(mask, 30, 15) == pytest.approx(11, abs=1)
    assert size_at(mask, 10, 15) == pytest.approx(3, abs=1)  # on the bare line: the stroke


def test_triangle_apex_orientation():
    yy, xx = np.mgrid[0:30, 0:30]
    up = ((yy >= 8) & (yy <= 22) & (np.abs(xx - 15) <= (yy - 8) * 0.55)).astype(np.float32)
    assert triangle_apex(up) == (0.0, -1.0)
    assert triangle_apex(up[::-1].copy()) == (0.0, 1.0)
    assert triangle_apex(up.T.copy()) == (-1.0, 0.0)
    disc = _disc(15, 15, 7, 30, 30)
    assert triangle_apex(disc) is None
    diamond = (np.abs(xx - 15) + np.abs(yy - 15) <= 8).astype(np.float32)
    assert triangle_apex(diamond) is None


def test_frac_cluster():
    m, r = _frac_cluster(np.array([3.0, 7.0, 12.0, 20.0, 1.0]))
    assert r > 0.99 and abs(m) < 0.01
    m, r = _frac_cluster(np.array([3.1, 7.3, 12.5, 20.7, 1.9]))
    assert r < 0.5


def test_snapped_series_lands_on_the_data_points():
    """matplotlib stamps markers on whole pixels; the measured centres must come back to the data points."""
    rng = np.random.default_rng(3)
    gx, gy = np.meshgrid(np.linspace(8, 92, 9), np.linspace(10, 90, 6))
    x = gx.ravel() + rng.uniform(-2, 2, gx.size)
    y = gy.ravel() + rng.uniform(-2, 2, gy.size)
    img, gt = _render("o", 7, x, y)
    paper = paper_colour(img, None)
    peaks = gt + rng.uniform(-1.5, 1.5, gt.shape)  # the network's rough estimate
    cen, rec = measure_series(img.astype(np.float32), paper, (0, 0, 0), peaks, (0, 0, img.shape[1], img.shape[0]))
    assert rec.snapped and rec.n_isolated == len(gt)
    assert len(cen) == len(gt)
    d = np.hypot(*(cen - gt).T)
    assert np.max(d) < 0.75  # the truth is uniform within the stamped pixel: at most half a pixel per axis
    # Without the convention the centroids would sit a mean half pixel off in both axes.
    assert abs(rec.size - 7 * 100 / 72) < 2.5


def test_triangles_get_matplotlibs_bbox_centre():
    rng = np.random.default_rng(5)
    gx, gy = np.meshgrid(np.linspace(8, 92, 8), np.linspace(10, 90, 5))
    x = gx.ravel() + rng.uniform(-2, 2, gx.size)
    y = gy.ravel() + rng.uniform(-2, 2, gy.size)
    for marker in ("^", "v"):
        img, gt = _render(marker, 12, x, y)
        paper = paper_colour(img, None)
        peaks = gt + rng.uniform(-1.5, 1.5, gt.shape)
        cen, rec = measure_series(img.astype(np.float32), paper, (0, 0, 0), peaks, (0, 0, img.shape[1], img.shape[0]))
        assert rec.shape == "tri" and rec.snapped
        d = np.hypot(*(cen - gt).T)
        assert np.median(d) < 0.8, marker


def test_line_markers_keep_markers_and_drop_dashes():
    x = np.linspace(5, 95, 12)
    y = 50 + 20 * np.sin(x / 15)
    img, gt = _render("o", 8, x, y, line=True)
    paper = paper_colour(img, None)
    # The traced line: the data path densified.
    xs = np.linspace(5, 95, 400)
    ys = 50 + 20 * np.sin(xs / 15)
    fig = plt.figure(figsize=(5, 4), dpi=100)
    ax = fig.add_subplot(111)
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    pts = ax.transData.transform(np.column_stack([xs, ys]))
    plt.close(fig)
    line = np.column_stack([pts[:, 0] - 0.5, img.shape[0] - pts[:, 1] - 0.5])
    # Peaks at the markers, plus two on the bare line between markers (the kind of thing dashes produce).
    mid = line[[60, 230]]
    peaks = np.vstack([gt, mid])
    cen, rec = measure_series(img.astype(np.float32), paper, (0, 0, 0), peaks, (0, 0, img.shape[1], img.shape[0]), line_px=line)
    assert rec.dropped == 2 and rec.stroke == pytest.approx(1.5 * 100 / 72, abs=1.0)
    assert len(cen) == len(gt)
    d = np.min(np.hypot(cen[:, None, 0] - gt[None, :, 0], cen[:, None, 1] - gt[None, :, 1]), axis=1)
    assert np.max(d) < 1.2


def test_dashed_line_is_not_a_scatter():
    fig = plt.figure(figsize=(5, 3), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    x = np.linspace(0, 100, 200)
    (art,) = ax.plot(x, 50 + 10 * np.sin(x / 10), ls="--", lw=2.5, color="k")
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    canvas.draw()
    img = np.asarray(canvas.buffer_rgba())[..., :3].copy()
    plt.close(fig)
    # Every dash a "marker": peaks at the centres of the dark blobs.
    import cv2
    m = (img[..., 0] < 128).astype(np.uint8)
    n, lab, stats, cent = cv2.connectedComponentsWithStats(m, 8)
    peaks = cent[1:]
    ex = Extraction(M=np.eye(2, 3), plot_area=None, series=[Series(kind="scatter", line_px=np.zeros((0, 2)), markers_px=peaks, color=(0, 0, 0))])
    ex = refine_markers(img, ex)
    assert all(len(s.markers_px) == 0 for s in ex.series)


def test_loose_peaks_join_their_colour():
    rng = np.random.default_rng(7)
    x = rng.uniform(10, 90, 10)
    y = rng.uniform(10, 90, 10)
    img, gt = _render("o", 6, x, y, colour="r")
    ex = Extraction(M=np.eye(2, 3), plot_area=None)
    ex.series = [Series(kind="scatter", line_px=np.zeros((0, 2)), markers_px=gt[:7], color=(255, 0, 0))]
    ex.loose_markers = np.vstack([gt[7:], [[3.0, 3.0]]])  # three red peaks and one on the paper
    ex = refine_markers(img, ex)
    assert len(ex.series) == 1 and len(ex.series[0].markers_px) == 10
