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

## Scoreboard

(Pending curator's regenerated probe batch and the full scoreboard sweep.)

### t3-ticks-r2 probe set (1000 charts, factor grid)

Factors: N_ticks in {3,4,5,6,8,10,12} per axis, axis_style in {linear, log}, dpi in {80, 100, 160}, label_density in {sparse, dense}, grid in {off, on}, label_rotation in {0, 45, 90}, has_offset at ~25%.
Seed base 14,000,000.
Pending the fixed-locator regen.

Headlines (pending `out/t3r2/ticks.json`):

- |err| p50 / p90 per policy (none / shift / affine), bucketed by N_marks and by axis_style.
- Rate of unidentifiable-slope fallback into shift-only.
- Rate at which `|b - 1|` falls inside vs outside the identifiability window.

### Chart.js corpus

(Pending the curator's integ re-measurement vs the new commit.)

### End-to-end mpl-val 200 and plotly-v1 150

(Pending.)

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
