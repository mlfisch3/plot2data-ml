# t3-precision: the failure catalogue

Curator's record of where the sub-pixel error comes from, measured on the v3 checkpoint (`runs/v3/best.pt`).
All pixel errors are in source pixels unless marked; "% ph" is a percentage of the plot height, the scoreboard's unit.
Every number here is reproducible from the scripts in `scripts/` and the probe sets under `data/t3-*` (generator `p2d/synth/probe_t3.py`).

How the records were made:

```sh
python teams/t3-precision/scripts/diag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --out out/t3/diag-base.pkl
python teams/t3-precision/scripts/diag_report.py out/t3/diag-base.pkl [--simple]       # per-column, per-peak, per-tick, per-frame tables
python teams/t3-precision/scripts/probe_report.py out/t3/diag-peaks.pkl                # per-factor tables for a probe set
python teams/t3-precision/scripts/corpus_diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt   # corpus: calibration versus trace
```

(Sections are filled in as the measurements land; see the dated entries in NOTES.md.)

Provenance: every "baseline" number below was measured with the contest-start code (commit 6b313e9).
The mpl-val and plotly-v1 collections ran from this worktree before any file under `p2d/` had been edited (pickles written 01:54 and 02:0x, the first live edit to `p2d/extract.py` was at 01:55:44 and the Plotly process had imported the module at 01:54:18); every later baseline run imports `p2d` from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` (`P2D_ROOT=... scripts/diag.py`).

## 0. The scoreboard baseline, reproduced here

`python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine` (this worktree, before any edit; `out/t3/base-refine.txt`): simple / all: line_rms_median 0.189 / 0.311 %, peak_err_median 0.307 / 1.77 %, xticks 0.30 / 0.29 px, yticks 0.35 / 0.32 px, frame median 1.39 / 1.47 px, p90 13.8 / 13.2 px.
Identical to the judge's `out/base/v3-pixel.txt`.

## 1. Lines: a few pixels on a tenth of the columns, not a fraction of a pixel everywhere

Source: `out/t3/report-base-simple.txt`, `out/t3/report-base-all.txt` (200 mpl-val charts; simple = 115 charts, 132 matched line series, 105,366 scored columns).

| columns (simple) | share of columns | share of squared error | bias (px) | median abs error (px) | kept from the network |
| --- | --- | --- | --- | --- | --- |
| all | 100% | 100% | +0.001 | 0.090 | 43.5% |
| within 3 px of the truth | 89.3% | 1.3% | -0.003 | 0.068 | |
| flat (abs slope < 0.5, > 3 columns from a vertex), within 3 px | 32% | 0.0% | +0.00 | 0.045 (0.023 where refined, 0.229 where kept from the net) | 28% |
| abs slope > 4 | 18% | 62.8% | -0.28 | 1.69 (p90 14.2) | 81% |
| abs slope 2 to 4 | 14% | 6.9% | +0.03 | 0.15 (p90 2.8) | 44% |
| within 1 column of a polyline vertex | 9% | 32.8% | -0.06 | 1.61 (p90 12.6) | 82% |
| 1 to 3 columns from a vertex | 12% | 20.4% | -0.05 | 0.86 (p90 9.3) | 82% |
| 3 to 8 columns from a vertex | 15% | 12.1% | -0.09 | 0.21 | 58% |
| more than 8 columns from a vertex | 48% | 7.4% | -0.06 | 0.05 | 28% |

Flat columns carry no bias by line width (0.5 to 6 px: +0.02 to -0.07 px), none by canvas scale (0.4 to 2.0: median 0.016 to 0.061 px), none by ink colour. Columns 1.5 to 3 px from a gridline are the one flat exception: median 0.18 px, 83% kept from the net.
A falling slope reads -0.05 px, a rising one +0.03 px (near-correct columns with abs slope > 0.5): a negligible lag.

Where `refine_lines` keeps the network's estimate (43.5% of columns on simple charts, 47% on all), and why (from the crops in `out/t3/cases/`, green truth, blue raw network, magenta refined):

- Low-contrast ink, `dd < 400`: the whole series is left to the network. `9000148` series 0, a 5 px teal line on lavender paper: flat columns wander by 1.5 px (RMS 0.157%, 100% kept).
- The ink run reaches the window edge (R = max(3, 2.5/s) + 4 rows): every steep flank, every thick line at small scale. `9000041` series 2 (highcharts, s = 0.39, slope 6.6): a 2 px offset along the whole flank, 67% kept.
- Dashes and gaps: no ink under the column, the network's centre line through the gap is 2 px off. `9000196` series 1 (plotly, dashed, s = 0.42): median 2.3 px over the worst 60 columns; `9000192` series 0 (5.8 px dashed line, spike): 1.0 px median, 98% kept.
- Vertex heat above 0.3 in the 3x3 canvas neighbourhood: up to 4 source px around every vertex at s = 0.4.

Oracle ceilings (`scripts/oracle.py out/t3/diag-base.pkl`), median per-series RMS in % ph, simple / all:

| if these columns were exact | simple | all |
| --- | --- | --- |
| nothing (as measured) | 0.189 | 0.311 |
| within 1 column of a vertex | 0.162 | 0.258 |
| within 3 columns of a vertex | 0.117 | 0.201 |
| within 8 columns of a vertex | 0.066 | 0.101 |
| abs slope > 4 | 0.096 | 0.181 |
| abs slope > 2 | 0.061 | 0.130 |
| the columns kept from the network | 0.039 | 0.072 |
| the gross columns (error > max(3, 2 lw) px) | 0.109 | 0.148 |
| every column with error > 1 px | 0.036 | 0.039 |

Worst series: the 23 worst simple series by RMS are all tracing failures (gross columns hold over 90% of their squared error); over all 132 matched simple series 49 are tracing-dominated and 83 precision-dominated, the latter with median RMS 0.081%.
The scoreboard median therefore sits on series whose RMS is made by a handful of gross columns at vertices, on flanks and in gaps, not by a sub-pixel bias.

## 2. Peaks: clipped by the network's own vertex estimate, which refinement never touches

916 scored turning points on simple charts (prominence at least 5% ph); "+" is inward (clipped).

| | median inward (px) | median abs (% ph) | clipped by > 1 px |
| --- | --- | --- | --- |
| all peaks, refined | +1.26 | 0.307 | 53% |
| all peaks, raw network | +1.25 | 0.307 | 53% |
| turning angle < 60 deg (blunt) | +0.05 to +0.12 | 0.07 to 0.16 | 9 to 18% |
| 90 to 120 deg | +2.14 | 0.47 | 58% |
| > 150 deg (needles) | +2.30 | 0.36 | 66% |
| canvas scale 1.0 (native) | -0.09 | 0.23 | 15% |
| scale 0.7 to 1 | +0.65 | 0.25 | 42% |
| scale 0.5 to 0.7 | +2.49 | 0.40 | 63% |
| scale < 0.5 | +2.54 | 0.42 | 68% |
| line width > 4 px | +3.58 | 0.59 | 63% |
| line width < 1.2 px | +0.53 | 0.09 | 35% |
| a vertex-head peak within 1 px of the tip (471 peaks) | +0.74 | 0.18 | 45% |
| nearest vertex peak 1 to 2 px | +2.34 | 0.43 | 60% |
| no vertex peak within 4 px (133) | +4.03 | 1.09 | 64% |

So: at native resolution the tips are right; the clipping is resolution loss on the 768 x 512 canvas (sigma 1.5 canvas px on the vertex heat is 3 to 4 source px at s = 0.4 to 0.5), and the vertex head's parabola estimate is short by 0.74 px even when it fires on the tip.
Overshoot by more than 1 px: 7% of peaks.
"All" split: median +3.7 px (1.77% ph), 64% clipped by > 1 px; 3,886 of 5,605 peaks are one-sample spikes of dense series (turning angle > 150 deg, median +8.4 px): the trace runs through the base of the spike. Probed by `data/t3-spikes`.

## 3. Ticks: the network is unbiased at 0.27 px; snapping to drawn marks adds +0.25 px; half the variance is a per-axis shift

1,970 labelled ticks on 200 charts.

| | x raw | x snapped (`refine_ticks`) | y raw | y snapped |
| --- | --- | --- | --- | --- |
| bias (px) | -0.02 | +0.21 | +0.10 | +0.28 |
| median abs (px) | 0.27 | 0.34 | 0.30 | 0.37 |
| p90 (px) | 0.76 | 0.86 | 0.78 | 0.89 |
| on the ticks that were snapped (73 to 76%) | 0.25 | 0.35 | 0.29 | 0.37 |

Why snapping is biased: matplotlib pixel-snaps tick marks and gridlines, the truth (and the data line) are not snapped. Snap error by the sub-pixel phase of the true position, x and y alike: fraction in [0, 0.25): +0.63 px (median abs 0.80); [0.25, 0.5): +0.46; [-0.25, 0): -0.02; [-0.5, -0.25): +0.22.
The raw network error carries a weaker version (+0.21 / -0.23 in the two central bins): it learned from the drawn marks.
Per axis: the mean error of one axis's ticks has a standard deviation of 0.34 px (x) / 0.46 px (y) across axes against a within-axis residual of 0.29 / 0.28 px, so half of the variance is a common shift per axis that least squares over the ticks cannot average away.
By what is drawn at the tick (raw): mark and grid 0.25 to 0.26 px; mark without grid 0.27 to 0.32; grid only 0.31 to 0.42; label only (no mark, no grid; n = 57 x, 47 y): bias +0.22 / +0.52 px, median 0.38 / 0.39, p90 0.85 / 1.25: the `nogrid` corpus case in miniature.
Scale: 0.21 px at s = 0.7 to 1, 0.36 to 0.38 at s < 0.5.

## 4. Frame: visible edges are fine; the hidden top edge is the whole p90

200/200 found in geometry mode (the end-to-end "frame_found 0.89" is `evaluate.py` replacing the extraction with an empty one when calibration fails, not the detector).

| edge | visible spine: n, bias, median abs, p90 (px) | hidden: n, bias, median abs, p90 |
| --- | --- | --- | --- |
| left | 78, +0.22, 0.37, 1.05 | 122, -0.46, 0.61, 3.26 |
| top | 49, +0.02, 0.37, 1.09 | 151, +5.23, 1.22, 13.21 |
| right | 49, -0.00, 0.37, 0.89 | 151, +0.01, 0.56, 2.39 |
| bottom | 141, -0.24, 0.42, 1.13 | 59, +1.63, 0.60, 6.87 |

All four spines visible (43 charts): max-corner error median 0.75 px, p90 1.75. Some hidden (157): median 2.11, p90 15.0.
The worst are spineless house styles where the corner heat lands on the first gridline below the true top: 9000023 highcharts +211 px, 9000049 +97, 9000133 excel +74, 9000036 news +67 (all with the top edge invisible).
A low top edge also truncates the series ROI (`extract` keeps ink within the frame plus 3 px).

Confirmed without the network (label maps and grey levels of mpl-val, 200 charts; tick-mark ink is the AXIS class in the band just outside the axis, gridline ink the GRID class across the plot):

| drawn ink, centroid minus true position | n | bias (px) | median abs | frac [-0.5,-0.25) | [-0.25,0) | [0,0.25) | [0.25,0.5) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| x tick marks (label map) | 722 | +0.23 | 0.32 | +0.13 | -0.12 | +0.59 | +0.37 |
| x tick marks (grey levels) | 662 | +0.29 | 0.35 | +0.19 | -0.05 | +0.63 | +0.44 |
| x gridlines | 380 | +0.28 | 0.32 | +0.21 | -0.02 | +0.63 | +0.37 |
| y tick marks (label map) | 620 | +0.30 | 0.33 | +0.19 | -0.06 | +0.69 | +0.39 |
| y gridlines | 569 | +0.31 | 0.37 | +0.24 | -0.06 | +0.64 | +0.43 |

So the ink of a matplotlib tick mark or gridline is pixel-snapped to a position +0.3 px (mean) from the true tick, by an amount that depends on the sub-pixel phase of the truth and reaches +0.7 px; `refine_ticks` measures that ink correctly (its +0.21 / +0.28 bias is the ink's) and the network's raw estimate, unbiased at 0.27 px median, is already at the floor set by this quantisation (a uniform error of width 1 px has median 0.25).
Consequence: on matplotlib the tick floor cannot be lowered by measuring marks or gridlines more carefully; it can only be lowered by a renderer-specific offset (here -0.3 px) or by fitting the data line's own registration.
What this does to a 400 px plot: 0.3 px is 0.075% of full scale, the size of the best corpus numbers; the corpus decomposition (section 6) says how much of each corpus error is this calibration offset.

## 5. Is the source-pixel refinement a loss? No: neutral on the median, and the lever is what it declines to measure

On the same 132 matched simple series (raw network trace versus refined, scored on the same columns): median per-series RMS raw 0.185% versus refined 0.183%; 24% of series end up worse, 5% by more than 0.02%; 10% better by more than 0.02%.
Refinement moves 56% of the columns; of those it improves 22% by more than 0.25 px (median 0.46 px -> 0.03 px) and worsens 4.5% by more than 0.25 px (median 0.34 -> 1.10 px: thick lines (43% have lw > 3 px), steep (36% have abs slope > 2), partial runs). The worsened columns are 2.5% of all columns and hold 0.6% of the squared error.
On "all" charts the median goes 0.295% -> 0.307%: the same picture with more dense series.
The 60-chart difference the brainstormer saw (0.146% without, 0.160% with) is the median of 34 series moving by one series; it is not a systematic loss, and `refine_markers` (0.077% -> 0.095% marker error) is a separate matter for team 4.

Per-series RMS by what the series is (simple / all, median % ph): solid lines 0.150 / 0.253 (84% of series, 93 to 95% of the squared error); dashed or dotted 0.238 / 0.467; plain `line` 0.146 / 0.239; `line+markers` 0.307 / 0.323; `area` 0.354 / 0.906; `step` 2.68 / 1.31 (vertical risers are scored at their midpoint and traced as steep runs).

Per-series RMS by canvas scale (simple): s < 0.5 (images wider than about 1,500 px) 0.068%; 0.5 to 0.7: 0.326%; 0.7 to 1: 0.208%; 1.0: 0.226%; s > 1 (small images, upscaled): 0.400%.
In the scoreboard's unit the large images are the best, not the worst: the pixel error grows with 1/s but the plot height grows faster. The resolution loss shows in the peaks (section 2: median inward 0.42% ph at s < 0.5 against 0.23% at s = 1) and in absolute pixels, which is what `retina-2x` on the corpus measures against a classical engine working at native resolution.

## A note on the peak metric (`metrics.peak_vertices`, not to be changed, but to be known)

An extremum of the drawn path is scored only when it stands out by 5% of the plot height against every point within 15 path points on each side; the comparison is against the window's extreme in the same direction, so two tips of similar height within 15 points of each other cancel and neither is scored.
A periodic wave with tips closer than 16 path points (the corpus `sawtooth-sharp`: 81 points, 15 teeth, 5.4 points per tooth) has no scored turning point under this definition, and a dense series with spikes every few samples scores none either, whatever the extraction does there.
The probe sets keep every tip at least 16 path points from its neighbours (collinear points along the flanks, which draw identically) so that the standard metric scores them; `corpus_diag.py` measures the sawtooth's tips with a prominence against the window's minimum instead.

## 6. The measurement rewrite: narrow-peaks regression and the fix

The brainstormer's `p2d/measure.py` (first version d3c4502) rewrote `refine_lines` to measure every column of a traced line on the source pixels and to recover vertices by flank fit and intersection.
The first version regressed on the corpus (series median 0.067% -> 0.085%, worst case narrow-peaks 0.211% -> 6.104%) and on scoreboard #5 (simple line_rms_median 0.189% -> 0.309%, all 0.311% -> 0.574%); commit 6db13c8 fixes three faults and the regression lands as a net gain on the scoreboard (preliminary iter_refine on `out/t3/cache-val60`: simple line_rms_median 0.160 -> 0.136, simple peak_err_median 0.298 -> 0.144, all peak_err_p90 7.082 -> 6.091).

Measurement from the pipeline (not from `measure.py` internals) on narrow-peaks, refine on, 200-sample grid in data space, truth from the corpus CSV, pre-fix (d3c4502+WIP) versus the base tree and the fixed tree:

| sample x (data) | truth | base pred (err) | pre-fix pred (err) | fixed pred (err) |
| --- | --- | --- | --- | --- |
| 1.0 (apex of spike 0) | 54.60 | 54.57 (-0.03) | 53.72 (-0.88) | 54.53 (-0.07) |
| 3.0 (apex of spike 1) | 59.80 | 59.04 (-0.76) | 58.01 (-1.79) | 59.80 (-0.00) |
| 5.0 (apex of spike 2) | 65.00 | 65.06 (+0.06) | 63.00 (-2.00) | 64.71 (-0.29) |
| 7.0 (apex of spike 3) | 70.20 | 70.28 (+0.08) | 70.15 (-0.05) | 70.15 (-0.05) |
| 9.0 (apex of spike 4) | 75.40 | 75.05 (-0.35) | 71.07 (-4.33) | 75.37 (-0.03) |
| 11.0 (apex of spike 5) | 80.60 | 80.14 (-0.46) | 74.47 (-6.13) | 79.64 (-0.96) |
| 2.5 (baseline between spikes) | 24.50 | 24.50 (-0.00) | 24.48 (-0.02) | 24.48 (-0.02) |

corpus_diag split on narrow-peaks: base rms 0.211% (calib 0.145 / trace 0.153, peaks in_p50 +0.19%); pre-fix 6.104% (calib 3.782 / trace 4.791, peaks in_p50 +1.90%); fixed 0.292% (calib 0.149 / trace 0.251, peaks in_p50 +0.06%: better than base at the tips, the residual lives in the first-sample flank climb where a one-pixel apex column cannot carry a continuous curve).

Three faults, documented so the pattern is remembered:

1. **The spike-triangle fill rewrote neighbour columns' values.** For a column that measured as a narrow apex (ink width at mid-height less than `2 t`), `measure.py` walked sideways to find the first "base" column on each side (span less than half the apex span) and reassigned every column in between the value `base + (tip - base) * max(0, 1 - |x - xv| / w_half)`. `w_half < 1 px` for a 1-pixel spike, so the formula collapsed to `base` for every column that was not the apex, erasing the flank columns' own centroids. The flank columns of an anti-aliased single-sample spike on matplotlib (4 to 5 columns wide at render time) hold the triangle's shape in their centroids; the fill replaced it with "baseline, apex, baseline".
2. **The occlusion test fired on butt-cap end columns.** `t_col[i] < 0.55 * t and |slope| < 2` marked a column as occluded (`clean = False`), and the `np.where(clean, cen, yc)` line fell those columns back to the network's trace (noise +-0.4 px). The first and last pixel columns of a straight stroke carry half the ink of an interior column (the butt cap is cut), so the test tripped at every segment end: `tests/test_measure::test_flat_line_centroid_and_stroke_width[1,2,4]` failed with first/last columns off by 0.25 px.
3. **The flank-fit intersection accepted lines that did not point towards the apex.** `_vertices` called `_fit_line` on each side of a candidate apex, accepted the intersection if the fits were straight (max residual below `0.3 + 0.05 |slope|`), and used `(a1 + b1 x, a2 + b2 x)` in the column override. Two flat flanks with the same gentle slope would fit well and intersect far from the apex, with both slopes pointing the same direction; the override then painted a long run of columns on the flat flank's value, which is the baseline at distance from an apex.

Fix in 6db13c8:
- Reverted `np.where(clean, cen, yc)` to `np.where(have, cen, yc)` so a column with any run (butt caps included) keeps its centroid.
- Gated the occlusion test: fires only when at least one neighbour within 2 columns on each side has mass at least 0.85 * t (both sides really covered, not an end), and the threshold tightened to 0.4 * t.
- Added a sign test on the flank fits (b1 and b2 point towards the apex direction) before using their intersection, with the apex direction given by `turn[k]`.
- Deleted the spike-triangle fill block. The apex column's own centroid, with the inserted vertex at `(xs[k] + dx, values[k])` and the vertex clustering by apex direction, gives the recovery: for a 1-pixel spike on narrow-peaks the apex column holds the ink centroid of the stroke's top row, the vertex drops in at that `x` with `y = top + t/2` (the classical turn rule), and the flank columns carry the shape with their own centroids.

Overlay at `out/t3/cases/narrow-peaks-broken.png` (3 x 6 panels, pre-fix: truth, base, pre-fix live, at 4x zoom on each spike) and `out/t3/cases/narrow-peaks-overlay.png` (same, fixed in the LIVE row).


## 7. Scoreboard, probes and corpus at the submission HEAD 9b82fba (replacement curator, 28 Oct 2026 20:30 EDT)

Merge target per judge: 8053952 (pre-apex-both-sides). 9b82fba stands as the declared submission on team/t3-precision for history.

Clean re-measure of the full scoreboard at HEAD 9b82fba (the submission commit), after the chain was killed at 17:28 EDT and the usage window reset. All GPU work serialised through `/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`.
Sources: `out/t3/r4-score5.txt` (geometry), `out/t3/r4-peaks.txt` (probe peaks), `out/t3/r4-spikes.txt` (probe spikes), `out/t3/r4-corpus.txt` (corpus).
The e2e `#1` and `#2` scoreboards against 9b82fba did not complete inside the first window and are not re-run here; the harness was reverted in 4c56536 so the e2e CLI is byte-identical to the baseline without `--refine`, and the baseline numbers hold on that path.

