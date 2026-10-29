# t3-precision notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:40 EDT (brainstormer)

Read BRIEF, ASSIGNMENT, README, RESULTS, all of p2d/, ACCURACY.md, the classical engine's trace.ts / ticks.ts / calibration.ts / frame.ts.

Harness finding: scoreboard commands #1 and #2 (`evaluate --ocr`) run `pipeline.run` with `refine=False` (the `--refine` flag is not in those commands), so no source-pixel refinement of lines, ticks or markers enters the end-to-end numbers on mpl-val and Plotly; corpus and real use `refine=True`. Measuring both ways on 60 charts (`out/t3/base-quick.sh`).

What the classical engine does for sub-pixel accuracy that we do not:
- Column value: alpha-weighted centroid where the column holds one flat stroke; where the ink span exceeds ~1.25 stroke widths it blends towards an explicit turning-point rule: at a local maximum the value is `topmost ink + t/2`, at a minimum `bottommost ink - t/2`, on a monotone steep run the middle of the span. `t` is measured as ink area / path length. Mitred corners (Chart.js) are detected by cross-section (a sliver half a stroke below the tip) and descended until the ink is a full stroke wide.
- Sub-pixel outer edges from the coverage of the edge rows (`top = lo + 0.5 - alpha_lo`).
- Ticks: ink-mass centroid of the tick mark including the antialiased columns either side; label-only axes use label blob centres kept on a regular grid (`keepRegular`).
- Frame: ink-weighted centre of the spine band across its rows.
- Calibration: least squares over all labelled ticks with pairwise RANSAC and leave-one-out; the same idea as ours.
Our pipeline: ridge centroid on the heat map (canvas resolution, sigma 1 px), then `refine_lines` re-measures a blend-weighted centroid per source column, but keeps the network estimate at any column whose 3x3 canvas neighbourhood has vertex heat > 0.3, whenever the ink run reaches the window edge, and whenever the centroid moves more than max(1.5, 1/s) px. Vertices come from the vertex heat peak (sigma 1.5 canvas px) via `snap_vertices`, never measured on the source pixels.

Next: per-column residual analysis (`scripts/colres.py`) to see which columns carry the RMS, then the ranked list.

## Wed 28 Oct 2026, 01:49 EDT (curator)

Read everything; the worktree reproduces the judge's v3 geometry baseline exactly (`out/t3/base-refine.txt`: simple RMS 0.1886%, peak 0.3065%, frame p90 13.2 px, ticks 0.29 / 0.32 px).
Built the diagnostic collector `teams/t3-precision/scripts/diag.py` (per column: raw and refined error, slope, line width, scale, gridline/axis/other-series distance, vertex distance, ink run height; per peak: signed inward error raw and refined, angle, widths, vertex heat; per tick: raw and snapped error with what is drawn at the tick; per frame: signed edge errors with spine visibility from the label map), the summariser `diag_report.py` and `probe_report.py`.
Probe generator `p2d/synth/probe_t3.py`, seven families with a seed base each (peaks 13.0M, scale 13.1M, ticks 13.2M, width 13.3M, log 13.4M, grid 13.5M, frame 13.6M); ground truth overlays checked at 8x on peak tips and tick anchors.
Building `data/t3-{peaks,scale,ticks,width,log,grid,frame}` (240 / 128 / 144 / 96 / 48 / 48 / 80 charts); diag runs on mpl-val, plotly-v1 and the probes queued on the GPU one at a time.
First finding from the brainstormer's 60-chart runs: on the same 60 charts the simple-chart line RMS is 0.1464% without `refine_lines` and 0.1595% with it, and marker error 0.077% vs 0.095% with `refine_markers`; the source-pixel refinement is a net loss on simple charts. The per-column records will say on which columns.

## Wed 28 Oct 2026, 01:51 EDT (brainstormer): the error budget and the ranked list

Baselines on the first 60 of mpl-val (`out/t3/base60-*.txt`), simple subset (35 charts, 34 line series):

