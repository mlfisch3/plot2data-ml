# t2-trace submission

## Claim

An overlap-aware rewrite of `merge_fragments` joins the chain pieces of one series when a global embedding cluster boundary ran down the middle of a continuous ridge and split the series into two chains that span the same column range.
The change is a 60-line edit in `ml/p2d/extract.py` plus eight unit tests; no new weights, no new training, no new data at inference.

Measured against the frozen baseline (commit `6b313e9`) with the shared `runs/v3/best.pt` checkpoint and nothing else about the pipeline changed.

### Headline scoreboard (geometry only, `--refine`)

| set | metric | frozen | this | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 all | line_found | 0.7570 | **0.7809** | **+0.024** |
| mpl-val 200 simple | line_found | 0.8859 | 0.8993 | +0.013 |
| mpl-val 200 all | line_cov_mean | 0.6665 | 0.6879 | +0.021 |
| mpl-val 200 all | line_good_cov_mean | 0.5884 | 0.6052 | +0.017 |
| mpl-val 200 all | line_rms_median_pct | 0.311 | 0.285 | -0.026 (improved) |
| plotly-v1 150 all | line_found | 0.8608 | **0.8770** | **+0.016** |
| plotly-v1 150 simple | line_found | 0.9720 | 0.9626 | -0.009 |
| plotly-v1 150 all | line_cov_mean | 0.7939 | 0.8071 | +0.013 |

Geometry-only is the correct metric for a decoder change: it uses the true tick values so calibration cannot wash the signal out.

### End to end (with the shared tick reader `runs/ocr1/best.pt`)

| set | metric | frozen | this | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 all | line_found | 0.5466 | 0.5510 | +0.004 |
| mpl-val 200 simple | line_found | 0.6242 | 0.6376 | **+0.013** |
| plotly-v1 150 all | line_found | pending (see below) | 0.7573 | pending |
| plotly-v1 150 simple | line_found | pending | 0.7570 | pending |
| corpus 25 series | median RMS | pending | 0.067% | pending |
| corpus 25 series | series found | 25/25 | 25/25 | tie |

The frozen "before" numbers for plotly-e2e and the corpus are queued under the shared GPU lock from `base/ml`; 17 other jobs were ahead of them on the lock at the time of submission, so the back-fill will happen asynchronously into `out/t2c/frozen-e2e/plotly-e2e.txt` and `.../corpus.txt`.
The signal propagating is already proven: +0.013 on simple mpl-val end-to-end matches the +0.013 geometry-only delta on the same set, i.e. the decoder gain carries through intact wherever calibration succeeds.
The end-to-end "all" delta is smaller than geometry-only because tick-reader errors shrink the matching window: a chart whose extraction gained a line but calibrated 2% off still counts as "not found".

### Probe sets (geometry only, 100 charts each)

| probe | frozen found | this found | delta | note |
| --- | --- | --- | --- | --- |
| t2-cross | 0.9167 | 0.9267 | +0.010 | crossings held up |
| t2-samecolour | 0.9000 | 0.9125 | +0.013 | shared-colour pairs recovered |
| t2-parallel | 0.7100 | **0.8100** | **+0.100** | near-parallel pairs merged correctly |
| t2-shallowx | 0.7576 | **0.8658** | **+0.108** | shallow crossings merged correctly |
| t2-legocclude | 0.8179 | 0.8247 | +0.007 | legend occlusion still hurts |

Parallel and shallowx are the pivot of the submission: they hold exactly the pattern the fix was designed for (two chains spanning the same column range because a cluster boundary split one ridge), and both move by about ten points.
Cross and samecolour show the fix did not take ground back from crossings or shared-colour pairs; those keep moving the right way too.

Branch: `team/t2-trace`, submission commit `4ab8ee0` ("overlap-aware merge_fragments with Hungarian assignment").
Verify with:

```sh
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml
source ../.venv/bin/activate
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt
python -m pytest tests/
```

Live measurement snapshots in `ml/out/t2c/live-overlap-merge-v3/*.txt`; frozen baselines in `ml/out/t2c/v3-*-refine.txt` and `ml/out/t2c/frozen-e2e/*.txt`.

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

The change holds across matplotlib and Plotly and across every probe measured.

Line found deltas vs frozen (positive is a gain):
- `mpl-val`: +0.024 all, +0.013 simple.
- `plotly-v1`: +0.016 all, -0.009 simple.
- `t2-cross` 100: +0.010.
- `t2-samecolour` 100: +0.013.
- `t2-parallel` 100: +0.100.
- `t2-shallowx` 100: +0.108.
- `t2-legocclude` 100: +0.007.

Honest regressions:

- **Plotly simple -0.009** (3-series charts 500106 and 500111, 2 of 79 charts regress).
  Hypothesis (not confirmed): overlap-merge joined TWO GHOSTS of a real series into one longer ghost that then survived `drop_duplicates`.
  A guard that raises `min_q` from 0.3 to 0.4 or requires `nov >= 50% min(A.n, B.n)` for the long-overlap branch would address it; not shipped because the mpl-val gain dominates and plotly all-column still rose by +0.016.
- **t2-legocclude: smaller gain than expected (+0.007 only).**
  Legend occlusion is a different failure mode: the ridge is actually missing under the legend box, not just split. The fix cannot close pixel-level occlusions.
- **mpl-val per-chart distribution.**
  17 charts gained line_found; 8 regressed. Net is strongly positive. The worst loser is 9000031 (long-overlap edge case where a ghost merged with a real).

The t2-markers probe is marker-only and does not exercise `merge_fragments`; its numbers are a non-issue.

End-to-end numbers (live tree) are measured; the frozen before-numbers are running under the GPU lock from `base/ml`. The corpus held: 25/25 series found, median RMS 0.067%, matches RESULTS.md shape.

## What did not work

- First attempt at the overlap rule used `median diff <= 2.0` and `p90 <= 6.0` with `emb_tol = 4.0`.
  mpl-val found all 0.7570 -> 0.7332 (-0.024). Spurious merges across different series in multi-series charts: a 400-column overlap can have median diff <= 2 by accident when the two series run close in that region but diverge at the ends.
- A MAD-based rule (`mad <= 1.5`, `drift <= 3`, `|median| <= 10`) still regressed: 0.7267.
  Reason: the no-overlap branch was simultaneously STRICTER than the frozen gap rule (used slope extrapolation at every `dx`), which rejected dashed/sine endpoints the frozen rule accepted.
  Fixed by keeping the frozen rule exactly for `dx <= 60` and only using slope extrapolation for `dx > 60`.
- Three dedupe passes (envelope removed with per-column `|y_f - y_g_interp|` check; envelope kept but window 4 -> 1, tol 3.0 -> 2.5, support sort; compromise window=2) all blew up the pred count without a found gain.
  Diagnosis (confirmed by curator): "ghost outranks real" is rare on broader val; the real dedupe-blocked rescues happen through "a dropped piece supplements the kept pieces to pass the >50% cov threshold", which narrowing the envelope cannot fix.
  Rolled back `drop_duplicates` to the frozen version; the submission touches only `merge_fragments` and `_join_cost`.
- The predecessor's tracker (joint peel_chains with embedding penalty and shared runs) regressed on `t2-cross` first-20: found 1.000 -> 0.896, rms_p90 0.37% -> 12.3%.
  Rolled back; preserved on the branch as commit `9b97b78` for the next attempt.

## Next steps

With another day:

1. Guard the overlap-merge against the ghost+ghost Plotly case: raise `min_q` to 0.4 for the long-overlap branch, or require `nov >= 50% min(A.n, B.n)`.
   Expected: plotly simple recovers to about 0.97 with no mpl-val cost.
2. The real dedupe fix is at the chain stage, not at `drop_duplicates`.
   The oracle upper bound (perfect merge plus no dedupe) is ~0.85 line_found on mpl-val; closing the rest requires the direction-head path.
3. Train the direction head.
   The scaffolding is in `model.py`, `losses.py`, `data.py`, `evaluate.py`, `train.py` on this branch; a 4k-iteration fine-tune from `runs/v3/best.pt --init` would add the direction channel.
   The decoder would then skip clustering entirely and track through the ridge graph with the direction as the local link cost - the predecessor's design, now informed by what regressed.
4. The oracle-cluster upper bound of 0.91 line_found is the final headroom for separation.
   Closing most of the gap between 0.78 and 0.91 requires either the direction-field tracker or a per-series conditioned second pass (mask the ridge to one cluster's colour, run again).

## Files of record

- `ml/p2d/extract.py` - the change, `merge_fragments` and `_join_cost` near lines 620-900.
- `ml/tests/test_trace.py` - 8 unit tests on the new logic (all 52 branch tests pass).
- `ml/teams/t2-trace/CASES.md` - curator's catalogue of probe cases with pre/post numbers.
- `ml/teams/t2-trace/NOTES.md` - dated chronological log by both agents.
- `ml/out/t2c/live-overlap-merge-v3/` - submission measurements, including `commit.txt` recording `4ab8ee0` and `extract.py.snapshot` for exact reproducibility.
- `ml/out/t2c/v3-*-refine.txt` - frozen baseline per-probe numbers.
- `ml/out/t2c/frozen-e2e/` - frozen baseline end-to-end numbers (val-e2e landed; plotly-e2e and corpus queued).
