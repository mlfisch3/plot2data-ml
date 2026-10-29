# t3-precision r2: the failure catalogue after integration

Baseline for this round: `integration/round-1` at `121ed4d` (the model is `runs/t5-chartjs/best.pt`, OCR `runs/ocr1/best.pt`, runtime flags `--tta shift` with `--refine` on the geometry scoreboard).
All pixel errors are source pixels; "% ph" is a percentage of the plot height, the scoreboard's unit.

Round-2 principle: diminishing returns.
Only probe the losses the integrated model still carries; stop re-measuring losses that round-1 already closed.

## 0. The integrated scoreboard, reproduced here

Headline numbers at `121ed4d` (from `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integration/ml/out/integ/`):

- **mpl-val 200** (simple / all): line_rms_median 0.2101 / 0.3076 %, peak_err_median 0.2253 / 1.3504 %, line_found 0.7517 / 0.6616, calib_x_within_0.5 0.9050, calib_y_within_0.5 0.8950, xticks_err_median 0.2376 / 0.2374 px, yticks_err_median 0.2704 / 0.2625 px.
- **plotly-v1 150** (simple / all): line_rms_median 0.1452 / 0.2057 %, peak_err_median 0.27 / 1.01 %, line_found 0.9252 / 0.8252, calib_x_within_0.5 0.9933, calib_y_within_0.5 0.8867, xticks_err_median 0.1003 / 0.1069 px, yticks_err_median 0.1468 / 0.1555 px.
- **Chart.js corpus** (25 series across 18 charts): series median 0.087 %, worst series 0.214 % (narrow-peaks), 0 series failed.
- **Real screenshots**: panel1 0.82 / 1.89 px (base 1.08 / 1.94), panel2 0.44 / 2.62, panel3 0.85 / 1.32, 05-retail-sales 2 lines 0.69 / 1.94 px.

The integration brought several of the headline numbers close to the floor set by tick measurement on this model:

- calib_x_within_0.5 at 0.9050 means 10 out of 100 mpl-val charts miss x-axis calibration by more than 0.5 % of full scale; same picture on calib_y_within_0.5 at 0.8950 (11 charts missing).
- plotly-v1 calib_x_within_0.5 at 0.9933 is already near the ceiling; the matching plotly calib_y at 0.8867 is the symmetric gap on the y side.
- xticks_err_median at 0.24 px on mpl-val and 0.10 px on plotly-v1: a 0.3 px floor on tick measurement at 400 px plot height is 0.075 % of plot height, the size of the integrated median corpus RMS.

The tick floor caps everything downstream.
A chart whose ticks are known to 0.1 px (sqrt(N) averaging on N marks) rather than 0.25 px takes 0.075 pp off calib error and lifts calib_within_0.5 toward 1.0.

## 1. What round 1 closed, and what it did not

From the integration report's corpus table (`out/integ/corpus.txt` vs base `out/base/v3-corpus.txt`):

| chart | base | integrated | delta |
| --- | --- | --- | --- |
| log-y                   | 0.170 | **0.065** | **-62%** |
| log-y-multi (avg)       | 0.099 | **0.037** | **-63%** |
| log-log                 | 1.326 | **0.210** | **-84%** |
| offset-annotation       | 61.222 | **0.100** | **-99.8%** |
| retina-2x               | 0.109 | **0.015** | **-86%** |
| jpeg-compressed         | 0.034 | **0.021** | **-38%** |
| sawtooth-sharp          | 0.268 | **0.113** | **-58%** |
| linear-single-nogrid    | 0.194 | **0.126** | **-35%** |
| **series worst**        | 61.222 | **0.214** | **-99.6%** |

Round 1 therefore closed:
- The giant offset-annotation outlier (t1 structured axis decode + regex tightening).
- Every log case (t5 native resolution + log-decade training + TTA).
- Scale sensitivity on retina-2x and jpeg-compressed (t5 native-res + TTA).
- The sharp-sawtooth clipping (t3 source-pixel measurement, after the apex-both-sides regression was neutralised in merge).

