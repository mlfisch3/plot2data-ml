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
