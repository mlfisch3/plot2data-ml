"""The t2-trace probe generator: exact ground truth in the standard format, one difficulty per case."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.data import densify
from p2d.synth import probe_t2 as P
from p2d.synth.mpl_render import DATA


@pytest.mark.parametrize("case", P.CASES)
def test_case_renders_with_truth_on_the_ink(case):
    r = P.generate(P.seed_for(case, 1))
    m = r.meta
    H, W = r.sem.shape
    assert r.image.shape == (H, W, 3) and r.inst.shape == (H, W)
    assert m["preset"] == "probe-" + case and P.case_of(m["seed"]) == case
    assert len(m["xticks"]) >= 2 and len(m["yticks"]) >= 2
    pa = m["plot_area"]
    assert 0 <= pa[0] < pa[2] <= W and 0 <= pa[1] < pa[3] <= H
    hits = total = 0
    for s in m["series"]:
        p = np.array(s["path_px"])
        assert len(p) >= 2 and s["kind"] in ("line", "step", "area", "line+markers")
        d = densify(p, 0.5)
        inside = (d[:, 0] >= pa[0]) & (d[:, 0] <= pa[2]) & (d[:, 1] >= pa[1]) & (d[:, 1] <= pa[3])
        d = d[inside]
        xi = np.round(d[:, 0]).astype(int).clip(0, W - 1)
        yi = np.round(d[:, 1]).astype(int).clip(0, H - 1)
        near = np.zeros(len(d), bool)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                near |= r.sem[(yi + dy).clip(0, H - 1), (xi + dx).clip(0, W - 1)] == DATA
        hits += near.sum()
        total += len(d)
    # Dashed and dotted series have gaps on purpose; everything else lies on data ink.
    assert hits / total >= (0.4 if case == "dotted" else 0.85 if case in ("samecolour", "multi") else 0.98)


def test_cases_provoke_what_they_say():
    cross = P.generate(P.seed_for("cross", 2)).meta
    assert 2 <= len(cross["series"]) <= 4 and all(s["linestyle"] == "-" for s in cross["series"])
    par = P.generate(P.seed_for("parallel", 2)).meta
    a, b = (np.array(s["path_px"]) for s in par["series"][:2])
    gap = np.abs(np.interp(a[:, 0], b[:, 0], b[:, 1]) - a[:, 1])
    assert np.median(gap) < 12  # a few pixels apart, by construction
    same = P.generate(P.seed_for("samecolour", 2)).meta
    assert same["series"][0]["color"] == same["series"][1]["color"]
    thin = P.generate(P.seed_for("thin", 2)).meta
    assert all(s["linewidth_px"] < 1.2 for s in thin["series"])
    small = P.generate(P.seed_for("small", 2)).meta
    assert small["width"] <= 480
    dense = P.generate(P.seed_for("dense", 2)).meta
    pw = dense["plot_area"][2] - dense["plot_area"][0]
    assert all(len(s["x"]) / pw > 1.0 for s in dense["series"])
    legend = P.generate(P.seed_for("legend", 2)).meta
    lb, pa = legend["legend_bbox"], legend["plot_area"]
    assert lb and lb[0] > pa[0] and lb[2] < pa[2] and lb[1] > pa[1] and lb[3] < pa[3]
