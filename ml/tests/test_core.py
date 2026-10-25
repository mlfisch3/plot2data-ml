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


@pytest.mark.parametrize("text", ["", "1,00", "abc", "Jan"])
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
