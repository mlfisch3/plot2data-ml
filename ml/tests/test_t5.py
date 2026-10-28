"""Tests for team t5's probe generators and the real-chart benchmark loader."""

from __future__ import annotations

import os
import shutil

import numpy as np
import pytest

from p2d.synth.probe_t5 import _affine_meta, _scale_meta, _shift_meta


def _meta():
    return dict(
        width=100, height=60, plot_area=[10.0, 5.0, 90.0, 50.0], xlim=[0, 1], ylim=[0, 1], xscale="linear", yscale="linear",
        xticks=[dict(value=0.5, pos=50.0, anchor=[50.0, 50.0], bbox=[45.0, 52.0, 55.0, 58.0], text="0.5")],
        yticks=[dict(value=0.5, pos=27.5, anchor=[10.0, 27.5], bbox=[1.0, 24.0, 8.0, 31.0], text="0.5")],
        series=[dict(kind="line", path_px=[[10.0, 50.0], [90.0, 5.0]], markers_px=[[50.0, 27.5]], linewidth_px=2.0, markersize_px=6.0)],
        legend_bbox=[60.0, 8.0, 85.0, 15.0],
    )


def test_scale_meta_maps_pixel_centres():
    m = _scale_meta(_meta(), 2.0)
    # Pixel centre i of the source lands at centre 2i + 0.5: the centre of the 2x2 block it becomes.
    assert m["plot_area"] == pytest.approx([20.5, 10.5, 180.5, 100.5])
    assert m["xticks"][0]["pos"] == pytest.approx(100.5)
    assert m["yticks"][0]["anchor"] == pytest.approx([20.5, 55.5])
    assert m["series"][0]["path_px"][1] == pytest.approx([180.5, 10.5])
    assert m["series"][0]["linewidth_px"] == 4.0
    assert m["width"] == 200 and m["height"] == 120


def test_shift_meta_moves_everything():
    m = _shift_meta(_meta(), 30, 20, 200, 120)
    assert m["plot_area"] == [40.0, 25.0, 120.0, 70.0]
    assert m["xticks"][0]["pos"] == 80.0 and m["xticks"][0]["anchor"] == [80.0, 70.0]
    assert m["yticks"][0]["pos"] == 47.5
    assert m["series"][0]["markers_px"] == [[80.0, 47.5]]
    assert m["legend_bbox"] == [90.0, 28.0, 115.0, 35.0]


def test_affine_meta_rotation_keeps_distances():
    import cv2

    R = cv2.getRotationMatrix2D((50.0, 30.0), 2.0, 1.0)
    m = _affine_meta(_meta(), R, 100, 60)
    p = np.array(m["series"][0]["path_px"])
    assert np.hypot(*(p[1] - p[0])) == pytest.approx(np.hypot(80, 45))
    # The bounding box of the rotated frame contains the rotated corners.
    assert m["plot_area"][0] <= 10.0 and m["plot_area"][2] >= 90.0
    assert m["xticks"][0]["pos"] == pytest.approx(m["xticks"][0]["anchor"][0])