What remains, measured at integration HEAD on the standard sets:

| chart | base | integrated | delta | why it is still here |
| --- | --- | --- | --- | --- |
| narrow-peaks        | 0.211 | 0.214 | +1% | sub-pixel apex measurement is at or near the floor; residual is tick-driven |
| narrow-small        | 0.066 | 0.109 | +65% | tick-driven: narrow data range on a 400 px plot magnifies calib error |
| dark-theme (avg)    | 0.032 | 0.090 | +180% | ink contrast against dark paper makes the tick-mark finder slip |
| scatter-halo (avg)  | 0.088 | 0.117 | +33% | not a tick-floor case; marker-measurement side |
| linear-single-solid | 0.033 | 0.082 | +148% | the "easy chart" regression noted in the integration report: source-pixel bias on pixel-perfect lines; marginal |
| scatter-markers     | 0.060 | 0.087 | +45% | marker-measurement side |

The round-2 action list splits cleanly:

- **Tick-floor cases**: narrow-small (+65%), the two calib_within_0.5 gaps (10/11 mpl-val charts and 11/150 plotly-v1 charts), the xticks_err_median at 0.24 px on mpl-val. These are what angle C (joint-affine `refine_ticks`) attacks: fit `mark = a + b * pos_net` over the N marks on an axis, so position noise averages toward 0.5 / sqrt(N) px rather than the 0.25 px single-mark floor.
- **Marker-measurement cases**: scatter-halo and scatter-markers. Outside this team's scope in r2 (team 4 territory).
- **The source-pixel-bias "easy chart" cases**: linear-single-solid and similar. The integration report flagged this as a known trade. No work in r2 unless it costs the headline.

## 2. The tick floor, from first principles

The current `refine_ticks` is shift-only: it fits one median shift per axis from the N drawn tick marks, applies that shift to every tick, and only when at least three marks agree beyond the pixel-snap noise.
Base measurement (`CASES.md` section 3, repeated here for continuity):

