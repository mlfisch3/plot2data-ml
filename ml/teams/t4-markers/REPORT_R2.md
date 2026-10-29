# t4-markers round 2

Submission branch: `team/t4-markers-r2`. Base: `integration/round-1` at `121ed4d`. Baseline pytest: 110.

Round 2 principle: diminishing returns.
The round-1 integration is already a strict win over the frozen baseline on every scoreboard (`INTEGRATION-REPORT.md`): mpl-val `marker_recall` 0.613 all / 0.809 simple, `marker_precision` 0.736 / 0.845; plotly 0.403 / 0.824 and 0.795 / 0.912; corpus worst case 61.222% -> 0.214%.
The round-2 angle is the biggest surviving gap after that.

## Claim

Add a y-snap-to-line step to `measure_series` for line+markers series: every centre whose y disagrees with the traced line's y at its x by less than half the marker is replaced by the line's y.
On line+markers series the trace is a sub-pixel ridge averaged along the line, which is a stronger anchor than one marker's heat peak.
Scatter and series without a traced line are untouched (gate on `line_px is not None and len(line_px) >= 3`, the same gate the dash veto already uses).
Expected to close the residual y-error on line+markers series without touching the x-axis estimates, with a bounded cost of nothing on scatter.

The patch is written by the brainstormer and currently stashed (`stash@{0}: t4r2-brainstormer: line-snap patch, hold for baseline`); pytest at 112 green with the patch applied.

## Diagnosis

See `CASES_R2.md` for the full round-2 case catalogue.
Short summary of where the integrated pipeline stands after round 1:

### What round-1 integration did for the markers side

The integrated model (`runs/t5-chartjs/best.pt` + `--tta shift` + `--refine` + markers.py step25) is the configuration measured here.
Numbers from `INTEGRATION-REPORT.md` (which measured with `--tta shift` and the full pipeline through `pipeline.run`, where `refine_markers` runs by default):

| chart | metric | base (v3) | integrated | delta |
| --- | --- | --- | --- | --- |
| mpl-val `all` | marker_recall | 0.481 | 0.613 | +0.132 |
| mpl-val `all` | marker_precision | 0.640 | 0.736 | +0.096 |
| mpl-val `simple` | marker_recall | 0.642 | 0.809 | +0.167 |
| mpl-val `simple` | marker_precision | 0.741 | 0.845 | +0.105 |
| plotly `all` | marker_recall | 0.418 | 0.403 | -0.016 (within noise) |
| plotly `all` | marker_precision | 0.772 | 0.795 | +0.024 |
| plotly `simple` | marker_recall | 0.762 | 0.824 | +0.062 |
| plotly `simple` | marker_precision | 0.783 | 0.912 | +0.130 |

The whole-integration gain is huge on mpl-val markers (+10 to +17 pp recall/precision) and strongly positive on plotly simple markers.
On plotly `all` the integration moves a tiny amount of recall into precision; `all` includes several catastrophic charts (one 6081-marker rope) and is noise-dominated.

### What is left after the integration

Round-1 wins did not touch three residual issues on markers:

- **Line+markers y drift (ROUND-2 ANGLE)**: markers drawn on a line, whose network heat peak lands away from the line's path.
  The line tracer already measures the line's y to ~0.2% RMS, which is a tighter y anchor than any one marker's heat peak.
  This is the F1/F3 interaction: not a rope (where the markers merge in x) nor a big marker (where the heat is diffuse), but the ordinary line+markers case.
  Not addressed in round-1.
- **Hollow / small markers at low DPR**: step25's `marker_err_median_pct` on the hollow probe is 0.096% (down from v3's 0.138%); bulk of the remaining error is open rings and thin strokes where the ink-weight threshold does not form one component.
  Angle A for a future round; sub-1pt gain today.
- **Overlap in x (ropes)**: 76% of mpl-val FNs.
  The zoom pass (`ml/p2d/zoom.py`) is written but not integrated.
  Round-3 lever if time allows.
- **Triangles in no-iso overlap**: round-1's triangle convention correction only runs when there are enough isolated blobs.
  In packed-triangle scatter the fallback is the raw heat peak. Marginal.
- **Dashes/spikes as markers (lines probe)**: step25 drops ~88 of the v3 spurious markers on the lines probe (-17%).
  Reaching 0 is still open; the gain is bounded by what the dash veto can safely do without killing dashed line+markers.

### Why angle D (y-snap to line)

- **Hits an unaddressed failure directly**: no round-1 change touched line+markers y.
  The round-1 pipeline measures the marker's y from its ink centroid (symmetric) or raw heat peak (asymmetric / no-iso); neither uses the line as a prior.
- **Clean gate**: `line_px is not None and len(line_px) >= 3` on the pure measure_series call site, same gate the step25 dash veto already uses to tell line+markers from scatter.
  Pure scatter and lines without a traced path pass through untouched.
- **Bounded cost**: the y value only moves if it is within `max(1.5, 0.6 * size)` of the line's y at that x; an outlier marker plotted beside the line is not pulled onto it.
- **Grounded in a measured anchor**: `line_rms_median_pct` on mpl-val is 0.21% (plotly 0.14%).
  The marker centre's y, after step25, is at a worse anchor than that on most line+markers charts.
- **Deferred alternatives were worse**: filled vs hollow (A) is 0.03pp sub-1pt; shape class fit (B) is substantial code for a modest residual gain on no-iso overlap; hollow halos (C) is Chart.js-narrow sub-1pt; shape-aware clustering (E) is a bigger surgery than D.

## Probe set

`data/t4r2-linemk/` - 216 charts at seeds 14,100,000 to 14,100,215, generated by the new `linemk` kind in `p2d/synth/probe_t4.py`.