def test_real_benchmark_truth_parsers(tmp_path):
    from p2d.eval_t5real import load_truth

    owid = tmp_path / "a.csv"
    owid.write_text("Entity,Code,Year,Life expectancy\nFrance,FRA,2000,79.1\nFrance,FRA,2001,79.3\nJapan,JPN,2000,81.2\nJapan,JPN,2001,81.5\n")
    t = load_truth({"kind": "owid"}, str(owid))
    assert set(t) == {"France", "Japan"}
    assert t["France"][1].tolist() == [79.1, 79.3]
    fred = tmp_path / "b.csv"
    fred.write_text("observation_date,UNRATE,CIVPART\n2000-01-01,4.0,67.3\n2000-07-01,.,67.1\n2001-01-01,4.2,67.2\n")
    t = load_truth({"kind": "fred"}, str(fred))
    assert t["UNRATE"][0].tolist() == pytest.approx([2000.0, 2001.0])  # the missing value is dropped
    assert t["CIVPART"][0][1] == pytest.approx(2000.0 + 182 / 366)
    t = load_truth({"kind": "fred", "q": "&cosd=2000-06-01&width=900"}, str(fred))
    assert t["CIVPART"][0].tolist() == pytest.approx([2000.0 + 182 / 366, 2001.0])  # the chart window cuts every series
    noaa = tmp_path / "c.csv"
    noaa.write_text("# comment\nyear,month,decimal date,average,deseasonalized,ndays,sdev,unc\n1958,3,1958.2027,315.71,314.44,-1,-9.99,-0.99\n1958,4,1958.2877,317.45,315.16,-1,-9.99,-0.99\n")
    t = load_truth({"kind": "noaa"}, str(noaa))
    assert t["average"][1].tolist() == [315.71, 317.45]


def test_real_benchmark_scoring_prefers_the_full_series():
    from p2d.eval_t5real import score_chart

    tx = np.linspace(2000, 2020, 21)
    ty = np.sin(tx)
    truth = {"s": (tx, ty)}

    class Res:
        series = [{"line": np.column_stack([tx[:5], ty[:5] + 0.001])},  # a short, near-perfect fragment
                  {"line": np.column_stack([tx, ty + 0.02])}]  # the whole series, 1% of the span off

    rows = score_chart({"q": ""}, truth, Res())
    assert rows[0]["cover"] == pytest.approx(1.0)
    assert rows[0]["rms_pct"] == pytest.approx(0.02 / (ty.max() - ty.min()) * 100, rel=1e-3)


@pytest.mark.skipif(shutil.which("node") is None or not os.path.exists("/usr/bin/google-chrome"), reason="needs node and Chrome")
def test_chartjs_truth_matches_the_render():
    """The recorded geometry must land on the ink: the plot frame on the border, the line on its pixels."""
    from p2d.synth.chartjs_render import generate
    from p2d.synth.mpl_render import AXIS, DATA

    r = generate(15200000)
    m = r.meta
    H, W = r.image.shape[:2]
    assert m["width"] == W and m["height"] == H
    pa = m["plot_area"]
    assert 0 <= pa[0] < pa[2] < W and 0 <= pa[1] < pa[3] < H
    for s in m["series"]:
        path = np.array(s["path_px"])
        if len(path) < 2:
            continue
        # Sample along the polyline and check the data class is within 2 px of each sample inside the frame.
        pts = []
        for a, b in zip(path[:-1], path[1:]):
            n = max(2, int(np.hypot(*(b - a)) / 3))
            pts += [a + (b - a) * t for t in np.linspace(0, 1, n)]
        pts = np.array(pts)
        inside = (pts[:, 0] > pa[0] + 2) & (pts[:, 0] < pa[2] - 2) & (pts[:, 1] > pa[1] + 2) & (pts[:, 1] < pa[3] - 2)
        hits = 0
        for x, y in pts[inside]:
            xi, yi = int(round(x)), int(round(y))
            if (r.sem[max(0, yi - 2): yi + 3, max(0, xi - 2): xi + 3] == DATA).any():
                hits += 1
        assert hits >= 0.9 * inside.sum()
    for t in m["xticks"] + m["yticks"]:
        b = t["bbox"]
        assert b[0] <= b[2] and b[1] <= b[3]
        assert t["text"]
    if any((r.sem == AXIS).ravel()):
        ys, xs = np.nonzero(r.sem == AXIS)
        # Axis ink lies along the frame edges (the border) or just outside them (tick marks, up to 10 px long).
        d = np.minimum.reduce([np.abs(xs - pa[0]), np.abs(xs - pa[2]), np.abs(ys - pa[1]), np.abs(ys - pa[3])])
        assert np.mean(d <= 1.5) >= 0.2 and np.max(d) <= 14
