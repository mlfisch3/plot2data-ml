"""The t3 probe generator writes the standard dataset format with exact geometry."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.metrics import peak_vertices
from p2d.synth import probe_t3 as P
from p2d.synth.mpl_render import AXIS, DATA, TICK_LABEL


@pytest.mark.parametrize("family", sorted(P.FAMILIES))
def test_probe_family_renders_consistent_ground_truth(family):
    seed = P.FAMILY_BASE[family] + 3
    r = P.generate(family, seed)
    m = r.meta
    H, W = r.image.shape[:2]
    assert (m["width"], m["height"]) == (W, H)
    assert r.sem.shape == (H, W) and r.inst.shape == (H, W)
    assert m["seed"] == seed and m["probe"]["family"] == family
    assert set(m) >= {"plot_area", "xticks", "yticks", "series", "xscale", "yscale", "xlim", "ylim"}
    pa = m["plot_area"]
    assert 0 <= pa[0] < pa[2] < W and 0 <= pa[1] < pa[3] < H
    # Every tick anchor sits on the plot edge it belongs to, and its label is tick-label ink.
    for t in m["xticks"]:
        assert abs(t["anchor"][1] - (pa[3] if t["side"] == "low" else pa[1])) < 1e-6
        assert pa[0] - 1 <= t["pos"] <= pa[2] + 1
    for t in m["yticks"]:
        assert abs(t["anchor"][0] - (pa[0] if t["side"] == "low" else pa[2])) < 1e-6
    assert (r.sem == TICK_LABEL).sum() > 0
    # The drawn ink of the series lies on the recorded path: every inked pixel is within half a stroke
    # (plus antialiasing) of the polyline, and the polyline runs through ink.
    s = m["series"][0]
    path = np.array(s["path_px"])
    ys, xs = np.nonzero(r.inst == 1)
    assert len(xs) > 50
    sub = np.random.default_rng(0).choice(len(xs), min(300, len(xs)), replace=False)
    from p2d.data import densify

    dense = densify(path, 0.5)
    d = np.sqrt(((np.column_stack([xs[sub], ys[sub]])[:, None, :] - dense[None, :, :]) ** 2).sum(-1)).min(1)
    assert np.quantile(d, 0.95) <= 0.5 * s["linewidth_px"] + 1.5
    inside = (path[:, 0] > pa[0] + 2) & (path[:, 0] < pa[2] - 2) & (path[:, 1] > pa[1] + 2) & (path[:, 1] < pa[3] - 2)
    v = path[inside][:: max(1, inside.sum() // 50)]
    near = np.array([(r.sem[max(0, int(round(y)) - 1): int(round(y)) + 2, max(0, int(round(x)) - 1): int(round(x)) + 2] == DATA).any() for x, y in v])
    assert near.mean() > 0.9


def test_peak_families_have_scored_turning_points():
    for family in ("peaks", "spikes"):
        r = P.generate(family, P.FAMILY_BASE[family] + 5)
        pa = r.meta["plot_area"]
        pv = peak_vertices(np.array(r.meta["series"][0]["path_px"]), 0.05 * (pa[3] - pa[1]))
        assert len(pv) >= 3, family


def test_frame_family_records_spine_visibility_in_the_label_map():
    r = P.generate("frame", P.FAMILY_BASE["frame"] + 3)
    assert r.meta["probe"]["spines"] in ("all", "lb", "b", "none", "offset")
    if r.meta["probe"]["spines"] == "none":
        assert (r.sem == AXIS).sum() == 0


def test_seed_bases_are_distinct_and_above_the_team_base():
    bases = list(P.FAMILY_BASE.values())
    assert len(set(bases)) == len(bases)
    assert min(bases) >= P.SEED_BASE == 13_000_000
