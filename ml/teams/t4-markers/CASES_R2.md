# t4-markers round 2: the failure catalogue, extended

Curator's file.
Round-1 CASES.md remains the definitive catalogue of F1-F11.
This file (CASES_R2.md) is the delta since the round-1 integration (`121ed4d`, markers.py at step25) and the new round-2 angle.
Every number here is the integrated model (`runs/t5-chartjs/best.pt` + `--tta shift` + `--refine`) unless marked otherwise.
Paths are relative to `ml/` in this worktree.

## Tools

Carried over from round 1 (copied in from `teams/t4-markers/tools/` under the base worktree):

- `teams/t4-markers/tools/marker_diag.py`: per-marker diagnosis.
  No TTA option; the diag numbers are a lower bound against the integrated model's own TTA-enabled eval.
- `teams/t4-markers/tools/probe_report.py`: slices a diagnosis `rows.json` by `meta["probe"]`.
- `teams/t4-markers/tools/bias_check.py`: ink centroid of the returned marker on no-pixel-truth images.
- `teams/t4-markers/tools/diag_delta.py`, `perchart_delta.py`, `suite_table.py`: delta table builders.
- `p2d/synth/probe_t4.py`: the probe generator.
  Round-2 adds the `linemk` kind (section 11 below).

New in round 2:

- `teams/t4-markers/tools/probe_suite_r2.sh <tag> [--sets ...] [--no-diag]`: runs the seven round-1 probes plus `val`, `plotly` and `linemk` through evaluate against `runs/t5-chartjs/best.pt` with `--tta shift --refine`.
  Writes `out/t4r2/eval-<set>-<tag>.txt`, `rows-<set>-<tag>.json` and (unless `--no-diag`) `diag-<set>-<tag>/`.
- `teams/t4-markers/tools/probe_suite_r2_single.sh <tag>`: single-lock variant.
  Acquires the shared gpu.lock once and runs every set back to back inside that one lock session, so the queue sees one slot not ten.
  Preferred under heavy contention.
- `teams/t4-markers/tools/extract_eval_numbers.py <tag>`: parse the recall / precision / error from all `eval-<k>-<tag>.txt` files.
- `teams/t4-markers/tools/compare_before_after.py <before_tag> <after_tag>`: Markdown delta table between two tag's eval outputs.

## 10. Re-measured round-1 probes against the integrated model (pending)

Standard numbers only (`evaluate --refine --tta shift`).
Comparison target: the step25 isolated numbers from `CASES.md` section 9 (measured with `runs/v3/best.pt` and `--refine`, no TTA).

The nine-set measurement is queued on the shared `gpu.lock` and did not complete inside the round-2 session's time budget (t5-robust was running a 3000-iter training on the GPU for most of the round-2 window, plus eight other teams' queued evals ahead of ours).
The suite is still queued at session end; outputs will land at `out/t4r2/eval-<k>-int.txt` and the comparison table at `out/t4r2/suite-int.log` once the lock clears.

The INTEGRATION-REPORT already gives mpl-val and plotly marker numbers for the integrated model (its measurement uses the full `pipeline.run`, where `refine_markers` runs by default):

| chart | metric | base (v3) | integrated | delta |
| --- | --- | --- | --- | --- |
| mpl-val `all` | marker_recall | 0.481 | 0.613 | +0.132 |
| mpl-val `all` | marker_precision | 0.640 | 0.736 | +0.096 |
| mpl-val `simple` | marker_recall | 0.642 | 0.809 | +0.167 |
| mpl-val `simple` | marker_precision | 0.741 | 0.845 | +0.105 |
| plotly `all` | marker_recall | 0.418 | 0.403 | -0.016 |
| plotly `all` | marker_precision | 0.772 | 0.795 | +0.024 |
| plotly `simple` | marker_recall | 0.762 | 0.824 | +0.062 |
| plotly `simple` | marker_precision | 0.783 | 0.912 | +0.130 |

The whole-integration gain is huge on mpl-val markers (+10 to +17 pp recall/precision) and strongly positive on plotly simple markers.
On plotly `all` the integration moves a tiny amount of recall into precision; `all` includes several catastrophic charts (one 6081-marker rope) and is noise-dominated.