### 7.1 Scoreboard #5: the apex-both-sides commit regresses the full 200-chart set

Measured at HEAD 9b82fba with `--refine`; compared with the frozen baseline (`out/t3/base-refine.txt`) and the previous commit 8053952 (`out/t3/r3-score5.txt`).

| metric (simple / all) | base (`refine_lines_v1`) | 8053952 | 9b82fba (SUBMISSION) | delta HEAD vs base |
| --- | --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 | **0.136** / 0.323 | 0.312 / 0.502 | **+0.123 (+65%)** / +0.191 (+61%) |
| line_rms_mean_pct | 0.575 / 0.883 | 0.653 / 1.041 | 1.183 / 1.407 | +0.608 / +0.524 |
| line_rms_p90_pct | 1.377 / 2.231 | 1.674 / 2.603 | 3.503 / 3.583 | +2.126 / +1.352 |
| peak_err_median_pct | 0.307 / 1.766 | **0.276** / 1.778 | 0.327 / 1.972 | +0.020 (+7%) / +0.206 (+12%) |
| peak_err_p90_pct | 3.006 / 12.476 | **2.635** / **11.973** | 3.403 / 12.838 | +0.397 (+13%) / +0.362 (+3%) |
| line_found | 0.886 / 0.757 | 0.893 / 0.777 | 0.893 / 0.768 | +0.007 / +0.011 |
| line_cov_mean | 0.815 / 0.667 | 0.828 / 0.687 | 0.827 / 0.679 | +0.012 / +0.012 |
| line_good_cov_mean | 0.764 / 0.588 | 0.772 / 0.603 | 0.731 / 0.572 | -0.033 / -0.016 |

