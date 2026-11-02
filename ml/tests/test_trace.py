"""Tests of merge_fragments: joining chain pieces that are one series.

The frozen baseline accepts only end-to-end joins with a <=8-column overlap;
these tests cover the new overlap-aware rule, which is where the biggest
mpl-val wins live (two whole chains that span the same column range because a
cluster boundary ran down the middle of a continuous ridge).
"""

from __future__ import annotations

import numpy as np
import pytest

from p2d.extract import _join_cost, merge_fragments


def _frag(c0: int, c1: int, y0: float, slope: float = 0.0, k: int = 0, emb: float = 0.0, q: float = 0.9) -> dict:
    cols = np.arange(c0, c1 + 1, dtype=float)
    ys = y0 + slope * (cols - c0)
    return {"cols": cols, "ys": ys, "emb": np.full(8, emb, dtype=float), "k": k, "q": q,
            "spans": [(int(y), int(y) + 1) for y in ys]}


def test_overlapping_pieces_of_one_series_merge():
    # Two chains covering 0-500 and 100-700 of the same line y = 10 + 0.1 col: one series.
    f0 = _frag(0, 500, 10.0, 0.1, k=0, emb=0.0)
    f1 = _frag(100, 700, 20.0, 0.1, k=1, emb=0.3)  # y at col 100 is 10 + 0.1*100 = 20
    cost = _join_cost(f0, f1)
    assert cost is not None and cost < 5.0
    merged = merge_fragments([f0, f1])
    assert len(merged) == 1
    assert merged[0]["cols"][0] == 0 and merged[0]["cols"][-1] == 700
    assert merged[0]["ks"] == [0, 1]


def test_overlapping_pieces_of_different_series_stay_apart():
    # Same column range, y 50 px apart: cannot be one series.
    f0 = _frag(0, 500, 10.0, 0.0, k=0, emb=0.0)
    f1 = _frag(100, 700, 60.0, 0.0, k=1, emb=0.3)
    assert _join_cost(f0, f1) is None
    assert len(merge_fragments([f0, f1])) == 2


def test_merge_respects_the_embedding():
    # Y agrees but the embedding mean distance is 8.5, far above the 4.0 tolerance.
    e1, e2 = 0.0, 3.0  # norm = sqrt(8) * 3 ~ 8.5
    f0 = _frag(0, 500, 10.0, 0.1, k=0, emb=e1)
    f1 = _frag(100, 700, 20.0, 0.1, k=1, emb=e2)  # matched slope and intercept
    assert _join_cost(f0, f1) is None
    assert len(merge_fragments([f0, f1])) == 2


def test_assignment_prevents_double_claim():
    # Two As want the same B; the one lining up in y wins, the other stays apart.
    fA1 = _frag(0, 100, 10.0, 0.0, k=0, emb=0.0)
    fA2 = _frag(0, 100, 20.0, 0.0, k=1, emb=0.0)
    fB = _frag(104, 300, 10.0, 0.0, k=2, emb=0.0)
    merged = merge_fragments([fA1, fA2, fB])
    assert len(merged) == 2
    # The y=10 chain spans 0..300; the y=20 chain stays at its original length.
    spans = sorted((int(m["cols"][0]), int(m["cols"][-1]), int(m["ys"][0])) for m in merged)
    assert spans == [(0, 100, 20), (0, 300, 10)]


def test_transitive_chain_merge():
    # Three overlapping pieces of the same line y = 10 + 0.1 col end up as one chain.
    f0 = _frag(0, 300, 10.0, 0.1, k=0, emb=0.0)
    f1 = _frag(100, 500, 20.0, 0.1, k=1, emb=0.2)
    f2 = _frag(300, 700, 40.0, 0.1, k=2, emb=0.4)
    merged = merge_fragments([f0, f1, f2])
    assert len(merged) == 1 and merged[0]["cols"][-1] == 700 and merged[0]["cols"][0] == 0