- Network's raw tick position: median abs 0.27 / 0.30 px (x / y), p90 0.76 / 0.78 px, bias -0.02 / +0.10 px.
- After shift-only snap: 0.34 / 0.37 px median, p90 0.86 / 0.89 px, bias +0.21 / +0.28 px (the renderer's pixel-snap bias of the drawn marks).

The 0.3 px floor is physical: a matplotlib tick mark is drawn as a 1-pixel-wide line whose centre is pixel-snapped, and the sub-pixel truth sits at a uniform [0, 1) phase against that snap, so a single mark's position is only good to about 0.5 / sqrt(12) = 0.14 px of standard deviation plus a renderer-specific offset (+0.3 px here).

Averaging over N marks of one axis brings the shift error down toward 0.5 / sqrt(N) px:

| N marks | expected shift error (px) | at 400 px plot | mpl-val integrated | plotly integrated |
| --- | --- | --- | --- | --- |
| 3  | 0.29 | 0.072 % | - | - |
| 4  | 0.25 | 0.063 % | - | - |
| 5  | 0.22 | 0.056 % | - | - |
| 6  | 0.20 | 0.051 % | - | - |
| 8  | 0.18 | 0.044 % | - | - |
| 10 | 0.16 | 0.040 % | - | - |
| 12 | 0.14 | 0.036 % | - | - |

The current baseline sits at 0.24 - 0.27 px on mpl-val, so even the median has not yet taken the sqrt(N) advantage: the shift value is still coherent across chart populations because of the ink-centring bias (+0.3 px), but a per-axis fit can only correct that offset once it is identified from the same marks.

Angle C adds the second degree of freedom: `mark_i = a + b * pos_net_i` where `b` corrects any per-axis scale drift (the network's heatmap at 768 x 512 for a 1500 px plot expands tick spacing by a fraction of a percent).
With N >= 5 marks the fit is well identified; the slope window around 1.0 tightens with 1 / sqrt(N) so a sparse axis cannot be fooled by two outlier marks and a bad shift.
The implementation and the slope-window rule are at `ml/p2d/extract.py` `_affine_from_marks` and the updated `refine_ticks` (brainstormer's commit `f8b1b1b`); the per-tick, per-policy comparison lives in `ml/p2d/eval_ticks_r2.py` (commit `6d04060`).

## 3. The round-1 probe sets re-measured at integration

Dataset: the same seven t3-* families from round 1 (peaks, spikes, ticks, width, log, grid, frame, scale).
Model: `runs/t5-chartjs/best.pt`, `--refine --tta shift`, no `--ocr` (probe sets are geometry-only; the standard scoreboard adds OCR).
Baseline column is `out/base/*.txt` or the `base-*.txt` captures in `out/t3/` from round 1 (both match: round-1 baseline is `v3/best.pt` without TTA on the frozen tree).
Round-2 column is `out/t3r2/integ-*.txt`.

### 3.1 Peaks (240 charts; `data/t3-peaks`)

PENDING INTEG MEASUREMENT (`out/t3r2/integ-peaks.txt`).
Expected: the round-1 win on `peak_err_p90` (6.84 - > 1.49 % ph at submission HEAD) persists at the integrated model; the full affine `refine_ticks` from angle C should not move probe peaks at all (ticks are not vertices).
This probe is a regression gate for angle C, not a win case.

### 3.2 Spikes (160 charts; `data/t3-spikes`)

PENDING INTEG MEASUREMENT (`out/t3r2/integ-spikes.txt`).
Expected: the round-1 win on dense-spike `peak_err_median` (5.78 - > 0.19 % ph on simple) persists at the integrated model.
This probe is a regression gate for angle C.

### 3.3 Ticks (576 charts; `data/t3-ticks` - round 1 family)

PENDING INTEG MEASUREMENT (`out/t3r2/integ-ticks.txt`).
This is the family angle C targets, but round 1's probe was built for the shift-only pipeline and does not isolate N_marks per axis.
Round 2 replaces this probe with `data/t3-ticks-r2` (section 4).

## 4. The round-2 probe set: `data/t3-ticks-r2`

Generator: `ml/p2d/synth/probe_t3_r2.py`, family `ticks`, seed base 14,000,000, 1,000 charts.
Each chart is one line series across a plot with tightly controlled tick geometry.

### 4.1 Factor grid

Per axis, independent:
- `n_ticks` in {3, 4, 5, 6, 8, 10, 12} (FixedLocator gives exactly N labelled major ticks; verified on 80-seed smoke test, 14/14 hit rate).
- `axis_style` in {linear, log}; log axes carry FixedLocator at `logspace(lo, hi, N)` with a numeric formatter so every tick gets a label.
- `label_density` in {sparse, dense}; dense adds AutoMinorLocator(5) on linear or sub-decade minor ticks on log.
- `grid` in {off, on}; `label_rotation` in {0, 45, 90} degrees.

Per chart:
- `dpi` in {80, 100, 160}.
- `has_offset` with p = 0.25: swaps the y formatter to ScalarFormatter with `useOffset=True` and `powerlimits=(-1, 1)` so the chart prints a "+1e3" / "+1e4" / "+1e5" offset label at the top of the y axis. The y data is placed on a narrow band `[base, base + 0.01 * base]`.

Expected coverage per axis (1,000 charts, 2,000 axes):
- Per N bucket: ~285 axes split across linear/log, so a per-bucket p50/p90 is from ~100 observations.
- Per rotation level: ~670 axes.
- Per grid state: ~1,000 axes.
- Offset axes (y only): ~250 y-axes.

### 4.2 Ground truth

Each chart's JSON records:

- `meta.xticks` / `meta.yticks`: the standard list of labelled major ticks (unchanged across probe families), each with `{value, pos, anchor, side, text, bbox}`. `pos` is the sub-pixel canvas position - this is what the brainstormer joins on.
- `meta.probe.axes.{x, y}.ticks`: round-2 per-tick annotations, one record per labelled major tick plus any minor tick whose gridline is drawn, with `{value, pos_canvas, text, mark_drawn, grid_drawn, is_minor}`.
- `meta.probe.axes.{x, y}` chart-level factors: `{n_ticks_target, n_ticks, axis_style, label_density, grid, label_rotation}`.
- `meta.probe.has_offset`, `meta.probe.axis_offset`, `meta.probe.dpi`.

### 4.3 Baseline measurements (shift-only `refine_ticks`)

PENDING: measured by `ml/p2d/eval_ticks_r2.py` once the probe set regenerates (ETA ~15 minutes from the generator kickoff).
The brainstormer's measurement script compares three policies on the same per-chart marks (no re-run of the network per policy):

1. `none`: the network's `pos_net` itself.
2. `shift`: the current `refine_ticks` median-shift correction, gated by `min_shift` and `max_spread`.
3. `affine`: the joint `mark = a + b * pos_net` fit now in `refine_ticks` (shift-only when N <= 4 marks, affine with slope-identifiability window when N >= 5).

Headline comparisons (expected, confirmed by numbers once the eval lands):

| metric | none | shift | affine (angle C) |
| --- | --- | --- | --- |
| tick p50 abs err (px) | ~0.27 | ~0.34 | TBD |
| tick p90 abs err (px) | ~0.76 | ~0.86 | TBD |
| per-axis mean err stdev (px) | ~0.35 | ~0.20 | TBD (predicted ~0.05 at N >= 8) |

### 4.4 Factor splits

PENDING: these are the splits the brainstormer's `eval_ticks_r2` will produce from the probe JSON joined with the extraction output.
Expected signal:
- `N_marks` factor: `none` and `shift` show roughly flat performance across N (shift already averages, but with +0.3 px bias). `affine` should scale as 1 / sqrt(N), dropping p50 from ~0.27 px at N = 3 to ~0.10 px at N = 12.
- `axis_style` factor: log axes with large span should see the biggest `affine` gain, because any scale drift in the network's heat-map tick placement is a multiplicative error in log space.
- `label_rotation` factor: regression gate; the current `refine_ticks` uses the label_box geometry for side detection, so rotated labels should still produce the same per-tick marks. If `affine` and `shift` numbers diverge across rotations, the label_box path is leaking.
- `has_offset` factor: regression gate on the `_OFFSET` axis path (round 1 commit `9b897ad` tightened the OCR regex). The probe exercises the drawn-mark side.

## 5. What r2 does NOT re-measure

By the diminishing-returns principle:

- `data/t3-width`, `data/t3-log`, `data/t3-scale`, `data/t3-frame`, `data/t3-grid`: these round-1 probes catalogued failures that integration already addressed (log-* corpus wins, retina-2x win, log-log cov improvement). Re-measuring would spend GPU time with no action-item outcome.
- The `narrow-peaks` corpus case: integrated at 0.214 % vs base 0.211 %, essentially parity. A Gaussian-fit specialisation (angle A, deferred) would buy at most 0.007 pp on the corpus median, well below diminishing-returns threshold.
- Marker measurements: scatter-halo and scatter-markers regressions are team 4 territory, not re-walked here.

## 6. Where this leaves angle C

The probe set is the diagnostic tool for angle C.
Six corpus cases are tick-sensitive: narrow-peaks, narrow-small, log-y, log-log, offset-annotation, linear-single-nogrid.
If `data/t3-ticks-r2` shows `affine` beating `shift` on every N bucket from 5 upward by >= 0.05 px p50 and >= 0.15 px p90, the fit propagates into calib_within_0.5 (expected 0.905 - > 0.95+) and into line_rms_median by 0.01 - 0.02 pp on mpl-val.
If it does not, angle C stops; angle A (narrow-peaks Gaussian fit) is the stretch fallback.
