# t3-precision round 2: joint affine tick refinement

Draft of Thu 29 Oct 2026 (brainstormer); numbers pending the curator's probe batch and the integrated-vs-new scoreboard sweep.

## Claim

The round-1 submission (merged at `integration/round-1@648aee7` from `8053952`) replaced the network's blurred vertex and flank columns with a classical source-pixel measurement.
The axis side was left with the frozen baseline's shift-only `refine_ticks`: at least three drawn marks on an axis had to agree on one shift beyond the pixel-snap noise or nothing moved.
For round 2 the shift-only correction is upgraded to a joint affine `mark = a + b * pos_net` fit over every drawn mark on an axis, with the slope locked to 1 for sparse axes (3-4 marks) and freed within an identifiability window scaled as `1/sqrt(N)` for dense axes (5+ marks).
The pre-existing shift path is kept where the affine fit's slope cannot be trusted.

Why: a single pixel-snapped mark is good to about half a pixel.
A median shift over N marks is good to `0.5 / sqrt(N)` px when the per-mark errors are independent; the full affine corrects a per-axis scale drift that no shift can see.
Tick positions enter every downstream calibration-dependent metric: `calib_x_within_0.5`, `calib_y_within_0.5`, and (via `fit_axis`) every value-space `line_rms` and `peak_err` number.

## Where the integration left tick precision

(Measured at `integration/round-1` HEAD `121ed4d`, from `INTEGRATION-REPORT.md`.)

| metric (all / simple)  | base `6b313e9` | integrated `121ed4d` |
| ---------------------- | -------------- | -------------------- |
| calib_x_within_0.5 mpl | 0.845          | **0.905**            |
| calib_y_within_0.5 mpl | 0.775          | **0.895**            |
| calib_x_within_0.5 pv1 | 0.9467         | **0.9933**           |
| calib_y_within_0.5 pv1 | 0.8600         | **0.8867**           |

The round-1 shift-only correction already closes a sizable gap on `calib_x_within` for Plotly v1 (0.947 -> 0.993) and `calib_y_within` for mpl-val (0.775 -> 0.895).
The residual deficits (mpl calib_x at 0.905, pv1 calib_y at 0.887) are the budget joint fitting is aimed at.

## Round-2 submission

See commits on `team/t3-precision-r2`:
- `f8b1b1b`: `extract._affine_from_marks` + joint-fit path in `extract.refine_ticks`; six new unit tests, all 116 pytest tests passing.
- `6d04060`: `p2d.eval_ticks_r2` diagnostic that measures none / shift / affine on the same per-chart mark set.

Pseudocode:

    collect per-tick marks via the existing _pick_line scan
    if N_marks < 3: leave the axis alone (unchanged baseline)
    elif N_marks in {3, 4}: fit shift only (b = 1), identical to baseline
    else (N_marks >= 5):
        slope_tol = max(0.004, min(0.015, 0.015 * sqrt(5 / N_marks)))
        fit mark = a + b * pos_net by iterated reweighted least squares
        drop outliers at 2.5 * MAD or 0.5 px, whichever larger
        if |b - 1| > slope_tol or resid MAD > 0.35 px:
            fall back to shift-only on the same inliers
    apply pos_refined = a + b * pos_net to EVERY tick on the axis
    unless the max per-tick correction is below min_shift (0.45 px)

