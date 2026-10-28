"""The t4 probe generator: exact ground truth in the standard format, and the drawn-centre rule."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.synth import probe_t4 as G
from p2d.synth.mpl_render import CLASS_NAMES, DATA, TEXT


@pytest.mark.parametrize("kind", G.KINDS)
def test_every_kind_renders_with_consistent_truth(kind):
    r = G.generate(14990000 + G.KINDS.index(kind), kind)
    m = r.meta
    H, W = r.image.shape[:2]
    assert r.sem.shape == (H, W) and r.inst.shape == (H, W) and (m["width"], m["height"]) == (W, H)
    assert r.sem.max() < len(CLASS_NAMES)
    assert m["probe"]["kind"] == kind
    pa = m["plot_area"]
    assert 0 <= pa[0] < pa[2] <= W and 0 <= pa[1] < pa[3] <= H
    assert len(m["xticks"]) >= 2 and len(m["yticks"]) >= 2
    n_markers = 0
    for k, s in enumerate(m["series"]):
        mk = np.array(s["markers_px"]).reshape(-1, 2)
        drawn = np.array(s["markers_drawn_px"]).reshape(-1, 2)
        assert len(mk) == len(drawn)
        if s["kind"] == "line":
            assert len(mk) == 0 and len(s["path_px"]) == len(s["x"])
        else:
            assert len(mk) == len(s["x"]) > 0
            # The drawn centre is the display coordinate rounded: floor(exact + 1) per axis (the JSON keeps
            # three decimals, so a value within 0.001 of a pixel boundary may round across it).
            diff = drawn - np.floor(mk + 1.0)
            frac = (mk + 1.0) - np.floor(mk + 1.0)
            assert np.all((diff == 0) | (np.abs(diff) == 1) & ((frac < 0.002) | (frac > 0.998)))
        n_markers += len(mk)
        # Every series left some ink of its own in the instance map.
        assert (r.inst == k + 1).sum() > 0
    if kind == "lines":
        assert n_markers == 0
    else:
        assert n_markers > 0
        assert "nn_px_median" in m["probe"]


def test_drawn_centre_is_the_ink_centroid_of_isolated_symmetric_markers():
    for seed in range(14990100, 14990120):
        r = G.generate(seed, "shapes")
        m = r.meta
        if not m["probe"]["hollow"] and m["probe"]["ms_px"] >= 5 and any(s in ("o", "s", "D", "h", "8", "P", "X", "*") for s in m["probe"]["shapes"]):
            break
    else:
        pytest.skip("no filled symmetric shapes chart in the seed range")
    img = r.image.astype(np.float32)
    pa = m["plot_area"]
    paper = np.median(img[int(pa[1]) + 2:int(pa[3]) - 1, int(pa[0]) + 2:int(pa[2]) - 1].reshape(-1, 3), 0)
    checked = 0
    for si, s in enumerate(m["series"]):
        if s["marker"] not in ("o", "s", "D", "d", "h", "8", "x", "+", "P", "X", ".", "*") or m["probe"]["hollow"]:
            continue
        rr = int(s["markersize_px"]) + 4
        for (x, y) in s["markers_drawn_px"]:
            xi, yi = int(round(x)), int(round(y))
            if xi - rr < 0 or yi - rr < 0 or xi + rr + 1 > img.shape[1] or yi + rr + 1 > img.shape[0]:
                continue
            win = r.inst[yi - rr:yi + rr + 1, xi - rr:xi + rr + 1] == si + 1
            if win.sum() < 4 or win[0].any() or win[-1].any() or win[:, 0].any() or win[:, -1].any():
                continue
            w = np.linalg.norm(img[yi - rr:yi + rr + 1, xi - rr:xi + rr + 1] - paper, axis=-1) * win
            yy, xx = np.mgrid[0:2 * rr + 1, 0:2 * rr + 1]
            cx = (w * xx).sum() / w.sum() + xi - rr
            cy = (w * yy).sum() / w.sum() + yi - rr
            assert abs(cx - x) < 0.2 and abs(cy - y) < 0.2
            checked += 1
    assert checked >= 5


def test_value_labels_are_text_not_data():
    # Find a "values" chart: the printed numbers must be in the text class, never data or marker truth.
    for seed in range(14990200, 14990240):
        r = G.generate(seed, "labels")
        if r.meta["probe"]["mode"] == "values":
            break
    else:
        pytest.skip("no values chart in the seed range")
    assert (r.sem == TEXT).sum() > 50
    n_markers = sum(len(s["markers_px"]) for s in r.meta["series"])
    assert n_markers == sum(len(s["x"]) for s in r.meta["series"] if s["kind"] != "line")
    assert (r.sem == DATA).sum() > 0


def test_dense_spacing_is_controlled():
    r = G.generate(14990300, "dense")
    p = r.meta["probe"]
    assert 0.5 * p["spacing_rel"] <= p["nn_rel_median"] <= 1.5 * p["spacing_rel"] or p["spacing_rel"] >= 2.5