### Expected shape of the probe deltas (anchored on the integration report's win pattern)

- **dense, multi**: large recall gain from t5's native-res reads (sub-pixel ropes still unresolved); err probably within +/- 0.02 pp.
- **row**: should be a touch better (t5's native read helps the thin markers; the step25 line-stroke veto is unchanged).
- **shapes, hollow**: likely unchanged on precision/recall (step25's symmetric centroid is the dominant mechanism; t5's new read does not change the ink shape).
- **labels**: possibly slight recall gain (t5 is better at distinguishing marker peaks from glyphs in native resolution).
- **multi**: should match the general-set wins (+3 to +6 pp recall).
- **lines**: step25 drops ~88 of v3's 534 spurious markers; integration should preserve that unless t5 reclassifies some ink.

The round-2 angle (y-snap to line) is orthogonal to all of these: it only moves centres on line+markers series, and it moves y, not x.
So the round-2 patch should not change these numbers beyond the second decimal place of `marker_err_median_pct` on the sets with line+markers series (val, plotly, row, labels).

## 11. Round-2 angle: y-snap to the traced line (linemk probe)

### The failure the angle targets

On a line+markers series the marker's x is the data position (exact in the chart's abscissa) and its y is the drawn y value.
PlotNet's marker heat has sigma ~1.5 px at the drawn centre; after step25's measure_series, a symmetric marker's y is the ink centroid, which is right.
A non-symmetric marker, or one in a no-iso cloud, is the raw heat peak, which drifts.
When the markers are drawn ON a line, the line tracer measures the line's y to ~0.2% median RMS - a tighter y anchor than any one marker's heat.

Step25 does nothing with this fact.
Round-2's claim: replace the measured y with the traced line's y at the same x, where the two agree within half the marker's size.
An outlier plotted beside the line (y disagreement > `max(1.5, 0.6 * size)`) is left alone.

### Why this is NOT just "x-smooth the markers"

The line tracer runs on the pixels, not on the marker list.
Where the line is drawn under the markers, the trace is averaged along the ridge over tens of pixels in x, so its sub-pixel y is independent of any one marker's heat.
Snapping to it is a direct precision gain, not a smoothing.
On a chart where the line is dashed and sparse, `len(line_px) < 3` and the snap does nothing.
On a chart where some markers have no line under them (end labels, discontinuities), the per-marker x-range check (`xmin <= x <= xmax`) leaves them alone.

### Probe set `data/t4r2-linemk`

216 charts at seeds 14,100,000 to 14,100,215, generated by `p2d/synth/probe_t4.py --kind linemk`.
Each chart's `meta["probe"]`:

| field | type | meaning |
| --- | --- | --- |
| `kind` | str | "linemk" |
| `spacing_rel` | float | nearest-neighbour marker spacing along x in marker diameters (0.3 to 2.5) |
| `ms_px` | float | marker diameter in source pixels |
| `n_series` | int | 1 or 2 |
| `line_lw_pt` | float | line stroke in points (0.8 to 4) |
| `dashed` | bool | solid 60%, dashed 40% |
| `shape` | str | one of o, s, D, ^, v, *, x, P, + |
| `n` | int | markers per series |
| `nn_px_median` | float | measured nearest-neighbour spacing in source px |
| `nn_rel_median` | float | measured spacing / median diameter |
| `n_markers` | int | total markers in-plot-area |