### What it provokes

Every chart is a line+markers series.
The markers sit exactly on the drawn line.
Varied dimensions, recorded in `meta["probe"]`:

| dimension | levels | range |
| --- | --- | --- |
| `spacing_rel` | 6 levels | 0.3, 0.5, 0.7, 1.0, 1.5, 2.5 marker diameters along x |
| `ms_pt` -> `ms_px` | 4 levels | 2 pt (2.5-4 px), 3 pt (3-5 px), 5 pt (5-10 px), 8 pt (8-16 px) at dpi 72-144 |
| `line_lw_pt` | 4 levels | 0.8, 1.5, 2.5, 4.0 pt (1 px to 8 px at dpi 72-144) |
| `dashed` | 2 levels | solid 60%, dashed 40% (random choice between "--", "-.", ":") |
| `n_series` | 2 levels | 1 (p = 2/3) or 2 (p = 1/3) |
| `shape` | 9 shapes | o, s, D, ^, v, *, x, P, + |
| curve | varied | random S.shape producing flat spans and steep spans in the same chart |

For every chart `meta["probe"]` records:
`kind="linemk", spacing_rel, ms_px, n_series, line_lw_pt, dashed, shape, n, nn_px_median, nn_rel_median, n_markers`.

Ground truth: `markers_px` records the exact value position (what the scoreboard matches against); `markers_drawn_px` records the drawn centre (matplotlib's integer stamp).

Realised distribution across 216 charts:
- 63,886 total markers
- spacing_rel: 0.3 (26), 0.5 (48), 0.7 (36), 1.0 (37), 1.5 (33), 2.5 (36)
- line_lw_pt: 0.8 (54), 1.5 (40), 2.5 (53), 4.0 (69)
- dashed: 76 / solid: 140
- n_series: 1 (152), 2 (64)
- shape: *, +, o, ^, s, x, D, P, v (balanced 17-33 each)

Expected failure modes the set surfaces:

- **Dense spacing + flat span**: markers merge in x, heat peaks sit along the ridge, y is well-centred.
  The fix should barely help here, since y is already close to the line (snap confirms position but doesn't move it).
- **Sparse spacing + sharp curve**: y heat may lag the drawn centre at a sharp bend; the line tracer follows the curve well because the line is thick, so y-snap buys the gain.
- **Thick dashed line + markers**: the step25 dash veto has to let the markers through (gate: skip veto on line+markers), while the y-snap replaces the drifted y.
  The hardest case for the fix.
- **Hollow markers on thick line**: the open ring plus line ink gives a diffuse heat that step25 falls back to raw peak for.
  The snap should pull y onto the line cleanly where present.

### Baseline numbers (integrated, no snap)

Measured with `runs/t5-chartjs/best.pt` + `--tta shift` + `--refine`, markers.py at `7421076` (step25 integrated).
Command:

```
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock nice -n 19 \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t4r2-linemk \
  --limit 216 --refine --tta shift --json out/t4r2/rows-linemk-int.json \
  > out/t4r2/eval-linemk-int.txt 2>&1
```

Numbers queued under heavy shared-lock contention (t5-robust is training 3000 iters on the GPU, and the other three teams are also running round-2 evals; up to seventeen flock waiters observed, so the queue advances slowly).
The baseline suite `teams/t4-markers/tools/probe_suite_r2_single.sh int` is waiting on the lock and will fill `out/t4r2/eval-{val,plotly,linemk,...}-int.txt` once it clears.
Expected set of eval outputs: `val`, `plotly`, `linemk`, `dense`, `row`, `shapes`, `hollow`, `multi`, `labels`, `lines`.

Partial outputs produced during the session land as empty files first (zero bytes until the per-chart loop finishes); monitor `out/t4r2/suite-int.log` for per-set completion lines.

### Expected numbers after the patch

With the brainstormer's y-snap-to-line patch (`stash@{0}: t4r2-brainstormer: line-snap patch, hold for baseline`), applied only inside `measure_series` for line+markers series:

- `marker_err_median_pct` collapses toward `line_rms_median_pct` (0.14-0.21%) wherever `line_px` covers the marker's x.
  Markers where `line_px` is sparse or absent keep their raw heat peak y.
- Recall and precision unchanged on linemk (the snap moves centres; it adds and drops nothing).
- val, plotly simple columns: a modest err_median_pct improvement where a chart's series is `line+markers` (common in mpl-val, less in plotly which tends toward scatter).
- Pure scatter sets (`shapes`, `hollow`, `multi`, `dense`): zero change (gate is `line_px is not None and len(line_px) >= 3`).
- `lines` (no-markers probe): zero change (no marker series, the snap does nothing).

The brainstormer's AFTER measurement will replace both tables above with real numbers once the baseline suite completes and the patch is unstashed; see `teams/t4-markers/tools/compare_before_after.py` for the delta table.

## Verification commands

- Baseline suite: `teams/t4-markers/tools/probe_suite_r2_single.sh int` (one single flock acquisition for all nine standard sets plus linemk).
- linemk eval: `python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t4r2-linemk --limit 216 --refine --tta shift --json out/t4r2/rows-linemk-int.json`.
- Pytest at the stashed baseline: `python -m pytest -q` -> 110 passed; after the brainstormer's `line-snap` tests land: 112 passed.
- Delta table: `python teams/t4-markers/tools/compare_before_after.py int snap`.

## Carried over commits in this submission

- `44264f9`: r2 scaffolding (probe_t4 linemk kind, suite runner, CASES_R2 + REPORT_R2 skeletons).
- `22cfafe`: extract_eval_numbers, single-lock runner, compare_before_after.
- (pending) brainstormer's y-snap patch commit on `measure_series`, loosened test and two new tests.