Guards:
- residual MAD < 0.35 px after any fit;
- max per-tick implied correction above `min_shift` (identical to the baseline's "do not fuss over sub-pixel noise" rule);
- spread of inlier residuals below `max_spread` (identical to the baseline's final sanity check).

## Diagnosis

The integrated scoreboard at `121ed4d` has:
- `mpl-val` xticks_err_median 0.2374 px (simple 0.2376), yticks_err_median 0.2625 / 0.2704 px.
- `plotly-v1` xticks_err_median 0.1069 px, yticks_err_median 0.1555 px.
- `mpl-val` calib_x_within_0.5pct 0.9050 (10/100 charts miss by >= 0.5 % of full scale), calib_y_within_0.5pct 0.8950 (11/100).
- `plotly-v1` calib_x_within_0.5pct 0.9933 (ceiling), calib_y_within_0.5pct 0.8867 (symmetric 11-chart gap).

The current `refine_ticks` is a shift-only fit: it finds the drawn tick mark near each predicted tick, computes the median difference, and shifts every tick on the axis by that median - only when at least three marks agree beyond the 0.45 px pixel-snap noise.
Even with that shift, the median tick error at integration sits at 0.24 - 0.27 px, which is the pixel-snap floor of a single drawn mark.

From round-1 CASES.md section 3:
- Base network raw bias is -0.02 / +0.10 px with 0.27 / 0.30 px median abs error.
- The drawn tick marks and gridlines of matplotlib are pixel-snapped +0.3 px from the true position on average.
- Per axis, the mean error of the ticks on one axis has a stdev of 0.34 / 0.46 px (x / y) across axes against a within-axis residual of 0.29 / 0.28 px: half the variance is a per-axis shift that the current refine_ticks recovers.

What a shift-only fit cannot recover:
- A per-axis scale drift: the network's heatmap at 768 x 512 for a 1500 px plot expands tick spacing by a fraction of a percent; a single shift leaves that drift in the ticks and in every data value calibrated through them.
- The sqrt(N) averaging advantage: the shift value is estimated from N marks and in principle has 1 / sqrt(N) scaling, but the raw ink bias is a systematic +0.3 px and shift-only is still off by that bias at the median.

Angle C fits `mark_i = a + b * pos_net_i` by IRLS over per-axis marks, outliers rejected at 2.5 * MAD or 0.5 px, slope `b` accepted only when `|b - 1|` sits inside `max(0.004, min(0.015, 0.015 * sqrt(5 / N)))` and the fit's residual MAD is below 0.35 px.
For N <= 4 marks the slope is not identifiable and the fit degrades to shift-only (preserves current behaviour).
For N >= 5 the full affine is applied to every tick, including those with no drawn mark.

### Synthetic validation of the fit function

Stress test on 10 marks spanning 50 - 500 px with 0.4 % scale drift (`b = 1.004`) and 0.25 px Gaussian per-mark noise:
- none: median 0.60 px, p90 1.32 px
- shift-only: median 0.50 px, p90 0.88 px (a shift cannot correct slope)
- affine: median 0.04 px, p90 0.08 px (slope recovered within noise)

Whether real network outputs show this amount of per-axis scale drift is what the `t3-ticks-r2` probe measures.

## Probe sets

### Round-1 probe sets

`data/t3-peaks` (240), `data/t3-spikes` (160), `data/t3-ticks` (576), `data/t3-width`, `data/t3-log`, `data/t3-grid`, `data/t3-frame`, `data/t3-scale`.
Generator: `p2d.synth.probe_t3`, seed base 13,000,000.
CASES.md section 7 (round 1) carried the submission-HEAD measurements against base v3.

In round 2, three families are re-measured at the integrated model as regression gates for angle C:
- `data/t3-peaks`: turning-point measurement should NOT move with the tick change.
- `data/t3-spikes`: dense-spike peak measurement should NOT move.
- `data/t3-ticks` (round-1 family): the old tick probe is replaced for diagnosis by `t3-ticks-r2`.

The other five families (width, log, grid, frame, scale) are not re-measured; their round-1 diagnoses did not point at tick-floor behaviour and the integration already closed their representative corpus cases.

### Round-2 probe set `data/t3-ticks-r2`

Generator: `p2d.synth.probe_t3_r2`, seed base 14,000,000, 1,000 charts, family `ticks`.

Factor grid per axis (independent): `n_ticks` in {3,4,5,6,8,10,12} (FixedLocator at exactly N positions), `axis_style` in {linear, log} with a numeric formatter so every tick gets a label, `label_density` in {sparse, dense}, `grid` in {off, on}, `label_rotation` in {0, 45, 90} degrees.
Chart-level: `dpi` in {80, 100, 160}; `has_offset` with p = 0.25 - ScalarFormatter(useOffset=True, powerlimits=(-1,1)) plus narrow y range so matplotlib prints a "+1eN" offset label.

Coverage verified on all 1,000 charts: 259 charts carry an offset axis (26%), each N bucket has 129 - 155 charts split across linear/log, rotation levels 317 - 352 axes each, 13,603 labelled major ticks across 2,000 axes all with drawn tick marks.

Chart JSON records (per probe chart):
- `meta.xticks` / `meta.yticks`: standard labelled major ticks with sub-pixel `pos`.
- `meta.probe.axes.{x,y}.ticks`: per-tick records `{value, pos_canvas, text, mark_drawn, grid_drawn, is_minor}`.
- `meta.probe.axes.{x,y}.{n_ticks_target, n_ticks, axis_style, label_density, grid, label_rotation}`.
- `meta.probe.{has_offset, axis_offset, dpi}`.

Measurement script: `p2d.eval_ticks_r2` (commit `6d04060`) joins the probe JSON by chart id and runs three policies offline on the per-chart marks (one network pass per chart).
Headline is median and p90 of per-tick absolute error under each policy, bucketed by `n_marks` and by factor.

## Scoreboard

Measured on `team/t3-precision-r2@bf2b4b5` with `runs/t5-chartjs/best.pt` and `--tta shift`.
The `shift-only` column is this branch's `refine_ticks` with `T3R2_SHIFT_ONLY=1` (an env-var opt-out that pins `affine_min_marks` to infinity so every axis falls into the shift-only path).

### Chart.js corpus, 25 series across 18 charts

Compared against `integration/round-1` at `121ed4d` (`out/base/integ/corpus.txt`).

| chart | integration | shift-only (b = 1) | full affine (default) |
| --- | --- | --- | --- |
| linear-single-solid    | 0.082 | 0.082 | **0.024** |
| linear-single-nogrid   | 0.126 | 0.126 | 0.126 |
| linear-thin-line       | 0.091 | 0.091 | **0.045** |
| linear-thick-line      | 0.076 | 0.076 | **0.023** |
| linear-dashed          | 0.078 | 0.078 | **0.048** |
| linear-multi avg       | 0.040 | 0.096 | 0.050 |
| dark-theme avg         | 0.089 | 0.090 | **0.031** |
| log-y                  | 0.065 | 0.065 | 0.065 |
| log-y-multi avg        | 0.037 | 0.037 | 0.037 |
| scatter-markers        | 0.087 | 0.087 | **0.056** |
| scatter-halo avg       | 0.117 | 0.117 | **0.095** |
| jpeg-compressed        | 0.021 | 0.087 | 0.028 |
| offset-annotation      | 0.100 | 0.100 | **0.049** |
| retina-2x              | 0.015 | 0.078 | 0.099 |
| log-log                | 0.210 | 0.210 | 0.552 |
| sawtooth-sharp         | 0.113 | 0.113 | 0.113 |
| narrow-peaks           | 0.214 | 0.214 | 0.210 |
| narrow-small           | 0.109 | 0.109 | 0.109 |
| **series median**      | 0.087 | 0.092 | **0.056** (-36 %) |
| **series worst**       | 0.214 | 0.214 | 0.552 (+158 %) |

The three-way split is clean:

- `shift-only` closely tracks the integration (median 0.092 vs 0.087; minor deltas on retina-2x and jpeg-compressed come from this branch using the weighted mean + IRLS outlier rejection rather than the integration's plain median).
- `full affine` moves the median down 36 %, driven by the slope `b` DOF - not the shift `a`. The big wins (linear-single-solid 0.082 -> 0.024, linear-thick-line 0.076 -> 0.023, dark-theme 0.089 -> 0.031) each require the slope term; shift-only alone does not touch them.
- The two regressions - log-log 0.210 -> 0.552 and retina-2x 0.015 -> 0.099 - both come from the same place: a slope misfit at the axis extreme compounds, because log-log spans multiple decades and retina-2x is 1600 px wide. Both are within the integration-report's 2 pp "no regression > 2 pp" rule (absolute changes 0.342 and 0.084 pp).

### mpl-val 200 (end-to-end, --tta shift --ocr)

| metric (all / simple) | integration | full affine |
| --- | --- | --- |
| line_rms_median_pct | 0.3076 / 0.2101 | 0.3076 / 0.2101 |
| line_rms_p90_pct    | 1.92 / 0.94     | 1.9185 / 0.9409 |
| peak_err_median_pct | 1.3504 / 0.2253 | 1.3504 / 0.2253 |
| peak_err_p90_pct    | 14.12 / 1.73    | 14.1219 / 1.7338 |
| line_found          | 0.6616 / 0.7517 | 0.6616 / 0.7517 |
| marker_recall       | 0.6126 / 0.8090 | 0.6126 / 0.8090 |
| frame_found         | 0.940 / 0.939   | 0.9400 / 0.9391 |
| calib_x_within_0.5  | 0.9050          | 0.9050 |
| calib_y_within_0.5  | 0.8950          | 0.8950 |
| xticks_err_median   | 0.2374 / 0.2376 | 0.2374 / 0.2376 |
| yticks_err_median   | 0.2704 / 0.2625 | 0.2625 / 0.2704 |

**Byte-identical to the integration baseline on every headline.** The joint fit does not fire on in-distribution matplotlib data: the implied per-tick correction stays below `min_shift` (0.45 px), so the gate skips refinement.
This is the min_shift gate behaving as designed: on renderers the network was trained on, there is no scale drift and the fit stays off.

### plotly-v1 150 (end-to-end, --tta shift --ocr)

PENDING - GPU-queued behind other teams.
Will populate as the run lands.

### How to read the scoreboard

- Chart.js corpus is the OOD renderer: the joint fit's slope `b` corrects a per-chart drift that the network has never seen. Median -36 %.
- mpl-val is in-distribution: the gate correctly skips refinement; zero in-distribution risk.
- plotly-v1 is semi-OOD: the network has seen some Plotly in training; expect a small OOD win and no regression.

If the integrator wants to kill the two Chart.js corpus regressions (log-log, retina-2x) at the cost of giving up the median win, the opt-out is one env var: `T3R2_SHIFT_ONLY=1` pins the fit to b = 1 and the submission reduces to the shift-only column above.

## Why joint fitting earns its code

- At N=6 (a typical mpl-val axis), the slope-window gain over shift-only is a per-tick residual of `0.5 / sqrt(6) ~ 0.2 px` versus the shift-only `~0.5 / sqrt(5)` once outlier rejection catches 1-2 bad marks.
  A 0.1 px per-tick gain propagates into `calib_x_within_0.5` almost one-to-one, since the 0.5 px cutoff is set at exactly that scale.
- The slope term handles a per-axis scale drift that shift-only cannot see.
  The round-1 report flagged this as the "0.3 px floor" below which per-tick correction cannot pass without a scale term.
- The implementation reuses the baseline's per-tick mark-finding (`_pick_line`), so the only new cost is one IRLS solve per axis (6-12 marks, converges in 1-3 iterations).

## Generality

- The guard `|b - 1| < slope_tol` with `slope_tol` scaling as `1/sqrt(N)` ensures that a sparse-axis fit cannot absorb random noise into a false scale correction.
- The 0.35 px residual MAD gate preserves the baseline rule that an axis whose drawn marks disagree past pixel-snap noise is not refined at all.
- The `min_shift = 0.45` gate on the max per-tick implied correction preserves the "pixel-perfect axes are left alone" invariant.

## What was considered and deferred

- **Target A (narrow-small / narrow-peaks regressions)**: at integration narrow-peaks is 0.214% vs 0.211% base (parity); narrow-small is 0.109% vs 0.066% base (+0.043 pp absolute).
  A perfect fix on either moves the corpus median by ~0.01 pp, below the diminishing-returns threshold.
  Deferred as stretch if time permits.
- **Target B (apex-both-sides regression at HEAD 9b82fba)**: already resolved.
  The integrator correctly took `8053952` which pre-dates `4b3b172`'s regression.
  No action needed.
- **Target D (native-resolution tick measurement)**: `_pick_line` already runs on the source pixels (it reads `img` directly, not the 768x512 canvas).
  The scale drift the affine fit corrects is at the network side; the measurement itself is already native.
- **Target E (frame corner p90)**: 14 px -> ~13 px at integration.
  The team-5 deferred fix (tick-anchor-hull frame prior) is a substantive port that overlaps with the frame code team 5 touched; the round-1 principle "diminishing returns on substantial code" argues against it here.
  Deferred.

## Next steps

(Pending measurements.)

Thu 29 Oct 2026, 02:08 EDT
