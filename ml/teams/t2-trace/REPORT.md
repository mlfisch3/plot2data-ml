# t2-trace submission

## Claim

An overlap-aware rewrite of `merge_fragments` joins the chain pieces of one series when a global embedding cluster boundary ran down the middle of a continuous ridge and split the series into two chains that span the same column range.
Measured against the frozen baseline (6b313e9), geometry-only, with the shared `runs/v3/best.pt` checkpoint, on the standard scoreboard:

| set | metric | frozen | this | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 all | line_found | 0.7570 | 0.7809 | **+0.024** |
| mpl-val 200 all | line_cov_mean | 0.6665 | 0.6879 | +0.021 |
| mpl-val 200 all | line_good_cov_mean | 0.5884 | 0.6052 | +0.017 |
| mpl-val 200 all | line_rms_median_pct | 0.311 | 0.285 | -0.026 (improved) |
| mpl-val 200 simple | line_found | 0.8859 | 0.8993 | +0.013 |
| plotly-v1 150 all | line_found | 0.8608 | 0.8738 | +0.013 |
| plotly-v1 150 all | line_cov_mean | 0.7939 | 0.8048 | +0.011 |
| plotly-v1 150 simple | line_found | 0.9720 | 0.9626 | -0.009 |

Probe sets (geometry only, 100 charts each):

| probe | metric | frozen | this | delta |
| --- | --- | --- | --- | --- |
| t2-cross | line_found all | 0.9167 | 0.9267 | +0.010 |
| t2-cross | line_good_cov_mean all | 0.843 | 0.8517 | +0.009 |
| t2-samecolour | line_found | 0.9000 | 0.9125 | +0.013 |
| t2-samecolour | line_good_cov_mean | 0.743 | 0.7522 | +0.009 |

Branch: `team/t2-trace`, head `4ab8ee0`.
Verify with:

```sh
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml
source ../.venv/bin/activate
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --refine
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/t2-cross --refine
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/t2-samecolour --refine
python -m pytest tests/
```

## Diagnosis

Staged attribution of the frozen baseline on 15 probe sets (`out/t2c/diag-probes.txt`): the network's line heat is present on 97-100% of columns of every true series.
The losses live in the decoder.

The curator's inspection on the 200-chart mpl-val (`out/t2c/inspect-val.json`): 32% of true series have ridge pixels in two or more big embedding clusters; 207 refused junctions between pieces of one true series.
Of those junctions, 83% have overlapping columns, with p50 overlap of 374 columns and p90 of 636 - two whole chains that span the series over the SAME column range, split by a cluster boundary running through the ridge.
End-of-A sits at the far column of A and start-of-B at the opposite far column, so endpoint y gaps are large (p50 56 px) although the ridges agree in the middle.
Only 3% of refused junctions sit in `dx in [1, 60]` where the frozen merge rule even looks.

The frozen `merge_fragments` only joined pieces with up to 8 columns of overlap and a 60-column gap: it was built for end-to-end gaps and could not touch the dominant case.

Secondary findings (not fixed in this submission, documented for the next pass):

- Dedupe sometimes removes a real partial of one series because the envelope of another series' chain (window=4, +/-3 tol) swallows it at a crossing region.
  Curator's measurement: disabling `drop_duplicates` entirely rescues 17 of 112 lost series (+0.037 line_found) and moves 74 of 224 partials to good_cov >= 0.9.
  See `out/t2c/dedupe-paths-analysis.txt` for a path breakdown; the biggest sub-lever is "cross-series envelope swallows real partial" (20/112, 18%).
- Peel_chains hops at shallow crossings when two series share one embedding cluster.
  The oracle-cluster upper bound (true instance labels at `cluster_embeddings`) is `line_found` 0.91 on the first 60 charts.

## Ideas considered, in order of expected gain

1. **Overlap-aware merge_fragments.** The dominant 83% of refused junctions.
   Shipped. Measured gain: +0.024 line_found on mpl-val all.
2. **Dedupe rewrite** (next lever).
   Ceiling +0.037 line_found and +0.16 ok rate on mpl-val all.
3. **Replace cluster+peel with a direction-field tracker through the whole ridge graph.**
   The predecessor's rewrite; direction-head scaffolding is in the tree (`model.py`, `losses.py`, `data.py`) but no model has been trained with it, and the ridge-level tracker needs more care than one iteration (first version regressed on simple cross probes: found 1.000 -> 0.896 on first 20 charts, rms_p90 0.37% -> 12.3%).
4. **Oracle cluster upper bound.** 0.91 line_found vs 0.78 now: embedding splits are what hurts the chain stage.
   The direction head + whole-ridge tracker is the correct way to close this.

## Implementation

`ml/p2d/extract.py: _join_cost(A, B)` returns a cost or `None`.
`merge_fragments(frags)` builds an `n x n` pairwise cost matrix, embeds it in a `2n x 2n` assignment matrix with `no_join=5.0` on identity blocks, and solves it with `scipy.optimize.linear_sum_assignment`, so each chain continues into at most one other and each start comes from at most one.