def test_end_to_end_join_small_gap_still_works():
    # Classical case the frozen rule already handled: a 10-column gap, agreeing slopes.
    # Same line y = 10 + 0.1 col: f0 ends at (100, 20), f1 starts at (110, 21).
    f0 = _frag(0, 100, 10.0, 0.1, k=0, emb=0.0)
    f1 = _frag(110, 200, 21.0, 0.1, k=1, emb=0.3)
    assert _join_cost(f0, f1) is not None
    assert len(merge_fragments([f0, f1])) == 1


def test_short_overlap_falls_back_to_endpoint_check():
    # 5-column overlap: too short to use median; endpoint check must pass.
    f0 = _frag(0, 100, 10.0, 0.0, k=0, emb=0.0)
    f1 = _frag(96, 200, 10.5, 0.0, k=1, emb=0.3)
    assert _join_cost(f0, f1) is not None
    f2 = _frag(96, 200, 20.0, 0.0, k=1, emb=0.3)  # 10 px off at endpoint: too far
    assert _join_cost(f0, f2) is None


def test_merge_leaves_slope_consistent():
    # Two overlapping pieces of a 0.4 slope line: merged y runs smoothly from 0 to 280.
    f0 = _frag(0, 500, 0.0, 0.4, k=0, emb=0.0)
    f1 = _frag(200, 700, 80.0, 0.4, k=1, emb=0.0)  # y at col 200 = 0 + 0.4 * 200 = 80
    merged = merge_fragments([f0, f1])
    assert len(merged) == 1
    o = merged[0]
    s = np.diff(o["ys"]) / np.diff(o["cols"])
    assert np.all(np.abs(s - 0.4) < 0.05)


# ---------------------------------------------------------------------------
# drop_duplicates: parallel-curve test for noisy twin traces
# ---------------------------------------------------------------------------


def _wiggly(c0: int, c1: int, offset: float = 0.0, seed: int = 0) -> dict:
    """A noisy sinusoid chain over [c0, c1], shifted by `offset` in y."""
    rng = np.random.default_rng(seed)
    cols = np.arange(c0, c1 + 1, dtype=float)
    base = 100.0 + 60.0 * np.sin(cols * 0.03) + offset
    ys = base + rng.normal(0.0, 3.0, size=len(cols))
    return {"cols": cols, "ys": ys, "emb": np.zeros(8, dtype=float), "ks": [0], "q": 0.75,
            "spans": [(int(y), int(y) + 1) for y in ys]}


def test_drop_duplicates_catches_parallel_twin_noisy_trace():
    from p2d.extract import drop_duplicates
    # A primary chain and a near-copy a few pixels off, both tracing the same curve.
    primary = _wiggly(0, 800, offset=0.0, seed=1)
    twin = _wiggly(50, 780, offset=4.0, seed=2)
    kept = drop_duplicates([primary, twin])
    assert len(kept) == 1
    # The longer survives.
    assert len(kept[0]["cols"]) == len(primary["cols"])


def test_drop_duplicates_keeps_two_truly_separate_series():
    from p2d.extract import drop_duplicates
    # Same column range but y curves are well apart - two real series.
    rng = np.random.default_rng(3)
    cols = np.arange(0, 800, dtype=float)
    y1 = 100.0 + 20.0 * np.sin(cols * 0.03) + rng.normal(0.0, 2.0, size=len(cols))
    y2 = 300.0 + 20.0 * np.sin(cols * 0.03 + 1.3) + rng.normal(0.0, 2.0, size=len(cols))
    def make(ys, k):
        return {"cols": cols.copy(), "ys": ys, "emb": np.zeros(8), "ks": [k], "q": 0.75,
                "spans": [(int(y), int(y) + 1) for y in ys]}
    kept = drop_duplicates([make(y1, 0), make(y2, 1)])
    # Both must survive: they trace different curves 200 px apart.
    assert len(kept) == 2


