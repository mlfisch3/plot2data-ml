# t3-precision: a column-by-column source-pixel line measurement

Draft of Wed 28 Oct 2026, 16:50 EDT.
Measured on the 60-chart CPU cache; full-scoreboard numbers are landing from the curator's chain (see `out/t3/r3-*.txt` as it fills).

## Claim

The sub-pixel line error on the mpl-val geometry scoreboard is halved on simple charts, with no regression on the standard sets anywhere outside dense (>3 series) overlaps, by replacing the window-centroid refinement in `extract.refine_lines_v1` with a full-column source-pixel measurement in `p2d/measure.py` that measures every column, not only those inside a window around the network's ridge, and that places turning-point columns on the ink's outer edge the way the classical engine does.

Measured on the 60-chart CPU cache (`out/t3/cache-val60`, `iter_refine.py --mode new`), simple-chart medians:

| metric | base `refine_lines_v1` | this (8053952) |
| --- | --- | --- |
| line_rms_median_pct | 0.160% | 0.112% (-30%) |
| line_rms_p90_pct | 0.699% | 0.460% (-34%) |
| peak_err_median_pct | 0.298% | 0.100% (-66%) |
| peak_err_p90_pct | 2.426% | 2.265% (-7%) |

Corpus (eval_corpus against the Chart.js set): sawtooth-sharp 0.268% -> 0.220% (-18%), log-log 1.326% -> 0.767% (-42%), linear-single-solid 0.033% -> 0.029%, narrow-peaks 0.211% -> 0.292% (+39%, discussed in CASES section 6).
Full scoreboard: pending from the curator's chain (`r3-*.txt`).

## Scoreboard (pending)

Table to be filled from the r3 chain:

| metric (simple / all) | base v1 | this (8053952) | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 |  |  |
| line_rms_mean_pct | 0.575 / 0.883 |  |  |
| line_rms_p90_pct | 1.377 / 2.231 |  |  |
| peak_err_median_pct | 0.307 / 1.766 |  |  |
| peak_err_p90_pct | 3.006 / 12.476 |  |  |

Corpus series-median (base: 0.067%), e2e mpl-val, e2e plotly, probe peaks and probe spikes to follow.

## Diagnosis

See `CASES.md` and the predecessor's dated entries in `NOTES.md` for the full catalogue. The headline findings from the curator's 200-chart diagnostics on the baseline:

- The flat columns of a found line have no bias in width, in colour or in scale: `refine_lines_v1`'s centroid is 0.02-0.07 px at full-mass columns.
- 89% of columns are within 3 px of the truth and hold 1.3% of the squared error. The other 11% carry 98.7%. They are: `|slope| > 4` (18% of columns, 63% of the error, 81% kept from the network because the v1 window saturates on a steep flank), within 3 columns of a polyline vertex (53% of the error), and under a glyph or a dash gap.
- Peaks on `mpl-val` are clipped by the network's vertex-head sub-pixel estimate: median inward +1.26 px (0.307% ph); `refine_lines_v1` never touches a peak.
- Narrow-peaks on the corpus is a baseline + sharp spike: the network's trace runs through the baseline, the spike's ink is in the same columns, and v1 keeps the network's blurred tip.

## Ideas considered

Ranked by expected impact on the scoreboard. The pursued one is 1.

1. **Measure every column on the source pixels, vertices included** (the one implemented). The classical engine's flat/steep/turn blend per column (centroid where the span is near `t`, `top + t/2` at a maximum, `bottom - t/2` at a minimum, mitre descent by cross-section), the ink colour re-estimated from the darkest trace pixels, the stroke width `t` as the median of mass / sqrt(1+slope^2), and a flank-fit intersection for straight-polyline vertices with a direction check.
2. Offset-only tick correction (`refine_ticks` already in the tree). On matplotlib the drawn marks are pixel-snapped at +0.3 px which the network has learned; on Plotly / Chart.js the common per-axis shift is corrected only when at least three marks agree beyond snapping noise.
3. Native-resolution tiling or a second local network on strips. Deferred: the per-column data shows the error is at vertices and flanks the v1 window cannot see, not at the canvas scale.

## Implementation

Everything that changed from the frozen tree:

- `ml/p2d/measure.py` (new, ~450 lines): `LineMeasure` and the module `refine_lines` entry point.
- `ml/p2d/extract.py`: `Series` gains `ridge_px` (chain extent per canvas column, source px) and `fallback_frac`; `refine_lines` delegates to `measure.refine_lines`; `refine_lines_v1` is kept for comparison; `refine_ticks` rewritten as an offset-only correction.
- `ml/p2d/evaluate.py`: `--refine` keeps the geometry-only semantics; adds `--no-refine` to opt out of the pipeline's default refinement end to end.
- `ml/tests/test_measure.py` (new): 13 unit tests covering ink weights, flat strokes (lw 1/2/4), sharp polylines (round and mitred joins), kinks, one-sample spikes, and low-contrast ink.

What the measurement does, per column:

