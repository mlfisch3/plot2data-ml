"""Unit tests for the deterministic parts of the learned pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.calibrate import fit_axis
from p2d.data import apply, densify, fit_transform, splat_min_dist, turning_vertices
from p2d.extract import refine_peak
from p2d.ocr import decode, encode, parse_value, CHARS
from p2d.sampling import auto_step, reconstruction_error


@pytest.mark.parametrize("text,value", [
    ("1,000", 1000), ("-2.5", -2.5), ("−3", -3), ("45%", 45), ("$1.2M", 1.2e6), ("3e5", 3e5), ("10^3", 1e3),
    ("10^-2", 0.01), ("2x10^4", 2e4), ("-$1,200", -1200), ("1.5k", 1500), ("2.50e+08", 2.5e8), ("0.000", 0.0),
])
def test_parse_value(text, value):
    assert parse_value(text) == pytest.approx(value)


@pytest.mark.parametrize("text,value", [
    # OWID "25 t" style labels and their OCR variants (lowercase 't' is a tonne unit, scale 1).
    ("25 t", 25), ("25t", 25), ("0 t", 0), ("15 t", 15),
    # Word-form SI suffixes - OWID "500 billion t", "$1 billion".
    ("500 billion", 500e9), ("1 billion", 1e9), ("$1 billion", 1e9),
    ("500 million", 500e6), ("500 thousand", 500e3), ("500 trillion", 500e12),
    ("500 billion t", 500e9),  # trailing noise ignored
    # Lowercase SI letters as the first glyph of a word suffix (ocr charset lacks `i`/`m`/`h`,
    # so "500 billion t" surfaces as "500b   n 1"; "500b"-anything should still read as 5e11).
    ("500b", 500e9), ("500 b", 500e9), ("200b   n 1", 200e9), ("0b n", 0),
    # Trailing noise that is NOT a known suffix letter also strips, provided it starts with a
    # space or letter (OWID "2,000 TWh" OCRs as "2,000 1 " with a stray '1' from the misread 'T').
    ("2,000  ", 2000), ("2,000 1 ", 2000), ("1,000 1 ", 1000),
])
def test_parse_value_lenient(text, value):
    assert parse_value(text) == pytest.approx(value)


@pytest.mark.parametrize("text,value", [
    # Plain numeric strings must stay as themselves even after lenient-suffix support -
    # the trailing-digit tail in "151" is a real digit, not an OCR'd 't'.
    ("151", 151), ("201", 201), ("251", 251), ("5001", 5001), ("15.1", 15.1),
    # Multi-char suffixes still land on their intended scale.
    ("$1T", 1e12), ("$800B", 800e9), ("1.5k", 1500),
])
def test_parse_value_strict_unchanged(text, value):
    assert parse_value(text) == pytest.approx(value)


@pytest.mark.parametrize("text", ["", "1,00", "abc", "Jan", "Marne 1", "Mc"])
def test_parse_value_rejects(text):
    assert parse_value(text) is None


def test_ctc_decode_collapses_repeats_and_blanks():
    seq = [encode("1")[0], encode("1")[0], 0, encode("1")[0], encode("0")[0], 0]
    lp = np.full((len(seq), len(CHARS) + 1), -20.0)
    lp[np.arange(len(seq)), seq] = 0.0
    assert decode(lp)[0] == "110"


def test_linear_fit_ignores_a_misread():
    pos = [100, 200, 300, 400, 500]
    vals = [0, 10, 20, 80, 40]  # 30 misread as 80
    f = fit_axis(pos, vals)
    assert f.scale == "linear"
    assert f.inliers == 4
    assert f.to_value(400) == pytest.approx(30, abs=1e-6)


def test_log_fit_chosen_for_decades():
    pos = [500, 400, 300, 200]
    vals = [1, 10, 100, 1000]
    f = fit_axis(pos, vals, ["10^0", "10^1", "10^2", "10^3"])
    assert f.scale == "log"
    assert f.to_value(250) == pytest.approx(10 ** 2.5)


def test_two_ticks_default_linear_unless_labels_say_log():
    assert fit_axis([100, 200], [10, 20]).scale == "linear"
    assert fit_axis([100, 200], [10, 100], ["10^1", "10^2"]).scale == "log"


def test_auto_step_keeps_a_spike_and_relaxes_on_smooth():
    x = np.arange(0, 800.0)
    smooth = 10 * np.sin(x / 80)
    s = auto_step(x, smooth, tol=0.5)
    assert s > 20
    assert reconstruction_error(x, smooth, s) <= 0.5
    spiky = smooth + np.where(np.abs(x - 400) < 6, 40 - np.abs(x - 400) * 6.0, 0)
    assert auto_step(x, spiky, tol=0.5) < s / 4


def test_fit_transform_maps_pixel_centres_and_corners():
    M = fit_transform(1536, 1024)  # exactly 2x the canvas
    p = apply(M, [[-0.5, -0.5], [1535.5, 1023.5]])
    assert p[0] == pytest.approx([-0.5, -0.5])
    assert p[1] == pytest.approx([767.5, 511.5])


def test_distance_field_is_exact_to_a_polyline():
    path = np.array([[10.0, 10.3], [40.0, 10.3]])
    d = splat_min_dist(densify(path, 0.25), 32, 64, 4)
    assert d[10, 20] == pytest.approx(0.3, abs=1e-3)
    assert d[12, 25] == pytest.approx(1.7, abs=1e-3)
    assert np.isinf(d[20, 20])


def test_turning_vertices_only_visible_corners():
    path = np.array([[0, 0], [10, 0], [20, 10], [20.5, 10.1], [30, 10]], float)
    v = turning_vertices(path)
    assert len(v) == 1 and v[0] == pytest.approx([10, 0])


def test_parabola_peak_recovers_subpixel_gaussian_centre():
    yy, xx = np.mgrid[0:20, 0:20]
    h = np.exp(-0.5 * (((xx - 9.3) ** 2 + (yy - 10.7) ** 2) / 1.5 ** 2))
    x, y = refine_peak(h, 9, 11)
    assert x == pytest.approx(9.3, abs=1e-6)
    assert y == pytest.approx(10.7, abs=1e-6)


def test_placement_keeps_small_charts_and_reads_large_ones_natively():
    from p2d.data import CANVAS_H, CANVAS_W
    from p2d.data import placement

    # A chart smaller than the canvas is placed exactly as in training (scaled up to fit, at most 2x).
    M, size = placement(400, 300)
    assert size == (CANVAS_W, CANVAS_H)
    assert M[0, 0] == pytest.approx(min(CANVAS_W / 400, CANVAS_H / 300, 2.0))
    # A chart larger than the canvas is read at scale 1 on a canvas grown to hold it, in multiples of 32.
    M, size = placement(1400, 880)
    assert M[0, 0] == 1.0 and M[1, 1] == 1.0
    assert size == (1408, 896)
    assert apply(M, [[0, 0]])[0] == pytest.approx([0, 0])  # pixel centres map to pixel centres
    # Beyond the pixel budget the scale drops, but never below the fit scale, and the canvas stays a multiple of 32.
    M, size = placement(3000, 2000)
    assert M[0, 0] < 1.0
    assert M[0, 0] >= min(CANVAS_W / 3000, CANVAS_H / 2000)
    assert size[0] % 32 == 0 and size[1] % 32 == 0
    assert size[0] * size[1] <= 1.3e6 + 32 * (size[0] + size[1])
    # Native placement can be switched off.
    M, size = placement(1400, 880, native=False)
    assert size == (CANVAS_W, CANVAS_H) and M[0, 0] == pytest.approx(min(CANVAS_W / 1400, CANVAS_H / 880))


def _axes_image(ticks_y, ticks_x, axis_x=60, axis_y=240, w=320, h=260):
    """White paper, a left and a bottom axis line, tick marks outside, no gridlines, no frame."""
    img = np.full((h, w, 3), 255, np.uint8)
    img[:, axis_x] = 80
    img[axis_y, :] = 80
    for y in ticks_y:
        img[y, axis_x - 5:axis_x] = 80
    for x in ticks_x:
        img[axis_y + 1:axis_y + 6, x] = 80
    return img


def test_refine_ticks_snaps_to_tick_marks_without_a_frame():
    from p2d.extract import Extraction, refine_ticks

    ty, tx = [40, 90, 140, 190], [100, 160, 220, 280]
    img = _axes_image(ty, tx)
    ex = Extraction(M=np.eye(2, 3), plot_area=None)
    # The network's estimates, a pixel and a half off, with the label boxes on the outside.
    ex.yticks = [dict(pos=y + 1.5, anchor=[60.0, y + 1.5], score=1.0, label_box=[20, y - 5, 50, y + 5]) for y in ty]
    ex.xticks = [dict(pos=x - 1.5, anchor=[x - 1.5, 240.0], score=1.0, label_box=[x - 10, 248, x + 10, 258]) for x in tx]
    refine_ticks(img, ex)
    for t, y in zip(ex.yticks, ty):
        assert t["pos"] == pytest.approx(y, abs=0.05) and t["pos_net"] == y + 1.5
    for t, x in zip(ex.xticks, tx):
        assert t["pos"] == pytest.approx(x, abs=0.05) and t["pos_net"] == x - 1.5


def test_affine_from_marks_pure_shift_identifiable_slope():
    # Six marks, every one shifted by exactly -1.5 px. The fit should return b = 1 and a = -1.5.
    from p2d.extract import _affine_from_marks

    pos_net = np.array([40.0, 90.0, 140.0, 190.0, 240.0, 290.0])
    marks = pos_net - 1.5
    w = np.ones_like(pos_net)
    a, b, inliers, mad = _affine_from_marks(pos_net, marks, w, slope_tol=0.015, resid_tol=0.35)
    assert b == pytest.approx(1.0, abs=5e-4)
    assert a == pytest.approx(-1.5, abs=5e-4)
    assert inliers.all() and mad < 1e-6


def test_affine_from_marks_recovers_shift_and_scale():
    # The network's tick positions carry a per-axis scale drift of 1 part in 400
    # (0.25%). Six marks are enough to see it; the fit should land within 0.02 px.
    from p2d.extract import _affine_from_marks

    pos_net = np.array([40.0, 90.0, 140.0, 190.0, 240.0, 290.0])
    a_true, b_true = -1.2, 1.0025  # 0.25% expansion, slope within the N=6 window.
    marks = a_true + b_true * pos_net
    w = np.ones_like(pos_net)
    a, b, inliers, mad = _affine_from_marks(pos_net, marks, w, slope_tol=0.015, resid_tol=0.35)
    assert b == pytest.approx(b_true, abs=5e-4)
    assert a == pytest.approx(a_true, abs=0.05)
    assert inliers.all() and mad < 1e-6


def test_affine_from_marks_rejects_a_wrong_tick_mark():
    # One mark is 2 px off (a glyph stroke misdetected). The IRLS outlier
    # rejection must drop it, and the fit over the remaining five must land
    # on the true shift.
    from p2d.extract import _affine_from_marks

    pos_net = np.array([40.0, 90.0, 140.0, 190.0, 240.0, 290.0])
    marks = pos_net - 1.5
    marks[2] = pos_net[2] + 0.9  # 2.4 px off the fit line
    w = np.ones_like(pos_net)
    a, b, inliers, mad = _affine_from_marks(pos_net, marks, w, slope_tol=0.015, resid_tol=0.35)
    assert not inliers[2] and int(inliers.sum()) == 5
    assert b == pytest.approx(1.0, abs=5e-4)
    assert a == pytest.approx(-1.5, abs=5e-4)
    assert mad < 1e-6


def test_affine_from_marks_falls_back_to_shift_when_slope_runs_away():
    # Four marks only (shift-only regime), with one outlier. _affine_from_marks
    # must still return a usable shift when the slope cannot be identified at all.
    from p2d.extract import _affine_from_marks

    pos_net = np.array([40.0, 90.0, 140.0, 190.0])
    marks = pos_net - 0.7
    w = np.ones_like(pos_net)
    a, b, inliers, mad = _affine_from_marks(pos_net, marks, w, slope_tol=0.0, resid_tol=0.35)
    assert b == 1.0
    assert a == pytest.approx(-0.7, abs=5e-3)
    assert inliers.all() and mad < 1e-6


def test_refine_ticks_affine_corrects_a_scale_drift():
    # Six x-axis ticks whose network positions are stretched by 1 part in 200
    # across the plot. The joint fit should pull every tick back to the drawn
    # mark; the previous shift-only logic would have left the end ticks ~0.6 px off.
    from p2d.extract import Extraction, refine_ticks

    tx = [60, 110, 160, 210, 260, 300]
    img = _axes_image([40, 90, 140, 190, 240], tx, w=360)
    ex = Extraction(M=np.eye(2, 3), plot_area=None)
    # Scale drift centred on the plot: pos_net = (true - 180) / 1.005 + 180, with a 0.4 px shift.
    def net_pos(x: float) -> float:
        return (x - 180.0) * 1.005 + 180.0 - 0.4
    ex.xticks = [dict(pos=net_pos(x), anchor=[net_pos(x), 240.0], score=1.0, label_box=[x - 10, 248, x + 10, 258]) for x in tx]
    ex.yticks = []  # not under test
    refine_ticks(img, ex)
    for t, x in zip(ex.xticks, tx):
        assert t["pos"] == pytest.approx(x, abs=0.1)
    # The record of the pre-refinement position is kept.
    assert all("pos_net" in t for t in ex.xticks)


def test_refine_ticks_keeps_three_mark_axis_shift_only():
    # Three ticks is the shift-only regime: an affine fit is not identifiable.
    # The result must match the single-median shift behaviour of the baseline.
    from p2d.extract import Extraction, refine_ticks

    ty = [50, 120, 190]
    img = _axes_image(ty, [100, 160, 220])
    ex = Extraction(M=np.eye(2, 3), plot_area=None)
    ex.yticks = [dict(pos=y + 0.9, anchor=[60.0, y + 0.9], score=1.0, label_box=[20, y - 5, 50, y + 5]) for y in ty]
    ex.xticks = []
    refine_ticks(img, ex)
    # Each tick moves by essentially the same shift and lands within half a pixel of the mark.
    for t, y in zip(ex.yticks, ty):
        assert t["pos"] == pytest.approx(y, abs=0.5)
        assert t["pos_net"] == y + 0.9


def test_log_needs_a_decade_or_a_label_saying_so():
    # Years 1970..2021 with the last label misplaced: a log fit would take all six, but is absurd.
    pos = [29, 81, 133, 184, 236, 293]
    f = fit_axis(pos, [1970, 1980, 1990, 2000, 2010, 2021])
    assert f.scale == "linear"
    assert fit_axis([100, 200, 300], [1, 10, 100]).scale == "log"
    assert fit_axis([100, 200], [2, 4], ["2x10^0", "4x10^0"]).scale == "log"


def test_crop_shift_keeps_the_middle_third_of_the_plot_in_view():
    from p2d.data import _crop_shift

    rng = np.random.default_rng(0)
    # A chart 2000 px wide with its plot area at 200..1800 on a 768 px canvas: whatever the shift,
    # the plot's middle third (733..1267) stays inside [0, 768).
    for _ in range(200):
        s = _crop_shift(rng, 200.0, 1800.0, 2000.0, 768)
        assert 200 + s + 1600 / 3 >= 0 and 200 + s + 2 * 1600 / 3 <= 768
    # A chart smaller than the canvas only slides within it.
    for _ in range(50):
        s = _crop_shift(rng, 50.0, 350.0, 400.0, 768)
        assert 0 <= s <= 768 - 400


def test_tta_fuses_passes_back_into_the_primary_canvas():
    """A fake network that marks one fixed source pixel: every pass must land it on the same canvas pixel."""
    import torch
    from p2d.data import N_HEAT, N_SEM, apply
    from p2d.extract import inv_affine
    from p2d.tta import run_net_tta

    class Net:
        def __init__(self):
            self.M = None  # set per pass from the canvas size, below

        def __call__(self, x):
            B, C, H, W = x.shape
            # The darkest canvas pixel is the dot; put a heat peak there.
            g = x[0].mean(0)
            idx = int(torch.argmin(g))
            heat = torch.full((1, N_HEAT, H, W), -10.0)
            heat[0, :, idx // W, idx % W] = 10.0
            return {"sem": torch.zeros(1, N_SEM, H, W), "heat": heat, "emb": torch.zeros(1, 8, H, W)}

    img = np.full((300, 400, 3), 255, np.uint8)
    img[120, 200] = 0  # one black pixel
    out, M = run_net_tta(Net(), img, device="cpu", native=True, tta="shift+scale")
    cx, cy = apply(M, [[200, 120]])[0]
    hy, hx = np.unravel_index(np.argmax(out["heat"][0]), out["heat"][0].shape)
    assert abs(hx - cx) <= 1 and abs(hy - cy) <= 1
    # Three passes fused: the primary (exactly 1 at the peak), the shifted and the scaled ones.
    assert 0.3 < out["heat"][0].max() <= 1.0


def test_axis_labels_in_strip_classifies_y_labels_only():
    """A FRED-style y label strip (left of the plot) is picked up; title text further left is not."""
    from p2d.extract import _axis_labels_in_strip

    frame = (100.0, 50.0, 500.0, 400.0)
    y_labels = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]  # three stacked
    title = [[15.0, 180.0, 28.0, 240.0]]  # a narrow axis-title piece far to the left
    x_label = [[200.0, 410.0, 230.0, 420.0]]  # below the plot (an x label)
    y_strip = _axis_labels_in_strip(y_labels + title + x_label, frame, horizontal=False)
    assert [b for b in y_labels] == y_strip
    x_strip = _axis_labels_in_strip(y_labels + title + x_label, frame, horizontal=True)
    assert x_strip == x_label


def test_promote_label_only_ticks_adds_virtual_ticks_from_unclaimed_y_labels():
    """A chart with no visible tick marks: the semantic layer still catches the y labels."""
    from p2d.extract import Extraction, _promote_label_only_ticks, inv_affine

    M = np.eye(2, 3)
    Mi = inv_affine(M)
    frame = [100.0, 50.0, 500.0, 400.0]
    ex = Extraction(M=M, plot_area=list(frame))
    # No real ticks found on either axis; the y strip has three label boxes.
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    claimed: list[list[float]] = []
    _promote_label_only_ticks(ex, boxes, claimed, frame, Mi)
    assert len(ex.yticks) == 3
    for t, b in zip(sorted(ex.yticks, key=lambda t: t["pos"]), boxes):
        assert t["pos"] == pytest.approx(0.5 * (b[1] + b[3]), abs=0.5)
        assert t["label_box"] == b


def test_promote_label_only_ticks_does_not_duplicate_an_existing_tick():
    """A heat peak at a label's y position already claims it; no virtual tick is added there."""
    from p2d.extract import Extraction, _promote_label_only_ticks, inv_affine

    M = np.eye(2, 3)
    Mi = inv_affine(M)
    frame = [100.0, 50.0, 500.0, 400.0]
    ex = Extraction(M=M, plot_area=list(frame))
    ex.yticks = [dict(pos=185.0, anchor=[100.0, 185.0], score=0.5,
                      label_box=[78.0, 180.0, 95.0, 190.0])]
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    claimed = [[78.0, 180.0, 95.0, 190.0]]
    _promote_label_only_ticks(ex, boxes, claimed, frame, Mi)
    # One real tick already there; two new virtual ticks added for the top and bottom labels.
    assert len(ex.yticks) == 3
    positions = sorted(t["pos"] for t in ex.yticks)
    assert positions[0] == pytest.approx(65.0, abs=0.5)
    assert positions[1] == pytest.approx(185.0, abs=0.5)
    assert positions[2] == pytest.approx(305.0, abs=0.5)