Ground truth: `markers_px` records the exact value position (what the scoreboard matches against); `markers_drawn_px` records the drawn centre (matplotlib's integer snap).

Realised distribution across 216 charts (`python teams/t4-markers/tools/extract_eval_numbers.py` after fill-in or inspect `data/t4r2-linemk/*.json`):

- 63,886 total markers
- spacing_rel: 0.3 (26), 0.5 (48), 0.7 (36), 1.0 (37), 1.5 (33), 2.5 (36)
- line_lw_pt: 0.8 (54), 1.5 (40), 2.5 (53), 4.0 (69)
- dashed: 76 / solid: 140
- n_series: 1 (152), 2 (64)
- shape: *, +, o, ^, s, x, D, P, v (balanced 17-33 each)

Representative seeds:
- `14100006` (sp=0.3): 245 markers at nn 3.43 px, diameter 10.7 px (ratio 0.32 - packed rope)
- `14100000` (sp=1.5): 136 markers at nn 17.5 px, diameter 10 px (ratio 1.75 - separated)
- `14100002` (sp=2.5): 54 markers at nn 33.3 px, diameter 10 px (ratio 3.3 - sparse)

### Baseline numbers (integrated, no snap) - pending

See section 10's blocker.
The baseline suite will fill `out/t4r2/eval-linemk-int.txt` once the lock clears.

### After the snap (predicted)

Prediction based on round-1 line_rms being 0.14 to 0.21% median:

- `marker_err_median_pct` collapses toward `line_rms_median_pct` (0.14-0.21%) wherever `line_px` covers the marker's x.
  Markers where `line_px` is sparse or absent keep their raw heat peak y.
- Recall and precision unchanged (the snap moves centres; it adds and drops nothing).

Measured numbers after the brainstormer unstashes the patch: will fill `out/t4r2/eval-linemk-snap.txt` once the AFTER run completes.

### Diagnosis slices (expected)

By `spacing_rel`:

| spacing_rel | expected before | expected after |
| --- | --- | --- |
| 0.3 (dense rope) | high error, low recall | lower error on survivors, recall unchanged |
| 0.5-0.7 (just-touching) | moderate error | big error cut |
| 1.0-1.5 (separated) | low error | small-to-moderate error cut |
| 2.5 (sparse) | smallest error | smallest cut (already close) |

By `line_lw_pt`:

| line_lw_pt | expected before | expected after |
| --- | --- | --- |
| 0.8 (thin) | heat dominates line | moderate cut (line y is reliable but weak anchor) |
| 2.5-4.0 (thick) | heat drifts toward line | large cut (line y strong anchor; moves heat peak to line) |

By `dashed`:

| dashed | expected before | expected after |
| --- | --- | --- |
| False (solid) | step25 baseline | large cut (dense trace) |
| True (dashed) | small drift (step25 dash gate off for line+markers) | moderate cut (trace sparser; gate falls back on no coverage) |

## 12. What this round does NOT touch

- F1 ropes (sub-pixel spacing): the zoom pass is still out.
  Any angle that resolved a rope would need to run the network at higher resolution on the chart's dense regions.
- F3 big markers: the integrated pipeline already handles big filled markers (step25's mixture + Agg snap).
  Residual on open rings is the hollow case; sub-1pt gain for a round-2 fix.
- F6 glyphs/digits: step25's `sem[TEXT] < sem[DATA]` veto is in the integrated pipeline and does what it does (nothing on mpl-val, +0.013 precision on the labels probe).
  PlotNet's `sem` map puts digit glyphs under DATA, not TEXT; a stronger discriminator needs a retrain.
- F8 centre precision bias (matplotlib's integer snap): corrected inside markers.py in round-1 (step25).
- Pure scatter: no `line_px` -> snap is a no-op.

## 13. Measurement caveat

Round-2's probe measurement sessions were blocked by heavy contention on the shared `gpu.lock`:

- t1-axis diag.py held the lock through our first 10-minute window.
- t2-trace cross-oracle, t2-trace plotly-v1, t3-precision peaks, t3-precision ticks, t5-robust t5-blur and t5-robust t5-dark all queued ahead.
- t5-robust launched a 3000-iter training job (batch 8, 6 workers) which took ~20-30 minutes on the GPU during the critical window.

The single-lock suite was waiting at session end.
The scaffolding (probe generator, tools, report, cases) is complete.
Fill-in of the before/after numbers is deferred to the first available moment on the shared GPU.

## Appendix: branch state and verification

- Branch: `team/t4-markers-r2`.
  Base: `integration/round-1` at `121ed4d`.
- Commits by the curator:
  - `44264f9`: scaffolding (probe_t4 linemk kind, suite runner, CASES_R2 + REPORT_R2 skeletons).
  - `22cfafe`: extract_eval_numbers, single-lock runner, compare_before_after.
- Pending commit from brainstormer:
  - the y-snap patch (currently stashed as `stash@{0}: t4r2-brainstormer: line-snap patch, hold for baseline`).
- Pytest at the stashed baseline: 110 passed.
  With the stashed patch applied: 112 passed (confirmed by brainstormer).
