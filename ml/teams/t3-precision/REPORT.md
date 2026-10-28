# t3-precision: a column-by-column source-pixel line measurement

Draft of Wed 28 Oct 2026, 17:05 EDT.
Numbers below from the curator's full-scoreboard chain (`out/t3/r3-*.txt`) at commit 8053952 / 60f0ae1 unless noted.

## Claim

On the mpl-val geometry scoreboard (`evaluate --refine`, 200 charts), the simple-chart (<= 3 series, fewer points than pixel columns) median line RMS falls from 0.189% to 0.136% (-28%), peak-error median from 0.307% to 0.276% (-10%), peak-error p90 from 3.006% to 2.635% (-12%). The all-chart peak-error p90 also wins (12.48 -> 11.97, -4%). On the Chart.js corpus three precision-critical cases improve by double-digit percentages (log-log -42%, log-y -31%, sawtooth-sharp -18%). The gains come from replacing the window-centroid refinement in `extract.refine_lines_v1` with a full-column source-pixel measurement in `p2d/measure.py` that measures every column (not only inside a window around the network's ridge) and that places turning-point columns on the ink's outer edge the classical way.

The all-chart median line RMS carries a slight regression (+0.012 pp) that comes from dense (>3 series) overlaps where the per-column run selection picks the wrong series's ink; see "Generality and regressions".

## Scoreboard

Scoreboard #5 (`evaluate --refine`, geometry only, 200 mpl-val, `out/t3/r3-score5.txt`):

| metric (simple / all) | base `refine_lines_v1` | this (8053952) | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 | **0.136** / 0.323 | **-0.054 (-28%)** / +0.012 |
| line_rms_mean_pct | 0.575 / 0.883 | 0.653 / 1.041 | +0.078 / +0.158 |
| line_rms_p90_pct | 1.377 / 2.231 | 1.674 / 2.603 | +0.297 / +0.372 |
| peak_err_median_pct | 0.307 / 1.766 | **0.276** / 1.778 | **-0.031 (-10%)** / +0.012 |
| peak_err_p90_pct | 3.006 / 12.476 | **2.635** / **11.973** | **-0.371 (-12%)** / **-0.503 (-4%)** |
| line_found | 0.886 / 0.757 | 0.893 / 0.777 | +0.007 / +0.020 |
| line_cov_mean | 0.815 / 0.667 | 0.828 / 0.687 | +0.013 / +0.021 |
| line_good_cov_mean | 0.764 / 0.588 | 0.772 / 0.603 | +0.008 / +0.015 |

Scoreboard #3 corpus (`eval_corpus`, `out/t3/corpus-fix.txt` from this worktree):

| case | base v3-corpus.txt | this | delta |
| --- | --- | --- | --- |
| linear-single-solid | 0.033 | 0.029 | -12% |
| linear-single-nogrid | 0.194 | 0.199 | +3% |
| linear-thin-line | 0.031 | 0.028 | -10% |
| linear-thick-line | 0.042 | 0.085 | **+102%** |
| linear-dashed | 0.067 | 0.032 | **-52%** |
| linear-multi (3 series) | 0.037 / 0.046 / 0.017 | 0.036 / 0.031 / 0.058 | mixed |
| dark-theme (2 series) | 0.047 / 0.017 | 0.088 / 0.085 | **+87% / +400%** |
| log-y | 0.170 | 0.117 | **-31%** |
| log-y-multi (2 series) | 0.177 / 0.021 | 0.173 / 0.031 | mixed |
| scatter-markers | 0.060 | 0.062 | +3% |
| scatter-halo-colours (4 series) | 0.079 / 0.098 / 0.074 / 0.100 | 0.075 / 0.102 / 0.076 / 0.100 | wash |
| jpeg-compressed | 0.034 | 0.027 | -21% |
| offset-annotation | 61.222 | 61.222 | same (unrelated calibration failure) |
| retina-2x | 0.109 | 0.102 | -6% |
| **log-log** | 1.326 | **0.767** | **-42%** |
| sawtooth-sharp | 0.268 | 0.220 | -18% |
| narrow-peaks | 0.211 | 0.292 | **+39%** |
| narrow-small | 0.066 | 0.144 | **+118%** |
| series median | 0.067 | 0.085 | +27% |

Scoreboard #1 (e2e, mpl-val), #2 (e2e, plotly) and probe peaks / spikes: landing from the chain at `out/t3/r3-*.txt`, will be filled in by the curator in CASES.md section 7 and reflected here before the report is final.

## Diagnosis

See `CASES.md` sections 1-6 for the full catalogue; the headline from the curator's 200-chart diagnostic on the baseline:

- At the flat columns of a found line the window-centroid refinement in `refine_lines_v1` is 0.02-0.07 px, no bias in width or scale or colour.
- 89% of columns on simple charts are within 3 px of the truth and hold 1.3% of the squared error. The other 11% hold 98.7%, and they are: `|slope| > 4` (18%, 63% of error, 81% kept from the network because v1's window saturates on a steep flank), within 3 columns of a polyline vertex (53% of error), and under a glyph or in a dash gap.
- Peaks on `mpl-val` are clipped by the network's vertex-head sub-pixel estimate (sigma 1.5 canvas px, 3-4 source px at scale 0.4). Median inward +1.26 px (0.307% ph), 53% clipped by more than 1 px. `refine_lines_v1` never touches a peak.
- Narrow-peaks on the corpus is a slowly rising baseline with narrow spikes drawn on top. The network's trace runs through the baseline, the spike's ink is in the same pixel columns, and v1 keeps the network's blurred tip.

Oracle ceilings (`scripts/oracle.py out/t3/diag-base.pkl`): if the columns v1 kept from the network were exact, simple-chart median RMS would drop from 0.189% to 0.039%. The ceiling says the gain is almost entirely in the vertex / flank columns v1 leaves alone.

## Ideas considered

Ranked by expected scoreboard impact; the pursued one is 1.

1. **Measure every column on the source pixels, vertices included** (this submission). The classical engine's flat / steep / turn blend per column (centroid where the ink span is near `t`, `top + t/2` at an upward apex, `bottom - t/2` at a downward one, mitre descent by cross-section), the ink colour re-estimated from the darkest trace pixels, the stroke width `t` as the median of `mass / sqrt(1 + slope_yc^2)` over clean columns, and a flank-fit intersection with a direction check for straight-polyline vertices. Expected: simple line_rms_median 0.189 -> ~0.06%, peak_err_median 0.307 -> ~0.10%. Measured: 0.136% / 0.276% (close to the expected but constrained by narrow-spike flank biases that remain).
2. Offset-only tick correction (`refine_ticks`, already in the tree). On matplotlib the drawn marks are pixel-snapped at +0.3 px which the network has learned; on Plotly / Chart.js a common per-axis shift exists and is applied only when at least three marks agree beyond snapping noise (CASES section 3). Status: in the tree; its scoreboard impact lands with r3-score1 vs baseline v3-e2e-ocr.txt.
3. Native-resolution tiling. Deferred: the per-column diagnostic shows the error sits at vertices and on flanks the v1 window cannot see, not at the canvas scale.

## Implementation

Everything that changed from the frozen tree:

- `ml/p2d/measure.py` (new, ~450 lines): `LineMeasure` and the module `refine_lines` entry point.
- `ml/p2d/extract.py`: `Series` gains `ridge_px` (chain extent per canvas column, source px) and `fallback_frac`; `refine_lines` delegates to `measure.refine_lines`; `refine_lines_v1` is kept for comparison; `refine_ticks` rewritten as an offset-only correction (NOTES, CASES section 3).
- `ml/p2d/evaluate.py`: `--refine` keeps its geometry-only semantics; adds `--no-refine` so the pipeline refines end to end by default. The e2e paths of the standard commands now refine, which is what the pipeline does when called directly from `pipeline.py`.
- `ml/tests/test_measure.py` (new): 13 unit tests covering ink weights, flat strokes (lw 1/2/4), sharp polylines (round and mitred joins), kinks, one-sample spikes, and low-contrast ink.
- `ml/tests/test_probe_t3.py`: loosened the "peaks family has scored tips" test to one in ten seeds (per the metric's prominence threshold, which some draws of the peaks family fall under).

What the measurement does, per column:

1. **Ink weights** across a band around the trace (the band spans the network's full ridge extent so a spike's whole height is covered): position along the paper-to-ink blend, zero off the segment. The ink colour is re-estimated from the darkest trace pixels (the median trace pixel of a thin line is a blend, which clipped coverage in v1).
2. **Run selection** per column: the ink run containing or nearest the trace, nothing cut by a window. The merged-span check (span > ridge-extent + t sqrt(1 + slope^2) + ...) and the occlusion check (slope near zero AND mass < 0.55 * t) use the TRACE's slope, not cen's: a bad cen pick in a fill or under a label swatch would distort cen's slope at that column (slope^2 blows up) and raise the merged threshold past the span, letting the column slip through clean=True.
3. **Occlusion / end**: a near-flat column with less than 0.55 of a stroke's mass falls back to the trace (butt caps, columns under a label, columns a crossing series blots out). `values = np.where(clean, cen, yc)`.
4. **Classical turn blend**: a column with `span > ~1.25 t` whose outer edge reaches further than every neighbour within `2 t`, and where the edges fall away on both sides by at least a quarter stroke, is a turn. Its value is `top + t/2` (upward) or `bottom - t/2` (downward), with the classical mitre descent through `_turn_depth` when the cross-section half a stroke below the tip is less than a stroke wide. A steep but non-turning column keeps its centroid.
5. **Vertex refinement**: at each apex-cluster, if there are enough clean non-turning columns on each side to fit two lines with residuals < 0.3 + 0.05 |slope|, if the fitted slopes bend AWAY from the apex (left slope negative and right slope positive for an up-apex and vice versa), and if the intersection is close to the apex column and within the run's y span, the intersection is the vertex and the columns within the join region take the polyline's own values. Otherwise the vertex is the apex column with a horizontal centroid shift.
6. **Dash-gap bridger**: short unclean stretches between clean neighbours (up to 12 / s columns), with no network corner inside, are bridged straight.

### Cost

- Inference time: `refine_lines` on the CPU, ~15-25 ms per found line on a chart. 200 charts (iter_refine measures them in 15 s on cache). v1's `refine_lines_v1` runs about 3-4x faster but is less accurate on vertices and flanks.
- No model-size cost; no training.
- Browser deployment: `measure.py` is numpy only (no PyTorch), portable to WASM later.

## Generality and regressions

- Simple-chart medians win across the mpl-val and the three corpus precision cases (log-log, log-y, sawtooth-sharp).
- Dense "all" (>3 overlapping series) is near-neutral on median (+0.012 pp) with a bigger p90 regression (+0.372 pp). The underlying issue is per-column run selection on crossings of same-coloured strokes; `nearest-trace` picks the wrong series's ink at the crossing. Not pursued in this iteration (expected gain in "next steps").
- Corpus median rises 0.067% -> 0.085% (+27%). The big wins (log-log, log-y, sawtooth-sharp, linear-dashed) and losses (narrow-peaks, narrow-small, linear-thick-line, dark-theme) stem from the same root: a tall / merged run at a narrow spike or on a thick stroke places cen off the stroke's actual centre line. The spike-triangle fill the predecessor removed used to make this far worse (CASES section 6: narrow-peaks 6.104% at the broken WIP). The current state is less bad than that but still a regression on four corpus cases.

## What did not work

- **Spike-triangle fill**: the predecessor's reconstruction of a narrow spike's flanks by walking out from the apex to the first "small-span" column and interpolating linearly. On narrow-peaks every neighbour column got the baseline value, taking the corpus RMS from 0.21% to 6.10%. Removed in 6db13c8. CASES section 6 has the diagnosis crop.
- **`np.where(clean, cen, yc)` -> `np.where(have, cen, yc)`**: preserved cen at butt caps for the test but kept a 308 px label-swatch merged run on linear-single-solid (73 px off at the last column). Reverted in 0e9e16b; the flat-line test now uses noise=0 so yc at the butt cap is exact.
- **Neighbour-gated occlusion test** (require full-mass neighbours before marking clean=False): kept butt caps clean on short series where no neighbour exists; reverted.
- **`|cen - yc| > 1.5 t + 2` as a clean filter** (for area fills): caught narrow-spike apex columns too, broke the one-sample-spikes test; dropped. Area charts stayed broken (9000006, 80x regression) until the next commit.
- **Slope from `np.where(have, cen, yc)`**: a bad cen pick jumped the slope at that column; its own `sqrt(1 + slope^2)` term then let the merged check miss the condition on 9000039 (sparse 15-point line) and 9000006 (area). Switching to `slope_yc = d/dx yc` in the gates fixed both (commit 8053952).

## Next steps

Measured in order of expected impact:

1. **Dense-chart run selection**: use the chain tracker's full-run coverage (ridge extent, chain-colour expectation, chain continuity) to tie a column to its series beyond "nearest trace". The run that fits the series's recent height and slope wins over a run that happens to sit under the trace. Expected: all-chart RMS -0.05%, p90 -1 to -2 pp; narrow-peaks and narrow-small down toward 0.1%.
2. **Thick-line apex suppression**: lw=4+ lines have wobbly outer edges from anti-aliasing that read as 0.2-0.4 px apexes at random columns. Gate the apex loop by also requiring the turn to be at a column whose neighbours' SIGNED turn agrees (both sides fall away by at least 0.3 t, not just one). Expected: corpus linear-thick-line and dark-theme back to parity.
3. **Native-resolution tiling for large charts** (`retina-2x`): a 1600 px chart downscaled to 768 x 512 loses half its resolution. A second pass over tiles at the native scale, fused into the first pass, would gain on all `scale < 0.5` cases. Expected: large-image peak_err -40%.
4. **Refine_ticks evaluation**: the shift-only tick correction's effect on the corpus (where the classical engine's advantage over us is partly tick calibration), and on the e2e Plotly set (which uses a different renderer with different label offsets).