def test_peak_has_label_rejects_a_peak_far_from_any_label():
    """The weak-peak pass only keeps peaks that line up with a tick label."""
    from p2d.extract import _peak_has_label

    frame = (100.0, 50.0, 500.0, 400.0)
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 300.0, 95.0, 310.0]]
    # x is the peak's canvas x; y is the peak's canvas y.
    assert _peak_has_label(100.0, 65.0, boxes, horizontal=False, frame=frame)
    assert _peak_has_label(100.0, 305.0, boxes, horizontal=False, frame=frame)
    assert not _peak_has_label(100.0, 180.0, boxes, horizontal=False, frame=frame)  # no label at 180


def test_needs_axis_fallback_fires_only_when_label_boxes_are_mostly_unclaimed():
    """Strong peaks at every label: no fallback. Few weak peaks for many labels: fire."""
    from p2d.extract import _needs_axis_fallback

    frame = (100.0, 50.0, 500.0, 400.0)
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    full_peaks = [(100.0, 65.0, 0.5), (100.0, 185.0, 0.5), (100.0, 305.0, 0.5)]
    assert not _needs_axis_fallback(frame, boxes, full_peaks, horizontal=False)
    one_peak = [(100.0, 65.0, 0.5)]
    assert _needs_axis_fallback(frame, boxes, one_peak, horizontal=False)