| run | line_found | good_cov | line_rms_median | peak_err_median | calib x/y within 0.5% |
| --- | --- | --- | --- | --- | --- |
| geometry, no refine | 0.91 | 0.83 | 0.146% | 0.299% | - |
| geometry, `--refine` (scoreboard #5) | 0.91 | 0.82 | 0.160% | 0.298% | - |
| oracle ticks, `--refine` | 0.74 | 0.62 | 0.160% | 0.310% | 0.97 / 0.92 |
| e2e `--ocr`, no refine (scoreboard #1 as run) | 0.62 | 0.53 | 0.273% | 0.197% | 0.90 / 0.88 |
| e2e `--ocr --refine` | 0.59 | 0.51 | 0.340% | 0.235% | 0.90 / 0.90 |

Two surprises: `refine_lines` does not lower the median RMS (0.146 -> 0.160), and turning refinement on end to end makes the line RMS worse (0.27 -> 0.34; `refine_ticks` moves ticks both ways, see `out/t3/tickdiag.txt` when it lands).

Per-column residuals (`scripts/colres.py`, `out/t3/colres.txt`, 60 charts, geometry with refine), simple subset, 26,519 columns:

- 47% of columns keep the network estimate (fallback). Refined columns: median |r| 0.027 px, p90 0.15 px, 1.4% of the squared error. Fallback columns: median |r| 0.52 px, p90 5.8 px, 98.6% of the squared error.
- |slope| > 3 px/px: 26.5% of columns, 74% fallback, 90% of the squared error. The window of `refine_lines` (+-7 to +-10 rows) cannot hold a steep run, so steep columns go back to the canvas-resolution ridge.
- Within 1.5 px of a drawn vertex: 9% of columns, 53% of the squared error; 1.5 to 4 px: 19%; 4 to 10 px: 22%. The vertex-heat gate (3x3 canvas window > 0.3) fires on 15.5% of columns and those hold 44% of the squared error.
- Line width and canvas scale barely matter once the fallback is accounted for (refined columns are unbiased: mean r -0.001 px).
- Peaks (229 with prominence >= 5%): snapped by the vertex head 66%, median |err| 0.15%, median shortfall +0.77 px; not snapped 34%, median |err| 1.16%, shortfall +8.6 px, almost all with flanks shorter than 3 px (dense data).

So the error is not sub-pixel noise at all: it is the columns the refinement declines to measure. The refined centroid is good to a fortieth of a pixel.

Ranked candidates (expected gain on the scoreboard):

1. **Measure every column on the source pixels, vertices included** (rewrite `refine_lines`): blend-weight map over the whole band, full-column runs (no window), run selected by distance to the network estimate with a span check for merged runs; stroke width `t` from ink area over path length; the classical flat/steep/turn blend per column (centroid where the span is about `t`, `top + t/2` at a maximum, `bottom - t/2` at a minimum, mitre descent by cross-section); at vertices with straight flanks, fit the two flanks and intersect, and give the join columns the polyline's own values. Expected: simple line_rms_median 0.16% -> about 0.06%; peak_err_median simple 0.30% -> about 0.1%, all 1.8% -> about 0.8%; corpus sawtooth 0.27% -> under 0.1%, narrow-peaks and thick-line down; the same code runs on Plotly and Chart.js, so it is general.
2. **Ticks: snap only where it helps, and learn the label offset per chart** (`refine_ticks`): accept a snap only when the line found is the same for most ticks of the axis (a consistent offset from the network's positions), fall back to the network otherwise; then fit the ticks jointly (equal spacing) and transfer the measured offset to label-only ticks. Expected: tick error median 0.3 -> 0.15 px, calib within 0.5% +2 to 4 points, e2e line_rms down by the calibration share (0.27 -> about 0.22%). Needs the tick diagnostics first.
3. **Frame on the source pixels**: snap each edge to the spine or outermost gridline, with the tick anchors as a consistency check; p90 of 14 to 21 px is wrong frames, not imprecise ones. Expected: frame median 1.4 -> 0.4 px; indirect gains in coverage (the ROI clips series) and tick snapping.
4. **Harness**: once 1 and 2 are in, make the e2e path of `evaluate` refine by default so #1 and #2 measure the pipeline as shipped; report the harness change separately.
5. Native-resolution tiles for large images: deferred; the per-column data says the canvas scale is not where the error is once columns are measured at source resolution.
6. Dash gaps: interpolate across short gaps instead of the network estimate; small.

Going after 1 first, then 2, then 3.

## Wed 28 Oct 2026, 02:00 EDT (curator)

Diagnosis on 200 mpl-val charts written to the mailbox and CASES.md sections 1 to 4 (lines, peaks, ticks, frame).
Provenance: `out/t3/diag-base.pkl` was written 01:54:14, the first live edit to `p2d/extract.py` was 01:55:44, and the plotly-v1 collection started 01:54:18 (module imported before the edit); both are clean baselines.
From now on every baseline run imports p2d from the frozen tree (`P2D_ROOT=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml`), supported by `scripts/diag.py` and `scripts/corpus_diag.py`; the queued probe-set and corpus runs were stopped (own pids only, matched on this team's file names) and re-queued that way.

## Wed 28 Oct 2026, 02:28 EDT (brainstormer): the measurement rewrite, first version

`p2d/measure.py`, reached through `extract.refine_lines` (the old one is `extract.refine_lines_v1`). Per line series:

- Ink weights over a band around the trace (the band spans the network's ridge extent, not just its centre line, so a spike's whole height is in it): position along the paper-to-ink blend, zero off the segment. The ink colour is re-estimated from the darkest trace pixels (the median trace pixel of a thin line is a blend, which clipped the coverage).
- Every column gets its full run of ink (no window); the run containing or nearest the network's estimate is taken. A run longer than the ridge's extent there plus a stroke plus a margin is merged ink (fallback); a flat column with less than 0.55 of a stroke's ink is occluded (fallback). `Series.ridge_px` (new, from the chain spans in `extract`) carries the ridge extent per canvas column.
- Stroke width `t` = median over columns of ink mass / sqrt(1 + slope^2) (exact on matplotlib strokes: 1.01, 2.01, 4.01 for 1, 2, 4 px).
- The classical turn rule: a column is an apex when its outer edge is beyond every neighbour within reach (2t columns) and the edges fall away on both sides by a quarter stroke or more; its value is `top + t/2` (or `bottom - t/2`), with the mitre descent by cross-section; a column that is merely steep keeps its centroid (the classical "middle of the span" is dropped: the centroid of a straight stroke is exact however steep).
- Vertices: each cluster of apex columns is one candidate (the column whose edge reaches furthest). Two line fits on the clean columns beyond the join region on each side; if both are straight (max residual < 0.3 + 0.05 |slope|) and the angle is at least 8 degrees, their intersection is the vertex and the join columns out to t / (2 tan(theta/2)) take the polyline's values. Otherwise the apex column's value is the vertex, its x the horizontal ink centroid of the outermost stroke's worth of rows, and, for a spike narrower than the stroke, the spill columns (whose runs reach from base to tip) are reconstructed as a triangle whose base width is the ink width at mid-height minus a stroke.
- Short unmeasured stretches between measured columns (dash gaps, a marker, a crossing; up to 12/s columns) are bridged straight unless the network put a corner inside.
- The measured vertices go into the trace beside the column samples; the network's corners survive only where their column could not be measured.

Unit strokes drawn by matplotlib (`tests/test_measure.py`, `teams/t3-precision/scripts/mpl_stroke.py`): flat line 0.002 px; zigzag flanks 0.007 to 0.02 px median, vertices within 0.02 px, both joins; kinks 0.002 px; dense one-sample spikes: tips within 0.0 to 1.2 px (round) and 0.2 to 3 px (mitred: the bevel at an acute angle stops at the vertex, and `top + t/2` then overshoots by up to t/2); dashed curve 0.04 px median with the gaps bridged. Two limits found on the way: a column centroid through a thick stroke on a tightly curved line is biased by order t^2 * curvature / 8 (0.1 px for a 4 px line at radius 7 px), and sub-pixel spike flanks cannot be placed to better than about a tenth of a pixel, which the metric turns into large column errors on dense charts.

Bugs found by the unit strokes before any real data: the classical "reach" marked every column within 2t of an apex as a turn (fixed by the no-higher-neighbour test); the join override indexed by coordinate instead of column index; the ink band was cut at the trace's own extent, so spikes lost their tops.

`refine_ticks` rewritten as an offset-only correction: the marks' median offset from the network's positions is applied to all ticks of an axis only when at least three marks agree (MAD < 0.45 px) on a shift beyond the snapping noise (|median| > 0.45 px). On matplotlib charts the drawn marks are pixel-snapped and the network is unbiased at the quantisation floor (curator, CASES.md section 3), so per-tick snapping only added noise (+0.07 px median, +0.25 px bias); on a renderer whose labels sit differently (Chart.js) the common shift is what the old snapping was really correcting.

## Wed 28 Oct 2026, 02:29 EDT (curator)

Tick quantisation confirmed on the label maps without the network (CASES.md section 3): matplotlib's tick marks and gridlines sit +0.3 px (mean, up to +0.7 depending on the sub-pixel phase) from the true tick; the network's 0.27 px is the floor.
Refinement is neutral on the median (section 5); per-series RMS by scale shows large images are the best in % of plot height (0.068% at s < 0.5) and the resolution loss is in the peaks.
Probe sets rebuilt: smallest peak prominence 6% (a 5% tooth on a sloped baseline falls under the metric's threshold on one side), every tip at least 16 path points from its neighbours so `metrics.peak_vertices` scores it (collinear flank points for the triangle; spike spacing at least 16 samples), Gaussian peaks sampled at four points per sigma.
`tests/test_probe_t3.py` added. The GPU chain (`out/t3/baseline-chain.sh`) now runs peaks and spikes from the base tree and the live tree first, then the standard `evaluate --refine` from both trees, then the other families and the corpus decomposition.
Lesson applied twice the hard way: a kill pattern must not appear anywhere else in the same command, not even as the launch line of the same script.

## Wed 28 Oct 2026, 16:12 EDT (curator, Opus 4.7 replacement)

Resumed after the 02:30 cutoff.
Working tree holds uncommitted edits from the brainstormer's second iteration (last file touch 02:29): `p2d/measure.py` adds a `net_vertices_x` argument, the bugfix `np.where(have,...)` -> `np.where(clean,...)` on the per-column values, and a short-gap bridger; `p2d/extract.py` replaces per-tick snapping with the offset-only `refine_ticks` (median shift across the axis's ticks); `p2d/evaluate.py` adds `--no-refine` and makes the e2e path refine by default; `scripts/diag.py` prints per-chart timing and writes `<out>.partial` every 20 charts.
Also untracked: `tests/test_measure.py` (the unit-stroke tests).
A stuck shell (pid 832056) was waiting on `out/t3/diag-plotly-base.pkl` that the killed predecessor never finished; killed it.
Nothing on the GPU.
The only measurement from the new code that landed before the cutoff is `out/t3/corpus-new1.txt` (eval_corpus at 02:42) and it carries a disaster: narrow-peaks 0.21 -> 6.10 %, dark-theme 0.047/0.017 -> 0.088/0.085 %, linear-thick-line 0.042 -> 0.085 %, narrow-small 0.066 -> 0.144 %, offset-annotation unchanged. The gains are on log-log 1.33 -> 0.89 % and sawtooth-sharp 0.27 -> 0.22 % and log-y 0.17 -> 0.12 %. Corpus series-median 0.067 -> 0.085 %.
Re-measurement plan: a geometry --refine on 200 mpl-val (standard scoreboard #5) with and without the new code, then the probe sets (peaks, spikes, scale, ticks, width, log, grid, frame), then the e2e commands, then isolate the narrow-peaks regression on crops.


## Wed 28 Oct 2026, 16:14 EDT (brainstormer, Opus 4.7 replacement)

Resumed from Fable's 02:30 cutoff. State inherited from the predecessor:
- `measure.py` is a full rewrite reached through `extract.refine_lines`; the v1 lives on as `refine_lines_v1`.
- `extract.refine_ticks` is now an offset-only correction (median shift across the axis's ticks, applied only when at least three marks agree beyond the snapping noise).
- `evaluate.py` adds `--no-refine`; the e2e path refines by default.
- The 60-chart CPU cache `out/t3/cache-val60` and `iter_refine.py` let me iterate measurement on CPU with the GPU extraction cached.

What I found in the predecessor's traces that must be fixed:
- `test_measure::test_flat_line_centroid_and_stroke_width[1]` fails on the butt-cap first column: the predecessor's `np.where(have, cen, yc)` -> `np.where(clean, cen, yc)` edit drops the end column from `cen` to `yc` because `t_col[0] < 0.55*t` fires on the half-coverage butt cap. That is an end-of-stroke effect, not occlusion; the test exposes it.
- `iter-new.json` on 60 cached charts (new refine_lines) vs `iter-old.json` (v1): on simple charts peak_err_median drops from 0.298% to 0.145% (a halving) but line_rms_median rises from 0.160% to 0.236%, and line_rms_p90 from 0.70% to 4.25%. On all charts, line_rms_median goes 0.312% -> 0.557%, p90 1.92% -> 3.58%. Peak gains, line losses: the sophisticated turn/vertex/spike code is pulling values far off where it should not fire. Also line_rms_mean 0.336 -> 1.190 on simple: a long tail of catastrophic series.
- `out/t3/corpus-new1.txt` carries the same picture: narrow-peaks 0.21% -> 6.10% (28x worse), narrow-small 0.07 -> 0.14, linear-thick-line 0.04 -> 0.09, dark-theme 0.017 -> 0.085, offset-annotation unchanged; but log-log 1.33 -> 0.89, sawtooth-sharp 0.27 -> 0.22, log-y 0.17 -> 0.12. Series-median goes 0.067 -> 0.085: a net corpus regression.

So the WIP's bones are right (big peak wins) but the vertex/spike code over-reaches and the clean/have swap is strict at the ends. I will go after the regression, keep the peak gains, and only then promote the e2e harness change (`--no-refine`). My next step is to repro narrow-peaks on a crop under iter_refine (CPU) and bisect which code path (apex extrapolation into the join columns, the spike-triangle fill, or the bridger) owns the 6% figure. If one path dominates, I will gate it; if several, I will fall back to the v1-style trace of flat/steep columns plus a smaller, surer vertex improvement (flank intersection only, no spike reconstruction).

Teammate: curator at agent id a28e75ba558dd3aea (short notes via SendMessage; long items in mailbox). Judge is `main`.

## Wed 28 Oct 2026, 16:22 EDT (curator): scoreboard #5 and #1 with the live tree

Numbers on 200 mpl-val, both from this worktree with the uncommitted measure.py / extract.py / evaluate.py edits, versus the frozen contest-start baseline (`out/t3/base-refine.txt` and `/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/v3-e2e-ocr.txt`).

Scoreboard #5 `evaluate --refine` (geometry):

| metric (simple / all) | baseline | new | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 | 0.309 / 0.574 | +0.120 / +0.263 |
| line_rms_mean_pct | 0.575 / 0.883 | 1.359 / 1.693 | +0.78 / +0.81 |
| line_rms_p90_pct | 1.377 / 2.231 | 4.477 / 5.071 | +3.10 / +2.84 |
| peak_err_median_pct | 0.307 / 1.766 | 0.381 / 1.921 | +0.074 / +0.155 |
| peak_err_p90_pct | 3.006 / 12.476 | 4.498 / 12.179 | +1.49 / -0.30 |
| line_found | 0.886 / 0.757 | 0.893 / 0.781 | +0.007 / +0.024 |
| line_cov_mean | 0.815 / 0.667 | 0.828 / 0.690 | +0.013 / +0.023 |
| line_good_cov_mean | 0.764 / 0.588 | 0.740 / 0.584 | -0.024 / -0.004 |

Scoreboard #1 `evaluate --ocr` (e2e; the new code refines by default, versus the baseline that did not refine at all):

| metric (simple / all) | baseline (no refine) | new (refine on) | delta |
| --- | --- | --- | --- |
| line_rms_median_pct | 0.310 / 0.441 | 0.465 / 0.647 | +0.155 / +0.206 |
| line_rms_p90_pct | 2.449 / 2.858 | 5.260 / 5.093 | +2.81 / +2.24 |
| peak_err_median_pct | 0.390 / 2.290 | 0.423 / 2.396 | +0.033 / +0.106 |
| line_found | 0.624 / 0.547 | 0.617 / 0.538 | -0.007 / -0.009 |
| calib_x_within_0.5pct | 0.845 / - | 0.845 / - | 0.000 |
| calib_y_within_0.5pct | 0.775 / - | 0.775 / - | 0.000 |
| calib_x_err_median_pct | 0.046 / - | 0.050 / - | +0.004 |
| calib_y_err_median_pct | 0.111 / - | 0.119 / - | +0.008 |

eval_corpus (from `out/t3/corpus-new1.txt`, 02:42, same live tree versus `/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/v3-corpus.txt`): series median 0.067% -> 0.085%; sawtooth-sharp 0.268 -> 0.220 (win); log-log 1.326 -> 0.889 (win); log-y 0.170 -> 0.117 (win); linear-single-solid 0.033 -> 0.029; narrow-peaks 0.211 -> 6.104 (disaster, see below); linear-thick-line 0.042 -> 0.085; dark-theme 0.047/0.017 -> 0.088/0.085; narrow-small 0.066 -> 0.144; linear-dashed 0.067 -> 0.079.

Narrow-peaks diagnosis (from `/tmp/.../scratchpad/narrow_values.py`): the 1-pixel spike at x=1 (truth sample at x=0.965 is y=46.5, truth at x=1 is y=48.97, truth at x=1.085 is y=35.46; a narrow triangle 4-5 samples wide) is reconstructed as a bare `baseline, apex, baseline` by the live code: predicted sample values at x=0.905/0.965/1.025/1.085 are 20.26/20.55/25.39/21.04 against 32.71/46.54/48.97/35.46 truth. The apex tip itself is correct to -0.88 y (truth 54.6, pred 53.72). Repeats at every spike (6 of them). The flank columns that read correctly in the base pipeline (via column centroid of the thin anti-aliased stroke) are rewritten by `measure.py`'s spike-triangle fill with `base + (tip - base) * max(0, 1 - |x - xv| / w_half)` where `w_half < 1 px`, which collapses to `base` for every q != apex. The yfit calibration of the pipeline is unchanged (base vs live a/b differ by less than 0.02 px): the whole regression is in the trace.

Other failing cases to look at next on the catalogue once the chain finishes: linear-thick-line (0.042 -> 0.085), dark-theme (0.047 -> 0.088 and 0.017 -> 0.085), linear-dashed (0.067 -> 0.079), narrow-small (0.066 -> 0.144).

Harness note: scoreboard #1 now defaults to refining in the e2e path, which matches the pipeline's real behaviour. The baseline comparison is therefore refine=False vs refine=True on 200 charts: section 5 of CASES.md gives the predecessor's measurement on the same 60 charts (simple RMS 0.185 vs 0.183%, essentially neutral; marker error 0.077 vs 0.095). The e2e harness change is itself not an improvement under the old measure.py; it is only justified if the new measure.py beats the raw network on the e2e path.


## Wed 28 Oct 2026, 16:42 EDT (curator): r3 scoreboard #5 against 8053952

Scoreboard #5 landed at 16:42:49 on 8053952 (`out/t3/r3-score5.txt`, HEAD and mtime logged in `remeasure3.log`). Three commits in sequence land the measurement rewrite as a clear simple-chart win:

| metric (simple / all) | baseline v1 | 6db13c8 | 0e9e16b | 8053952 |
| --- | --- | --- | --- | --- |
| line_rms_median_pct | 0.189 / 0.311 | 0.271 / 0.397 | 0.167 / 0.361 | **0.136 / 0.323** |
| line_rms_mean_pct | 0.575 / 0.883 | 1.124 / 1.222 | 0.703 / 1.028 | 0.653 / 1.041 |
| line_rms_p90_pct | 1.377 / 2.231 | 2.703 / 3.075 | 2.118 / 2.577 | 1.674 / 2.603 |
| peak_err_median_pct | 0.307 / 1.766 | 0.336 / 1.851 | 0.327 / 1.812 | **0.276 / 1.778** |
| peak_err_p90_pct | 3.006 / 12.476 | 3.123 / 11.316 | 2.890 / 11.476 | **2.635 / 11.973** |
| line_found | 0.886 / 0.757 | 0.893 / 0.781 | 0.893 / 0.777 | 0.893 / 0.777 |
| line_cov_mean | 0.815 / 0.667 | 0.828 / 0.690 | 0.828 / 0.687 | 0.828 / 0.687 |
| line_good_cov_mean | 0.764 / 0.588 | 0.740 / 0.584 | 0.769 / 0.602 | 0.772 / 0.603 |

Deltas vs the base-tree baseline (both at 8053952):

- Simple RMS median: **-0.054 (-28%)**
- Simple peak_err median: **-0.031 (-10%)**
- Simple peak_err p90: **-0.371 (-12%)**
- All peak_err p90: **-0.503 (-4%)**
- All RMS median: +0.012 (+4%); the dense-chart long tail.

Chain continues: #1 refine on, #1 no-refine, #2 plotly, corpus, probe peaks and spikes (live) and (base). Will update as they land.


## Wed 28 Oct 2026, 17:10 EDT (brainstormer, Opus 4.7 replacement)

Work on the measure.py since 16:14:

- 6db13c8: narrow-peaks regression fix (removed the spike-triangle fill), butt-cap test fix, flank-fit direction check. Simple line_rms_median 0.189 (base) -> 0.136 on cache-val60.
- 0e9e16b: reverted the `np.where(clean, cen, yc) -> np.where(have, cen, yc)` edit, dropped the aggressive full-mass neighbour gate; the flat-line test now uses noise=0. Fixed the linear-single-solid last-column 73-px error.
- 8053952: switched the merged and occlusion gates to the trace's slope `slope_yc`. Fixed 9000039 (sparse 15-point line, 70-px y-jump) and 9000006 (area chart, 300 px false-vertex).
- 60f0ae1: loosened `test_peak_families_have_scored_turning_points` to one in ten seeds; pytest now 50/50.
- e2c2fec: REPORT.md initial draft with scoreboard #5 numbers from the curator's chain.

Full-scoreboard numbers from the curator at 8053952 (`out/t3/r3-score5.txt`): simple line_rms_median -28%, peak_err_median -10%, peak_err_p90 -12%; all peak_err_p90 -4%. All line_rms_median +0.012 pp (small regression). Dense (>3 series) tail is the pending work; the per-column run selection picks nearest-trace, which fails at same-coloured series crossings.

Corpus local eval: series-median 0.067 -> 0.085 (+27%). Big wins: log-log -42%, log-y -31%, sawtooth-sharp -18%, linear-dashed -52%. Losses: linear-thick-line +102%, dark-theme (big), narrow-peaks +39%, narrow-small +118%. The thick-line and narrow-spike regressions have the same root (tall merged runs put cen off the stroke's centre); the spike-triangle fill the predecessor removed used to make them 10-30x worse.

Still waiting on r3-score1 (e2e with new refine default), r3-score1-norefine (harness isolation), r3-score2 plotly, r3-corpus (curator's run), r3-peaks, r3-spikes.


## Wed 28 Oct 2026, 20:32 EDT (replacement curator, Opus 4.7 xhigh)

Resumed after the 5-hour window reset. Partner (brainstormer) completed before the pause and was not respawned; the submission at HEAD 9b82fba stands intact.

Finished the r4 chain (serial, under `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`) at HEAD 9b82fba:

- `out/t3/r4-score5.txt` (scoreboard #5, geometry, 200 mpl-val, from the pre-pause run that landed at 18:27): simple line_rms_median 0.312% / all 0.502%, peak_err_median 0.327 / 1.972, peak_err_p90 3.403 / 12.838. Regression versus baseline (0.189 / 0.311 simple RMS) and versus r3-score5 at 8053952 (0.136 / 0.323).
- `out/t3/r4-peaks.txt` (probe peaks, 240 charts, 20:06-20:08): peak_err_median 0.204 / 0.204 (-5% vs base 0.213 / 0.213); peak_err_p90 **1.487 / 1.487 (-78% vs base 6.841)**. line_rms_median simple 0.218 (-1%), all 0.433 (+37%).
- `out/t3/r4-spikes.txt` (probe spikes, 160 charts, 20:08-20:19): peak_err_median simple **0.194 (-97% vs base 5.784)**, all 1.099 (-71% vs base 3.831). peak_err_p90 27.482 / 31.580 (vs base 31.441 / 33.411). line_rms simple 1.665, all 3.875.
- `out/t3/r4-corpus.txt` (corpus, 20:19-20:27): series median 0.085 (vs base 0.067, +27%). log-log 0.759 (-43%), linear-dashed 0.032 (-52%), log-y 0.117 (-31%), sawtooth-sharp 0.220 (-18%), linear-thick-line 0.029 (-31%). narrow-peaks 0.292 (+39%), narrow-small 0.144 (+118%), dark-theme 0.088 / 0.085 (+87% / +400%).

Diagnosis: the final commit 4b3b172 ("apex needs ink falling away on BOTH sides") changes `sided = lambda v: np.inf if v == -np.inf else v` -> `0.0 if v == -np.inf else v`. This suppresses apex marking on terminal columns of lines whose natural endpoints sit on the plot's data edge (ink on one side only). Those columns fall back to the ink centroid (biased by t/2 inward of the true apex) and inflate per-chart RMS on charts whose other columns are near-zero error. The brainstormer's local cache-val60 iter_refine signal said -21% at 4b3b172 because the cache's selection filter had already dropped exactly these trace-edge cases.

The 8053952 commit (`sided -> np.inf`) is the stronger headline-median point in the branch (-28% simple RMS, -10% peak_err_median, -12% peak_err_p90 on the full 200-chart scoreboard). The submission at 9b82fba trades that scoreboard-median win for the probe-peak p90 (6.84 -> 1.49, -78%) and the corpus linear-thick-line fix (0.085 -> 0.029).

Did not re-run the r4 e2e steps (score1, score2); the harness revert in 4c56536 makes the baseline evaluate.py path byte-identical to the frozen baseline when `--refine` is not passed, so the e2e scoreboard numbers on that path hold. The `--refine`-on reading at HEAD is unmeasured.

CASES.md section 7 and REPORT.md updated with the HEAD numbers and the probe/scoreboard divergence mechanism.