def test_drop_duplicates_keeps_disjoint_segments():
    from p2d.extract import drop_duplicates
    # Two chains that cover disjoint x-ranges stay apart even if their shapes are similar.
    rng = np.random.default_rng(4)
    def seg(c0, c1):
        cols = np.arange(c0, c1 + 1, dtype=float)
        ys = 100.0 + 30.0 * np.sin(cols * 0.03) + rng.normal(0.0, 2.0, size=len(cols))
        return {"cols": cols, "ys": ys, "emb": np.zeros(8), "ks": [0], "q": 0.75,
                "spans": [(int(y), int(y) + 1) for y in ys]}
    kept = drop_duplicates([seg(0, 300), seg(500, 800)])
    assert len(kept) == 2


def test_parallel_curve_rejects_short_overlap():
    from p2d.extract import _parallel_curve
    # 10 shared points is too few to trust a correlation.
    a = {"cols": np.arange(0, 100, dtype=float), "ys": np.sin(np.arange(100) * 0.1)}
    b = {"cols": np.arange(90, 110, dtype=float), "ys": np.sin(np.arange(90, 110) * 0.1)}
    inside = (b["cols"] >= a["cols"][0]) & (b["cols"] <= a["cols"][-1])
    assert _parallel_curve(b, a, inside, min_corr=0.9, diff_frac=0.1) is False


def test_parallel_curve_detects_same_curve_at_offset():
    from p2d.extract import _parallel_curve
    rng = np.random.default_rng(5)
    cols = np.arange(0, 400, dtype=float)
    ya = 100.0 + 20.0 * np.sin(cols * 0.05) + rng.normal(0.0, 1.5, size=len(cols))
    yb = 100.0 + 20.0 * np.sin(cols * 0.05) + 5.0 + rng.normal(0.0, 1.5, size=len(cols))
    a = {"cols": cols, "ys": ya}
    b = {"cols": cols.copy(), "ys": yb}
    inside = np.ones(len(cols), dtype=bool)
    assert _parallel_curve(b, a, inside, min_corr=0.9, diff_frac=0.3) is True


def test_parallel_curve_rejects_different_curves():
    from p2d.extract import _parallel_curve
    rng = np.random.default_rng(6)
    cols = np.arange(0, 400, dtype=float)
    ya = 100.0 + 20.0 * np.sin(cols * 0.05) + rng.normal(0.0, 1.5, size=len(cols))
    # Different-phase sinusoid: not a parallel copy.
    yb = 100.0 + 20.0 * np.sin(cols * 0.05 + 2.0) + rng.normal(0.0, 1.5, size=len(cols))
    a = {"cols": cols, "ys": ya}
    b = {"cols": cols.copy(), "ys": yb}
    inside = np.ones(len(cols), dtype=bool)
    assert _parallel_curve(b, a, inside, min_corr=0.9, diff_frac=0.1) is False


def test_parallel_curve_rejects_same_shape_far_apart():
    # Two sinusoids of the same shape 100 px apart in y: correlated r=1 but far.
    from p2d.extract import _parallel_curve
    rng = np.random.default_rng(7)
    cols = np.arange(0, 400, dtype=float)
    ya = 100.0 + 20.0 * np.sin(cols * 0.05) + rng.normal(0.0, 1.0, size=len(cols))
    yb = 300.0 + 20.0 * np.sin(cols * 0.05) + rng.normal(0.0, 1.0, size=len(cols))
    a = {"cols": cols, "ys": ya}
    b = {"cols": cols.copy(), "ys": yb}
    inside = np.ones(len(cols), dtype=bool)
    # a's y-range is ~40 px. 200 px separation vs that is a huge diff_frac,
    # so even with correlation 1 the gate must stay closed.
    assert _parallel_curve(b, a, inside, min_corr=0.9, diff_frac=0.05) is False