def test_axis_factor_rejects_a_fake_multiplier_far_from_the_spine():
    # fred-dgs10-dgs2: no `1eN` multiplier is printed on the chart, but `_end_search`'s wide
    # scan picks up legend glyph sequences near the top of the plot. The spine-margin filter
    # in `axis_factor` must reject matches whose x-centre is well away from either axis spine,
    # otherwise a bogus `1e3` from the chart title / legend text multiplies every y value by 1000.
    import numpy as np
    from p2d.extract import Extraction
    from p2d.pipeline import axis_factor

    class FakeReader:
        """Always decodes whatever crop it is given as `1e3`. Mocks the OCR noise that trips
        up the FRED chart in the real pipeline."""
        def __call__(self, *_args, **_kw):
            raise RuntimeError("tests should go through read_crops, not call the reader directly")

    def fake_read_crops(_reader, crops):
        return [("1e3", 0.0)] * len(crops)

    import p2d.pipeline as pipe_mod
    orig_read = pipe_mod.read_crops
    pipe_mod.read_crops = fake_read_crops
    try:
        # Plot area at (73, 62, 1079, 539): the FRED chart's layout. A loose label whose centre
        # sits ~221 px from the left spine (well past 0.1*w = 100) must not count.
        img = np.full((623, 1100, 3), 255, np.uint8)
        far_box = [281.0, 13.0, 308.0, 26.0]
        ex = Extraction(M=np.eye(2, 3), plot_area=[73.0, 62.0, 1079.0, 539.0], loose_labels=[far_box])
        scale, shift, text = axis_factor(FakeReader(), img, ex, "y")
        assert (scale, shift, text) == (1.0, 0.0, None)
        # A box right at the left spine (within 20 px of x0) still fires, so the matplotlib
        # offset-annotation case keeps working.
        near_box = [78.0, 13.0, 110.0, 26.0]
        ex = Extraction(M=np.eye(2, 3), plot_area=[73.0, 62.0, 1079.0, 539.0], loose_labels=[near_box])
        scale, shift, text = axis_factor(FakeReader(), img, ex, "y")
        assert scale == 1000.0 and shift == 0.0 and text == "1e3"
    finally:
        pipe_mod.read_crops = orig_read
    # Three labels but only one weak hit: FRED's missing-tick case, fallback fires.
    one_weak_peak = [(100.0, 65.0, 0.4)]
    assert _needs_axis_fallback(frame, boxes, one_weak_peak, horizontal=False)


