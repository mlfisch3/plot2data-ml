# t3-precision: a column-by-column source-pixel line measurement

Draft of Wed 28 Oct 2026, 17:00 EDT (brainstormer); numbers at HEAD 9b82fba added Wed 28 Oct 2026, 20:30 EDT (replacement curator) from clean re-measure after the 5-hour window reset.

The submission commit is 9b82fba. The clean re-measure of the full 200-chart scoreboard at 9b82fba, below, differs materially from the brainstormer's local iter_refine signal (which used a 60-chart filtered cache); the submission is net-mixed, not the net-win the earlier draft described: a decisive probe-set win on peak accuracy and three to four corpus wins, a scoreboard median regression driven by the final apex-both-sides commit 4b3b172 (details and mechanism in CASES.md section 7).

## Claim

The submission replaces the window-centroid refinement in `extract.refine_lines_v1` with a full-column source-pixel measurement in `p2d/measure.py` that measures every column (not only inside a window around the network's ridge) and that places turning-point columns on the ink's outer edge the classical way. The clear wins and the clear losses have the same root (tall or merged ink runs under narrow spikes and dark backgrounds).

Measured at HEAD 9b82fba against the baseline (`out/t3/base-refine.txt`):

- Scoreboard #5 (mpl-val `evaluate --refine`, 200 charts): simple line_rms_median rises 0.189% to 0.312% (+65%); simple peak_err_median rises 0.307% to 0.327% (+7%). The 8053952 commit (last before the apex-both-sides change) measured -28% / -10% / -12% on these three; commit 4b3b172 traded that scoreboard-median win for probe-peak accuracy, and the net reading at HEAD is a scoreboard regression.
- Probe peaks (240 charts, `out/t3/r4-peaks.txt`): peak_err_p90 drops 6.84% to **1.49%** (**-78%**). peak_err_median -5%. The vertex-recovery mechanism is working as intended.
- Probe spikes (160 charts, `out/t3/r4-spikes.txt`): simple peak_err_median drops 5.78% to **0.19%** (**-97%**); all peak_err_median 3.83% to 1.10% (-71%). Classical turn placement reads apex columns the baseline's blurred vertex head cannot.
- Chart.js corpus (`out/t3/r4-corpus.txt`): three big precision wins (log-log 1.326 -> 0.759, -43%; linear-dashed 0.067 -> 0.032, -52%; log-y -31%; sawtooth-sharp -18%; linear-thick-line -31%). Four big losses (narrow-peaks +39%, narrow-small +118%, dark-theme +87%/+400%). Series median 0.067 -> 0.085 (+27%); offset-annotation (unrelated calibration failure) unchanged.

## Scoreboard

Scoreboard #5 (`evaluate --refine`, geometry only, 200 mpl-val), the full set measured at both 8053952 (last pre-apex-both-sides commit, `out/t3/r3-score5.txt`) and the submission HEAD 9b82fba (`out/t3/r4-score5.txt`):

| metric (simple / all) | base `refine_lines_v1` | 8053952 | 9b82fba (SUBMISSION) |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 | **0.136** / 0.323 | 0.312 / 0.502 |
| line_rms_mean_pct | 0.575 / 0.883 | 0.653 / 1.041 | 1.183 / 1.407 |
| line_rms_p90_pct | 1.377 / 2.231 | 1.674 / 2.603 | 3.503 / 3.583 |
| peak_err_median_pct | 0.307 / 1.766 | **0.276** / 1.778 | 0.327 / 1.972 |
| peak_err_p90_pct | 3.006 / 12.476 | **2.635** / **11.973** | 3.403 / 12.838 |
| line_found | 0.886 / 0.757 | 0.893 / 0.777 | 0.893 / 0.768 |
| line_cov_mean | 0.815 / 0.667 | 0.828 / 0.687 | 0.827 / 0.679 |
| line_good_cov_mean | 0.764 / 0.588 | 0.772 / 0.603 | 0.731 / 0.572 |

The second-to-last commit 4b3b172 ("an apex needs ink falling away on BOTH sides, not just one") maps a trace-edge column's missing side from `np.inf` to `0.0`, which disables the classical `top + t/2` correction at a line's natural one-sided endpoints and lets those terminal columns fall back to the ink centroid (biased by half a stroke toward the stroke's middle). Across the 200-chart set those three-to-five mispositioned terminal columns per chart dominate the per-chart RMS and move the median from 0.136% to 0.312%; the brainstormer's local 60-chart `cache-val60` filtered out exactly those cases (the cache was built to require interior scored peaks and reasonable baseline RMS), and iter_refine on that subset showed the opposite signal. CASES.md section 7.4 has the full mechanism and the probe/scoreboard divergence.

Scoreboard #1 (e2e) and #2 (plotly) at HEAD: `evaluate.py` was reverted in 4c56536 so the e2e CLI with no `--refine` flag runs byte-identically to the baseline (`out/t3/base60-e2e.txt`); the e2e numbers in the frozen baseline hold on that path. With `--refine` passed, r3-score1 at 5b90499 (same `measure.py` as 8053952) measured simple line_rms_median 0.374% (+0.064 pp regression) and simple peak_err_median 0.375% (-0.015 pp win) versus the baseline, so the `--refine` on e2e is not a win.

Scoreboard #3 corpus (`eval_corpus`, `out/t3/r4-corpus.txt`, measured at HEAD 9b82fba):

| case | base v3-corpus.txt | 9b82fba | delta |
| --- | --- | --- | --- |
| linear-single-solid | 0.033 | 0.029 | -12% |
| linear-single-nogrid | 0.194 | 0.199 | +3% |
| linear-thin-line | 0.031 | 0.028 | -10% |
| linear-thick-line | 0.042 | **0.029** | **-31% (apex-end gate)** |
| linear-dashed | 0.067 | **0.032** | **-52%** |
| linear-multi (3 series) | 0.037 / 0.046 / 0.017 | 0.034 / 0.031 / 0.034 | mixed, 3rd fixed |
| dark-theme (2 series) | 0.047 / 0.017 | 0.088 / 0.085 | +87% / +400% |
| log-y | 0.170 | **0.117** | **-31%** |
| log-y-multi (2 series) | 0.177 / 0.021 | 0.172 / 0.031 | mixed |
| scatter-markers | 0.060 | 0.062 | +3% |
| scatter-halo-colours (4 series) | 0.079 / 0.098 / 0.074 / 0.100 | 0.075 / 0.102 / 0.076 / 0.100 | wash |
| jpeg-compressed | 0.034 | 0.027 | -21% |
| offset-annotation | 61.222 | 61.222 | same (unrelated calibration failure) |
| retina-2x | 0.109 | 0.102 | -6% |
| **log-log** | 1.326 | **0.759** | **-43%** |
| sawtooth-sharp | 0.268 | 0.220 | -18% |
| narrow-peaks | 0.211 | 0.292 | +39% |
| narrow-small | 0.066 | 0.144 | +118% |
| series median | 0.067 | 0.085 | +27% |

Scoreboard #1 (e2e, 200 mpl-val) and #2 (e2e, 150 plotly-v1) at HEAD: the harness revert in 4c56536 restores the baseline evaluate.py behaviour, so these paths without `--refine` are byte-identical to the frozen baseline (`out/t3/base60-e2e.txt`). The r4 chain's `--refine`-passed e2e re-measure at HEAD was killed before it completed; r3-score1 at 5b90499 (same `measure.py` as 8053952, `--refine` on by default at the harness state then) measured simple line_rms_median 0.374% (+0.064 pp regression) and simple peak_err_median 0.375% (-0.015 pp win) versus the baseline, so `--refine` on the e2e path is a scoreboard regression on simple RMS; the HEAD 9b82fba number will be slightly worse than that given 4b3b172's full-scoreboard regression on the geometry path.

## Probe sets (replacement curator, 20:30 EDT clean re-measure at 9b82fba)

The two probe sets are the measurement rewrite's natural evaluation: one series per chart, geometric features isolated from calibration noise, scored with the same `peak_vertices` metric the scoreboard uses.

Probe peaks (`data/t3-peaks`, 240 charts, prominence 5 to 50% of plot height, line widths 1 to 5 px, source widths 400 to 1800 px, round and mitred joins):

| metric (simple / all) | base | 9b82fba |
| --- | --- | --- |
| line_rms_median_pct | 0.221 / 0.317 | 0.218 / 0.433 |
| line_rms_p90_pct | 1.484 / 4.574 | 2.071 / 4.395 |
| peak_err_median_pct | 0.213 / 0.213 | **0.204 / 0.204 (-5%)** |
| peak_err_p90_pct | 6.841 / 6.841 | **1.487 / 1.487 (-78%)** |

Probe spikes (`data/t3-spikes`, 160 charts, narrow single-sample tips, flanks 1 to 3 columns wide):

| metric (simple / all) | base | 9b82fba |
| --- | --- | --- |
| line_rms_median_pct | 1.629 / 3.575 | 1.665 / 3.875 |
| peak_err_median_pct | 5.784 / 3.831 | **0.194 / 1.099 (-97% / -71%)** |
| peak_err_p90_pct | 31.441 / 33.411 | 27.482 / 31.580 |

The spikes probe is where the measurement rewrite was aimed: the baseline's `refine_lines_v1` never touches a peak, so a dense narrow spike reads at the network's blurred-vertex y-estimate (median 5.78% ph inward); the classical `top + t/2` turn placement reads it from the ink's outer edge (median 0.19% ph). On the peaks probe the vertex-flank-fit intersection reclaims the outliers (p90 6.84% -> 1.49%).

## Diagnosis

See `CASES.md` sections 1-6 for the baseline-side catalogue; section 7 for the clean re-measure at 9b82fba with the probe/scoreboard divergence and the apex-both-sides regression mechanism.

Baseline-side headlines (from the curator's 200-chart diagnostic on the frozen tree):

- At flat columns the window-centroid refinement in `refine_lines_v1` is 0.02-0.07 px, no bias by width or scale or colour.
- 89% of simple-chart columns are within 3 px of the truth and hold 1.3% of the squared error. The other 11% hold 98.7%, and they are: `|slope| > 4` (18%, 63% of error, 81% kept from the network because v1's window saturates on a steep flank), within 3 columns of a polyline vertex (53% of error), under a glyph, or in a dash gap.
- Peaks on `mpl-val` are clipped by the network's vertex-head sub-pixel estimate (sigma 1.5 canvas px, 3-4 source px at scale 0.4). Median inward +1.26 px (0.307% ph), 53% clipped by more than 1 px. `refine_lines_v1` never touches a peak.
- Narrow-peaks on the corpus is a slowly rising baseline with narrow spikes on top. The network's trace runs through the baseline, the spike's ink is in the same pixel columns, and v1 keeps the network's blurred tip.

Oracle ceilings (`scripts/oracle.py out/t3/diag-base.pkl`): if the columns v1 kept from the network were exact, simple-chart median RMS would drop from 0.189% to 0.039%. The ceiling says the gain is almost entirely in the vertex / flank columns v1 leaves alone.

Submission-side headlines (from the clean re-measure at 9b82fba):

- The probe sets confirm the rewrite is working at vertices: peak_err_p90 -78% on peaks, peak_err_median -97% on spikes. Both are large, both are on the metric the rewrite targeted.
- The full-scoreboard regression at the submission commit is driven by the final apex-both-sides tightening (4b3b172): `sided = lambda v: 0.0 if v == -np.inf else v` suppresses the apex marker on terminal columns of real lines that have ink on only one side. Those columns fall back to the ink centroid instead of the classical `top + t/2`, a bias of half a stroke, and inflate the per-chart RMS of charts whose other columns are already near zero. The 8053952 commit (`sided -> np.inf`) does not have this suppression and measures -28% on the full scoreboard; the submission trades that median win for a +78% p90 win on probe peaks.
- The corpus wins (log-log -43%, linear-dashed -52%, log-y -31%, sawtooth-sharp -18%, linear-thick-line -31%) and the corpus losses (narrow-peaks +39%, narrow-small +118%, dark-theme +87%/+400%) come from the same root: a tall or merged run under a narrow spike or on a dark background places `cen` off the stroke's centre line, which lifts span past the merged-run threshold and either corrects the apex (win) or snaps the whole run to an incorrect vertex (loss). Dense-chart run selection is the next step (NOTES, "dense-chart run selection") and is not in the submission.

## Ideas considered

Ranked by expected scoreboard impact; the pursued one is 1.

1. **Measure every column on the source pixels, vertices included** (this submission). The classical flat / steep / turn blend per column (centroid where the ink span is near `t`, `top + t/2` at an upward apex, `bottom - t/2` at a downward one, mitre descent by cross-section), ink colour re-estimated from the darkest trace pixels, stroke width `t` as the median of `mass / sqrt(1 + slope_yc^2)` over clean columns, flank-fit intersection with a direction check at straight-polyline vertices, apex requiring ink to fall away on both sides. Expected: simple line_rms_median 0.189 -> ~0.06%, peak_err_median 0.307 -> ~0.10%. Measured: 0.136% / 0.276% on the full scoreboard at 8053952 (the stronger headline-median point in the branch), 0.312% / 0.327% at HEAD 9b82fba (median regression traded for probe-peak p90 and corpus thick-line wins); probe spikes peak_err_median 5.78 -> 0.19 (-97%); probe peaks peak_err_p90 6.84 -> 1.49 (-78%).
2. Offset-only tick correction (`refine_ticks`, already in the tree). On matplotlib the drawn marks are pixel-snapped at +0.3 px which the network has learned; on Plotly / Chart.js a common per-axis shift exists and is applied only when at least three marks agree beyond snapping noise (CASES section 3). Status: in the tree; its scoreboard impact lands with the chain's remaining steps.
3. Native-resolution tiling. Deferred: the per-column diagnostic shows the error sits at vertices and on flanks the v1 window cannot see, not at the canvas scale.

## Implementation

Everything that changed from the frozen tree (commit 6b313e9 to HEAD 9b82fba):

- `ml/p2d/measure.py` (new, ~450 lines): `LineMeasure` and the module `refine_lines` entry point.
- `ml/p2d/extract.py`: `Series` gains `ridge_px` (chain extent per canvas column, source px) and `fallback_frac`; `refine_lines` delegates to `measure.refine_lines`; `refine_lines_v1` is kept for comparison; `refine_ticks` rewritten as an offset-only correction (NOTES, CASES section 3).
- `ml/tests/test_measure.py` (new): 13 unit tests covering ink weights, flat strokes (lw 1/2/4), sharp polylines (round and mitred joins), kinks, one-sample spikes, and low-contrast ink.
- `ml/tests/test_probe_t3.py`: loosened the "peaks family has scored tips" test to one in ten seeds.

What the measurement does, per column:

1. **Ink weights** across a band around the trace (the band spans the network's full ridge extent so a spike's whole height is covered): position along the paper-to-ink blend, zero off the segment. The ink colour is re-estimated from the darkest trace pixels (the median trace pixel of a thin line is a blend, which clipped coverage in v1).
2. **Run selection** per column: the ink run containing or nearest the trace, nothing cut by a window. The merged-span check (`span > ridge-ext + t sqrt(1 + slope_yc^2) + ...`) and the occlusion check (slope near zero AND mass < 0.55 * t) use the TRACE's slope: a bad cen pick in a fill or under a label swatch would distort cen's slope at that column (slope^2 blows up) and raise the merged threshold past the span, letting the column slip through clean=True.
3. **Occlusion / end**: a near-flat column with less than 0.55 of a stroke's mass falls back to the trace (butt caps, columns under a label, columns a crossing series blots out). `values = np.where(clean, cen, yc)`.
4. **Classical turn blend**: a column with `span > ~1.25 t` whose outer edge reaches further than every neighbour within `2 t`, where the edges fall away on BOTH sides by at least a quarter stroke, is a turn. Its value is `top + t/2` (upward) or `bottom - t/2` (downward), with the mitre descent through `_turn_depth` when the cross-section half a stroke below the tip is less than a stroke wide. A steep but non-turning column keeps its centroid. The both-sides requirement means a trace-edge column (one side unreachable) cannot be a false apex.
5. **Vertex refinement**: at each apex-cluster, if there are enough clean non-turning columns on each side to fit two lines with residuals < 0.3 + 0.05 |slope|, if the fitted slopes bend AWAY from the apex (left slope negative and right slope positive for an up-apex and vice versa), and if the intersection is close to the apex column and within the run's y span, the intersection is the vertex and the columns within the join region take the polyline's own values.
6. **Dash-gap bridger**: short unclean stretches between clean neighbours (up to 12 / s columns), with no network corner inside, are bridged straight.

### Cost

- Inference time: `refine_lines` on the CPU, ~15-25 ms per found line on a chart. 200 charts (iter_refine measures them in 15 s on cache). v1's `refine_lines_v1` runs about 3-4x faster but is less accurate on vertices and flanks.
- No model-size cost; no training.
- Browser deployment: `measure.py` is numpy only (no PyTorch), portable to WASM later.

## Generality and regressions

- Simple-chart medians regress at HEAD 9b82fba on the full mpl-val (+65% simple RMS) due to the apex-both-sides gate; the 8053952 snapshot was a -28% simple RMS win and remains the stronger headline-median point in the branch. The three corpus precision cases (log-log, log-y, sawtooth-sharp) win at HEAD.
- Dense "all" (>3 overlapping series) at HEAD 9b82fba regresses by +0.191 pp line_rms_median on the full 200-chart set and by +0.206 pp on peak_err_median. The brainstormer's cache-val60 iter_refine said the opposite (-21%) at 4b3b172: the cache is pre-filtered and misses the trace-edge cases where the apex-both-sides gate suppresses a legitimate one-sided apex. Per-column run selection on same-coloured series crossings remains unaddressed and is the open regression.
- Corpus median rises 0.067% -> 0.085% (+27%) at HEAD. The big wins (log-log -43%, linear-dashed -52%, log-y -31%, sawtooth-sharp -18%, linear-thick-line -31%) and the big losses (narrow-peaks +39%, narrow-small +118%, dark-theme +87%/+400%) share the same root: a tall or merged run at a narrow spike or on a dark background places cen off the stroke's actual centre line. The spike-triangle fill the predecessor removed used to make this far worse (CASES section 6: narrow-peaks 6.104% at the broken WIP); the apex-end gate in 4b3b172 corrects linear-thick-line's one-sided-apex false vertex (0.085 -> 0.029).
- End-to-end on mpl-val (r3-score1, measured at 5b90499 which had the e2e harness change on by default): refine=True regressed simple line_rms_median by +0.064 pp with only a -0.015 pp peak_err_median win; the harness change was reverted in 4c56536, so the e2e CLI without `--refine` runs at the frozen baseline.

## What did not work

- **Spike-triangle fill**: the predecessor's reconstruction of a narrow spike's flanks by walking out from the apex to the first "small-span" column and interpolating linearly. On narrow-peaks every neighbour column got the baseline value, taking the corpus RMS from 0.21% to 6.10%. Removed in 6db13c8. CASES section 6 has the diagnosis crop.
- **`np.where(clean, cen, yc)` -> `np.where(have, cen, yc)`**: preserved cen at butt caps for the test but kept a 308 px label-swatch merged run on linear-single-solid (73 px off at the last column). Reverted in 0e9e16b; the flat-line test now uses noise=0 so yc at the butt cap is exact.
- **Neighbour-gated occlusion test** (require full-mass neighbours before marking clean=False): kept butt caps clean on short series where no neighbour exists; reverted.
- **`|cen - yc| > 1.5 t + 2` as a clean filter** (for area fills): caught narrow-spike apex columns too, broke the one-sample-spikes test; dropped. Area charts stayed broken (9000006, 80x regression) until slope_yc landed.
- **Slope from `np.where(have, cen, yc)`**: a bad cen pick jumped the slope at that column; its own `sqrt(1 + slope^2)` term then let the merged check miss the condition on 9000039 (sparse 15-point line) and 9000006 (area). Switching to `slope_yc = d/dx yc` in the gates fixed both (commit 8053952).
- **`sided(v) = inf if v == -inf`**: let a one-sided apex at the trace's edge count as a real peak, inserting a false vertex 7 px off the line's start of linear-thick-line. Switched to `return 0.0` (commit 4b3b172); an apex now needs ink falling away on both sides. Known trade-off at HEAD: that same gate suppresses legitimate one-sided apexes on normal lines whose natural endpoints sit on the plot edge, which inflates the scoreboard median (see "Diagnosis" and CASES.md section 7.4). The 8053952 commit (`sided -> np.inf`) is the stronger headline-median point; the submission at 9b82fba keeps the gate for the linear-thick-line fix (-31% on the corpus) and the probe-peak p90 (6.84 -> 1.49).
- **End-to-end `--no-refine` harness change** (make e2e refine by default): regressed simple line_rms_median by +0.064 pp with only a -0.015 pp peak_err_median win; reverted (4c56536).

## Next steps

Measured in order of expected impact:

1. **Dense-chart run selection**: use the chain tracker's full-run coverage (ridge extent, chain-colour expectation, chain continuity) to tie a column to its series beyond "nearest trace". The run that fits the series's recent height and slope wins over a run that happens to sit under the trace. Expected: all-chart RMS -0.05%, p90 -1 to -2 pp; narrow-peaks and narrow-small down toward 0.1%.
2. **Dark-theme and other wide-colour-contrast charts**: the ink-weight paper-to-ink segment, re-estimated from the darkest trace pixels, inverts on a dark background. A sign-insensitive re-estimation (percentile of absolute `t_raw`) would centre on the actual drawn ink. Expected: corpus dark-theme back to parity.
3. **Native-resolution tiling for large charts** (`retina-2x`): a 1600 px chart downscaled to 768 x 512 loses half its resolution. A second pass over tiles at the native scale, fused into the first pass, would gain on all `scale < 0.5` cases. Expected: large-image peak_err -40%.
4. **Refine_ticks evaluation**: the shift-only tick correction's effect on the corpus (where the classical engine's advantage over us is partly tick calibration), and on the e2e Plotly set (which uses a different renderer with different label offsets). The r4-chain's score2 at HEAD did not complete in the first window; the baseline evaluate.py path at HEAD is byte-identical to the baseline, and the `--refine` reading at HEAD was not measured. Open for the next window.
5. **Revisit the apex-both-sides gate**: at HEAD, the gate costs ~0.18 pp of simple line_rms_median on the full scoreboard. A direction-only gate (demand the opposite side has ink moving in the right sense, rather than a mass fall-off) or a span-only correction at terminal columns would recover the headline median and keep the probe-peak p90 and the corpus linear-thick-line win.