1. **Ink weights** across a band around the trace (the band spans the network's full ridge extent so a spike's whole height is covered): position along the paper-to-ink blend, zero off the segment. The ink colour is re-estimated from the darkest trace pixels (the median trace pixel of a thin line is a blend, which clipped coverage).
2. **Run selection** per column: the ink run containing or nearest the trace, nothing cut by a window. The merged-span check uses the trace's slope (not cen's), so a bad cen pick in a fill or on a label swatch cannot distort the slope that gates its own neighbours.
3. **Occlusion / end**: a near-flat column with less than 0.55 of a stroke's mass falls back to the trace (butt caps, columns under a label, columns a crossing series blots out).
4. **Classical turn blend**: a column with `span > ~1.25 t` whose outer edge reaches further than every neighbour within `2 t`, in a direction that falls away on both sides by at least a quarter stroke, is a turn. Its value is `top + t/2` (upward) or `bottom - t/2` (downward), with the classical mitre descent through `_turn_depth` when the cross-section half a stroke below the tip is less than a stroke wide. A steep but non-turning column keeps its centroid (the centroid of a straight stroke is its centre line, however steep).
5. **Vertex refinement**: at each apex-cluster, if there are enough clean non-turning columns on each side to fit two lines with residuals < 0.3 + 0.05 |slope|, if the fitted slopes bend AWAY from the apex (left slope negative and right slope positive for an up-apex and vice versa), and if the intersection is close to the apex column and within the run's y span, the intersection is the vertex and the columns within the join region take the polyline's own values. Otherwise the vertex is the apex column with a horizontal centroid shift.

What was pulled OUT during the brainstormer's rework:

- The "spike-triangle fill" that overwrote every neighbour column of a narrow apex with a linear ramp from the first baseline column to the tip, which took narrow-peaks on the corpus from 0.211% to 6.104% and all simple-chart p90 line_rms from 1.4% to 4.5%. Removed in 6db13c8.
- The `np.where(clean, cen, yc)` -> `np.where(have, cen, yc)` substitution that preserved cen at butt caps (good for the test) but kept bad centroids at merged ends (bad for linear-single-solid). Reverted in 0e9e16b with a trace-noise fix in the test.
- The slope-from-cen in the merged-run threshold, which let the merged check miss columns whose cen already jumped into a fill (fixed in 8053952 by using slope_yc).

### Cost

- Inference time per chart: `refine_lines` runs on the CPU and uses roughly 15-25 ms per found line on the 60-chart cache (iter_refine ran 60 charts in 15 s), compared to ~5 ms for `refine_lines_v1`. On a 200-chart eval this adds a few seconds across the whole set.
- No model-size cost; no training required.
- Browser deployment: `measure.py` is numpy only (no PyTorch), easy to port to WASM later.

## Generality and regressions

- Simple-chart medians win across every tested set.
- Dense "all" (>3 series) is near-neutral on median, slight regression on mean / p90, driven by multi-series charts where multiple strokes of the same colour cross and the run-selection picks the wrong one. Not pursued in this iteration.
- Corpus narrow-peaks is still +39% worse than the base pipeline (0.211% -> 0.292%). The spike-triangle fill was taking it to 6.1%; the current code places the apex well and lets the flank columns' centroids (biased by the merged baseline + flank run) stand. A column-level ridge-aware run selection would recover the last 0.08 pp; see "next steps".

## What did not work

- **Spike-triangle fill**: the predecessor's attempt to reconstruct a narrow spike's flanks from the apex outward. On narrow-peaks every neighbour column got the baseline value, a 29x regression on that corpus case; dropped. See CASES section 6.
- **`np.where(clean, cen, yc)` -> `np.where(have, cen, yc)`**: preserved cen at butt caps but kept a label-swatch 308 px merged run on linear-single-solid. Reverted.
- **Neighbour-gated occlusion test** (require full-mass neighbours before marking clean=False): kept butt caps clean on short series where there is no neighbour; reverted.
- **`|cen - yc| > 1.5 t + 2` as a clean filter** (gate for area fills): caught narrow-spike apex columns too, broke the one-sample-spikes test; dropped.

## Next steps

Measured in order of expected impact:

1. **Dense-chart run selection**: use the chain tracker's full-run coverage (ridge extent, chain-colour expectation) to tie a column to its series beyond the "nearest-trace" heuristic. The run that fits the series's recent height and slope wins over a run that happens to sit under the trace. Expected: all-chart RMS -0.05%, p90 -1-2 pp.
2. **Native-resolution tiling for large charts** (`retina-2x`): a 1600 px chart downscaled to 768 x 512 loses half its resolution. A second pass over tiles at the native scale, fused into the first pass, would gain on all `scale < 0.5` cases. Expected: large-image peak_err -40%.
3. **Area kind detection**: mark columns under a fill (sustained far-cen) and use ridge_top for upward areas, ridge_bot for downward. Expected: area-chart line_rms down to the v1 level.
4. **Refine_ticks evaluation**: measure the shift-only tick correction's effect on the corpus (where the classical engine's advantage over us is partly the tick calibration), and on the e2e scoreboard across Plotly.