def test_needs_axis_fallback_blocked_when_strong_peak_is_confident():
    """A healthy strong peak above 0.6 keeps the weak pass from firing even if the strip
    has unclaimed non-tick boxes (axis titles, offsets). This is the mpl-val protection."""
    from p2d.extract import _needs_axis_fallback

    frame = (100.0, 50.0, 500.0, 400.0)
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    # The strong pass found one tick at score 0.8 (healthy detector), the two other
    # strip boxes are stray strip text, not missed ticks.
    confident_peak = [(100.0, 65.0, 0.8)]
    assert not _needs_axis_fallback(frame, boxes, confident_peak, horizontal=False)


def test_needs_axis_fallback_soft_band_requires_three_strong_hits():
    """Max heat in [0.5, 0.6) is a soft band: dexuseu-style charts (three ticks caught,
    more needed to shrink the refine window) fire, 2-tick mpl-val cases stay out."""
    from p2d.extract import _needs_axis_fallback

    frame = (100.0, 50.0, 500.0, 400.0)
    # Five label boxes, three with strong hits in the 0.5-0.6 band.
    boxes = [
        [78.0, 60.0, 95.0, 70.0],
        [78.0, 120.0, 95.0, 130.0],
        [78.0, 180.0, 95.0, 190.0],
        [78.0, 240.0, 95.0, 250.0],
        [78.0, 300.0, 95.0, 310.0],
    ]
    three_strong = [(100.0, 65.0, 0.55), (100.0, 125.0, 0.55), (100.0, 185.0, 0.55)]
    assert _needs_axis_fallback(frame, boxes, three_strong, horizontal=False)
    # Two strong hits in the same band do not open the gate: this is the 9000118
    # 2-tick mpl-val case, where the real axis already has every tick it should.
    two_strong = [(100.0, 65.0, 0.55), (100.0, 185.0, 0.55)]
    assert not _needs_axis_fallback(frame, boxes, two_strong, horizontal=False)


