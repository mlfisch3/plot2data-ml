"""Tests of the line tracker: column runs, chains through crossings, fragment joins, direction targets."""

from __future__ import annotations

import numpy as np
import pytest

from p2d.data import DIR_SCALE, column_curve, direction_targets
from p2d.extract import column_runs, merge_fragments, peel_chains


def _heat_from_curves(curves, H=64, W=120, sigma=1.0):
    """Line heat (Gaussian of the distance to the nearest curve) and an embedding that names the curve."""
    yy = np.arange(H)[:, None]
    heat = np.zeros((H, W))
    emb = np.zeros((8, H, W))
    best = np.full((H, W), np.inf)
    for k, ys in enumerate(curves):
        d = np.abs(yy - ys[None, :])
        heat = np.maximum(heat, np.exp(-0.5 * (d / sigma) ** 2))
        take = d < best
        best = np.where(take, d, best)
        emb[k] = np.where(take, 1.0, emb[k])
        for j in range(len(curves)):
            if j != k:
                emb[j] = np.where(take, 0.0, emb[j])
    emb *= 6.0  # well apart, as the discriminative loss makes them
    return heat.astype(np.float32), emb.astype(np.float32)


def test_column_runs_centres_and_cuts_fused_runs():
    W = 40
    x = np.arange(W)
    a = np.full(W, 20.3)
    b = np.full(W, 24.3)  # 4 px below: the two ridges fuse into one run above the threshold
    heat, emb = _heat_from_curves([a, b], H=48, W=W)
    runs = column_runs(heat > 0.25, heat, emb)
    assert len(runs) == 2 * W  # cut by the embedding jump, one run per curve per column
    ys = np.sort(runs.y.reshape(W, 2), axis=1)
    assert np.allclose(ys[:, 0], 20.3, atol=0.15) and np.allclose(ys[:, 1], 24.3, atol=0.15)
    runs = column_runs(heat > 0.25, heat, None)
    assert len(runs) == W  # without an embedding the fused run stays whole


def test_chains_follow_their_series_through_a_crossing():
    W = 120
    x = np.arange(W, dtype=float)
    up = 10 + 0.4 * x  # rises from 10 to 58
    down = 58 - 0.4 * x  # falls from 58 to 10; they cross at x = 60
    heat, emb = _heat_from_curves([up, down])
    runs = column_runs(heat > 0.25, heat, emb)
    chains = peel_chains(runs)
    assert len(chains) == 2
    for ch in chains:
        ys = runs.y[ch]
        slope = np.diff(ys) / np.diff(runs.col[ch])
        assert np.all(np.abs(np.abs(slope) - 0.4) < 0.3), slope  # never flips direction: no hop at the crossing
    assert sum(len(ch) for ch in chains) >= 2 * W - 12


def test_chain_cannot_jump_a_large_vertical_gap():
    W = 60
    x = np.arange(W, dtype=float)
    left = np.where(x < 30, 10.0, np.nan)
    right = np.where(x >= 30, 40.0, np.nan)
    heat = np.zeros((64, W), np.float32)
    for ys in (left, right):
        for c in range(W):
            if np.isfinite(ys[c]):
                heat[:, c] = np.maximum(heat[:, c], np.exp(-0.5 * (np.arange(64) - ys[c]) ** 2))
    emb = np.zeros((8, 64, W), np.float32)
    runs = column_runs(heat > 0.25, heat, emb)
    chains = peel_chains(runs)
    assert len(chains) == 2 and all(len(ch) == 30 for ch in chains)


def _frag(c0, c1, y0, slope, e=None):
    cols = np.arange(c0, c1 + 1, dtype=float)
    e = np.zeros(8) if e is None else e
    return {"cols": cols, "ys": y0 + slope * (cols - c0), "embs": np.tile(e, (len(cols), 1)),
            "spans": [(0, 0)] * len(cols), "q": 1.0}


def test_merge_fragments_joins_across_a_crossing_by_geometry():
    out = merge_fragments([_frag(0, 100, 0, 1.0), _frag(103, 200, 97, -1.0), _frag(0, 100, 200, -1.0), _frag(103, 200, 103, 1.0)])
    assert len(out) == 2
    for o in out:
        s = np.diff(o["ys"]) / np.diff(o["cols"])
        assert np.allclose(s, s[0])


def test_merge_fragments_is_an_assignment():
    # Two ends compete for one continuation: the one it lines up with wins, the other stays apart.
    out = merge_fragments([_frag(0, 100, 0, 1.0), _frag(0, 100, 20, 1.0), _frag(104, 200, 104, 1.0)])
    assert sorted(len(o["cols"]) for o in out) == [101, 198]
    assert any(o["ys"][0] == 0 and len(o["cols"]) == 198 for o in out)


def test_merge_fragments_respects_the_embedding():
    e1, e2 = np.zeros(8), np.full(8, 3.0)  # 8.5 apart
    out = merge_fragments([_frag(0, 100, 0, 1.0, e1), _frag(104, 200, 104, 1.0, e2)])
    assert len(out) == 2


def test_direction_targets_point_at_the_next_column():
    H, W = 32, 40
    path = np.array([[5.0, 10.0], [35.0, 25.0]])  # slope 0.5
    c0, ys = column_curve(path)
    assert c0 == 5 and len(ys) == 31 and ys[0] == pytest.approx(10.0)
    region = np.zeros((H, W), np.uint8)
    for c in range(c0, c0 + len(ys)):
        region[int(round(ys[c - c0])), c] = 1
    d = direction_targets(region, {1: (c0, ys)}, H, W)
    y, x = int(round(ys[10])), c0 + 10
    assert d[2, y, x] == 1.0
    assert y + d[0, y, x] * DIR_SCALE == pytest.approx(ys[11])
    assert y + d[1, y, x] * DIR_SCALE == pytest.approx(ys[9])
    assert d[2, int(round(ys[0])), c0] == 1.0 and d[1, int(round(ys[0])), c0] == 0.0  # no previous column: zero target
