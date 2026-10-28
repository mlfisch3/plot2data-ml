"""The t1-axis probe generator: every style renders, and its ground truth is consistent with the render."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.synth import probe_t1
from p2d.synth.mpl_render import TICK_LABEL


@pytest.mark.parametrize("style", probe_t1.STYLES)
def test_style_renders_with_consistent_truth(style):
    seed = 11_900_000 + probe_t1.STYLES.index(style)
    r = probe_t1.generate(seed, style)
    H, W = r.image.shape[:2]
    m = r.meta
    assert m["probe"] == style and m["width"] == W and m["height"] == H
    assert r.sem.shape == (H, W) and r.inst.shape == (H, W)
    pa = m["plot_area"]
    assert 0 <= pa[0] < pa[2] <= W and 0 <= pa[1] < pa[3] <= H
    axis = m["probe_axis"]
    ticks = m[axis + "ticks"]
    assert len(ticks) >= 2
    if style in ("two_lin", "two_log"):
        assert len(ticks) == 2
    if style == "crowded_y":
        assert len(ticks) >= 9
    if style in ("mult_sci", "offset"):
        assert m["offset_text"][1] != ""
    if style == "pow10_edge":
        assert m.get("cropped_left_px", 0) > 0
        assert all(t["text"].startswith("10^") for t in ticks)
    for key in ("xticks", "yticks"):
        for t in m[key]:
            lo, hi = (pa[0], pa[2]) if key == "xticks" else (pa[1], pa[3])
            assert lo - 1 <= t["pos"] <= hi + 1
            b = t["bbox"]
            # The label's ink is where the bbox says: tick-label pixels of the sem map inside it (unless it is
            # cut by the image edge, as pow10_edge does on purpose).
            x0, y0 = max(0, int(np.floor(b[0]))), max(0, int(np.floor(b[1])))
            x1, y1 = min(W, int(np.ceil(b[2])) + 1), min(H, int(np.ceil(b[3])) + 1)
            if x1 > x0 and y1 > y0:
                assert (r.sem[y0:y1, x0:x1] == TICK_LABEL).any(), (style, key, t["text"])
    for s in m["series"]:
        p = np.array(s["path_px"])
        assert len(p) >= 2 and np.all(np.isfinite(p))


def test_style_by_seed_cycles_evenly():
    styles = [probe_t1.style_of(s) for s in range(11_000_000, 11_000_000 + 2 * len(probe_t1.STYLES))]
    assert sorted(set(styles)) == sorted(probe_t1.STYLES)
    assert styles[: len(probe_t1.STYLES)] == styles[len(probe_t1.STYLES):]