def test_needs_axis_fallback_blocked_when_strong_peaks_scatter_outside_strip():
    """A noisy heat channel: half the strong peaks sit far from the strip. Firing a
    weak pass only turns the noise into ticks, so the gate stays shut even when
    there are unclaimed labels at low heat."""
    from p2d.extract import _needs_axis_fallback

    frame = (100.0, 50.0, 500.0, 400.0)
    boxes = [[78.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    # Three strong peaks: one in the strip (near x=100, which is fx0), two scattered
    # across the plot interior (x=250, x=400 are both >50 px right of the axis).
    scattered = [(100.0, 65.0, 0.4), (250.0, 150.0, 0.4), (400.0, 220.0, 0.4)]
    assert not _needs_axis_fallback(frame, boxes, scattered, horizontal=False)


def test_promote_label_only_ticks_skipped_when_axis_has_enough_ticks():
    """Virtual-tick promotion stops once the heat passes have already filled an axis.
    This stops stray strip text from being promoted on healthy mpl-val charts."""
    from p2d.extract import Extraction, _promote_label_only_ticks, inv_affine

    M = np.eye(2, 3)
    Mi = inv_affine(M)
    frame = [100.0, 50.0, 500.0, 400.0]
    ex = Extraction(M=M, plot_area=list(frame))
    # Already two y ticks from strong pass; axis is well-covered.
    ex.yticks = [
        dict(pos=65.0, anchor=[100.0, 65.0], score=0.7, label_box=[80.0, 60.0, 95.0, 70.0]),
        dict(pos=185.0, anchor=[100.0, 185.0], score=0.7, label_box=[78.0, 180.0, 95.0, 190.0]),
    ]
    # Another unclaimed strip box exists but should not become a tick.
    boxes = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0], [78.0, 300.0, 95.0, 310.0]]
    claimed = [[80.0, 60.0, 95.0, 70.0], [78.0, 180.0, 95.0, 190.0]]
    _promote_label_only_ticks(ex, boxes, claimed, frame, Mi)
    assert len(ex.yticks) == 2