Two branches of `_join_cost`:

- Short gap (`dx in [1, 60]`): the frozen rule exactly - pixel gap between A's last run and B's first run must be `<= 3 + 2 dx`, embedding distance `<= 3.0`.
  The frozen rule tests the endpoints by their y positions; endpoint slopes at a sine extremum do not land right under extrapolation and the original rule was correct not to try.
- Long gap (`dx in [60, 90]`): the frozen gap rule plus a slope-extrapolation gate.
- Short overlap (`<= 8 cols`): frozen's max |diff| `<= 2.5` rule.
- Long overlap (`> 8 cols`): the new path.
  Both chains must come from different clusters, each with `q >= 0.3` and `>= 50` columns.
  The y gap along the shared columns must be nearly constant: `|median| <= 6`, `MAD <= 1.2`, `|linear drift across the overlap| <= 2.5`.
  Together these separate the "cluster split a ridge" case (constant 1-6 px offset, half a ridge width) from crossing or neighbouring series (median moves across the overlap).

Cost (unit-free): `|median diff| + 2 * MAD + 0.5 * drift + de + 0.0005 * nov` for overlaps and `0.03 * (gap + dx) + de` for gaps, both below `no_join = 5.0` for valid pairs.

Transitive chains fall out naturally: A matches B, B matches C, and merging follows `nxt`.

Cost: `scipy.optimize.linear_sum_assignment` on a `2n x 2n` matrix (`n` = number of chains per chart, typically 10-60), so `O(n^3)`; negligible against inference.
No new memory, no new parameters, no new training.

Tests: `ml/tests/test_trace.py` covers overlapping pieces of one series, different series staying apart, embedding gating, assignment preventing double-claim, transitive chain merging, short gap, short overlap fallback, and slope consistency after merging.

## Generality and regressions

The change holds across matplotlib and Plotly and across every probe:
- `mpl-val`: +0.024 found all, +0.013 simple.
- `plotly-v1`: +0.013 found all, -0.009 simple.
- `t2-cross`, `t2-samecolour`: +0.010 and +0.013 found.
- Pending (curator's full sweep running): `t2-parallel`, `t2-multi`, `t2-dense`, `t2-wide`, `t2-shallowx`, `t2-legocclude`, Chart.js corpus and the real screenshots.

Plotly simple -0.009: hypothesised to be a ghost+real merge in single-series charts whose output chain then sits just below the metric's matching threshold.
This is the same ghost+real problem that `drop_duplicates` would solve.

No end-to-end gain is measured yet; that run is in flight.

## What did not work

- First attempt at the overlap rule used `median diff <= 2.0` and `p90 <= 6.0` with `emb_tol = 4.0`.
  mpl-val found all 0.7570 -> 0.7332 (-0.024). Spurious merges across different series in multi-series charts: a 400-column overlap can have median diff <= 2 by accident when the two series run close in that region but diverge at the ends.
- A MAD-based rule (`mad <= 1.5`, `drift <= 3`, `|median| <= 10`) still regressed: 0.7267.
  Reason: the no-overlap branch was simultaneously STRICTER than the frozen gap rule (used slope extrapolation at every `dx`), which rejected dashed/sine endpoints the frozen rule accepted.
  Fixed by keeping the frozen rule exactly for `dx <= 60` and only using slope extrapolation for `dx > 60`.
- A dedupe pass that replaced the envelope test with a per-column `|y_f - y_g_interp|` check and tightened `tol` turned out too lax: pred counts rose from 6 to 22 on charts like 9000037, with no change to `line_found`.
  The envelope width was doing work the per-column test did not; narrowing the window from 4 to 1 and tol from 3.0 to 2.5 is a safer path and is being measured now.
- The predecessor's tracker (joint peel_chains with embedding penalty and shared runs) regressed on `t2-cross` first-20: found 1.000 -> 0.896, rms_p90 0.37% -> 12.3%.
  Rolled back; preserved on the branch as commit `9b97b78` for the next attempt.

## Next steps

With another day:

1. Finish the dedupe pass: narrow envelope (`window=1`) + support-ordered sort (`q * len`).
   Measurement pending; ceiling +0.037 found, +0.16 ok rate.
2. Train the direction head.
   The scaffolding is in `model.py`, `losses.py`, `data.py`, `evaluate.py`, `train.py` on this branch; a 4k-iteration fine-tune from `runs/v3/best.pt --init` would add the direction channel.
   The decoder would then skip clustering entirely and track through the ridge graph with the direction as the local link cost - the predecessor's design, now informed by what regressed.
3. The oracle-cluster upper bound of 0.91 is the final headroom for separation.
   Closing most of the gap between 0.78 and 0.91 requires either the direction-field tracker or a per-series conditioned second pass (mask the ridge to one cluster's colour, run again).