Reading: 8053952 was the winning snapshot (-28% simple RMS, -10% peak_err_median, -12% peak_err_p90). The two commits that followed, 4b3b172 (an apex demands ink falling away on BOTH sides) and 4c56536 (harness revert, pure evaluate.py), moved the full 200-chart simple RMS from 0.136% to 0.312% (+130% on the pre-apex-both-sides tree, +65% versus the baseline). The brainstormer's local iter_refine on `out/t3/cache-val60` reported the opposite at 4b3b172 (simple RMS 0.112 -> 0.089, -21%): the 60-chart cache is heavy on narrow and sharp cases where the both-sides gate is correct; it under-samples the long-tail of lines that run into the plot edge and have a legitimate one-sided apex at the final column (see 7.4).

### 7.2 Probe peaks (240 charts; `out/t3/r4-peaks.txt`, `out/t3/base-peaks.txt`)

Isolated turning-point probes (one-series polyline, prominence 5 to 50% of plot height, angles 10 to 90 degrees, line widths 1 to 5 px, round and mitred joins, source widths 400 to 1800 px).

| metric (simple / all) | base | 9b82fba (SUBMISSION) | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.221 / 0.317 | 0.218 / 0.433 | -0.003 / +0.116 (+37%) |
| line_rms_p90_pct | 1.484 / 4.574 | 2.071 / 4.395 | +0.587 (+40%) / -0.180 |
| peak_err_median_pct | 0.213 / 0.213 | **0.204** / **0.204** | **-0.010 (-5%)** |
| peak_err_p90_pct | 6.841 / 6.841 | **1.487** / **1.487** | **-5.354 (-78%)** |
| line_cov_mean | 0.938 / 0.928 | 0.981 / 0.968 | +0.043 / +0.040 |
| line_good_cov_mean | 0.884 / 0.770 | 0.923 / 0.815 | +0.039 / +0.045 |

Reading: the probe set that the measurement rewrite targets shows a decisive peak_err_p90 win (6.84 -> 1.49, -78%). Flank-fit intersection and classical turn placement reclaim the probe's hardest vertices. Line RMS on the "all" set regresses by +37% in median, the same mechanism as the full scoreboard (false-apex suppression on edge columns).

### 7.3 Probe spikes (160 charts; `out/t3/r4-spikes.txt`, `out/t3/base-spikes.txt`)

Dense spike probes (narrow single-sample tips every 2 to 8 points, flanks 1 to 3 columns wide, round and mitred joins). The baseline could not score most tips (prominence met the metric's floor but the trace clipped them).

| metric (simple / all) | base | 9b82fba (SUBMISSION) | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 1.629 / 3.575 | 1.665 / 3.875 | +0.036 / +0.300 |
| line_rms_p90_pct | 6.522 / 11.298 | 7.402 / 14.743 | +0.880 / +3.445 |
| peak_err_median_pct | 5.784 / 3.831 | **0.194** / 1.099 | **-5.590 (-97%)** / **-2.732 (-71%)** |
| peak_err_p90_pct | 31.441 / 33.411 | 27.482 / 31.580 | -3.959 (-13%) / -1.831 |

Reading: a 97% drop in simple peak_err_median (5.78 -> 0.19 %ph) on the dense-spike probe set. The classical `top + t/2` turn placement reads the apex from the ink's outer edge where the network's blurred vertex head cannot; this is exactly what the measurement rewrite was built for. The line_rms_p90 "all" set is worse (+30%) because the dense-crossing families defeat the per-column nearest-trace run selection; this is the open regression noted in `NOTES.md` under "dense-chart run selection".

### 7.4 Why 60-cache iter_refine said "win" while 200-chart said "lose" at 9b82fba

The brainstormer's `scripts/iter_refine.py --cache out/t3/cache-val60` reads 60 charts the predecessor filtered as "iterable" (every chart has at least one scored peak and a reasonable baseline RMS; selection favoured charts with narrow sampled peaks visible at least 2 columns from the plot edge). On that cache the apex-both-sides change dropped simple RMS from 0.112 to 0.089 (-21%).

The full 200-chart mpl-val is harsher: it contains lines that start or end at the plot's data edge (plot area or data range endpoint) where the natural apex of a line sits on the final column with ink only on one side.
Before 4b3b172, `sided = lambda v: np.inf if v == -np.inf else v` let a one-sided apex still count (the minimum of (inf, measured_side) is the measured side), so the final column got the classical `top + t/2` correction, which is the right answer there.
After 4b3b172, the one-sided side maps to 0 and `peak = 0`, so the column silently falls back to the ink centroid (biased by t/2 inward of the true apex position by half a stroke).
In a chart with ~500 columns and ~495 near-zero errors, three to five mispositioned terminal columns dominate the per-chart RMS: 0.1 pct ph is "0.5 px on a 500-px plot", one terminal column off by 2 px (one stroke of a 2 px line) is 0.4 %ph before averaging.

The 60-cache's selection filter dropped exactly these cases. iter_refine's signal at 4b3b172 is a sampling artefact.

### 7.5 Corpus at HEAD 9b82fba (`out/t3/r4-corpus.txt`)

Clean reading matching the brainstormer's local 9b82fba run (series median 0.085%; same wins and losses).

| case | base v3-corpus.txt | 9b82fba | delta |
| --- | --- | --- | --- |
| **log-log** | 1.326 | **0.759** | **-43%** |
| log-y | 0.170 | 0.117 | -31% |
| **linear-dashed** | 0.067 | **0.032** | **-52%** |
| linear-thick-line | 0.042 | 0.029 | -31% (apex-end gate) |
| sawtooth-sharp | 0.268 | 0.220 | -18% |
| linear-single-solid | 0.033 | 0.029 | -12% |
| jpeg-compressed | 0.034 | 0.027 | -21% |
| retina-2x | 0.109 | 0.102 | -6% |
| scatter-markers | 0.060 | 0.062 | +3% |
| linear-single-nogrid | 0.194 | 0.199 | +3% |
| narrow-peaks | 0.211 | 0.292 | +39% |
| narrow-small | 0.066 | 0.144 | +118% |
| dark-theme (2 series) | 0.047 / 0.017 | 0.088 / 0.085 | +87% / +400% |
| offset-annotation | 61.222 | 61.222 | unchanged (unrelated) |
| series median | 0.067 | 0.085 | +27% |

### 7.6 Summary at the submission state

The submission at HEAD 9b82fba is net-mixed, not the net-win the REPORT draft describes:

- Scoreboard #5 (headline): regresses on simple and all RMS, modestly worse on peak_err. The win measured at 8053952 did not survive 4b3b172.
- Probe peaks: a -78% peak_err_p90 win, decisive on the targeted vertex metric.
- Probe spikes: a -97% peak_err_median win, decisive on dense-spike tips.
- Corpus: four double-digit wins (log-log, log-y, linear-dashed, sawtooth-sharp, linear-thick-line), four double-digit losses (narrow-peaks, narrow-small, dark-theme, dense tails); series median rises 0.067 -> 0.085.

A judge measuring the submission at HEAD will see the regression on scoreboard #5 and the wins on the probes and the four corpus wins; the full picture is in the probe-level data, not in the scoreboard median alone. The 8053952 commit (`t3: use the trace's slope in the merged-run and occlusion tests`) is the strongest headline-metric commit in the branch; 9b82fba adds the apex-end gate which trades scoreboard-median accuracy for probe-peak accuracy.
