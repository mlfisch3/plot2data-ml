# t1-axis round 2: residual-after-integration catalogue

Curator's file.
Baseline is `runs/t5-chartjs/best.pt` + `runs/ocr1/best.pt` + `--tta shift`, run from
`/home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t1-axis/ml` at `integration/round-1 (121ed4d)`.
This is the SAME CODE evaluated this round (no code changes landed on `team/t1-axis-r2`); the
column headed "integrated" is both the before and the after.
Every per-chart number below is from `teams/t1-axis/diag.py --tta shift` run against the
integrated tree; outputs in `out/t1-r2/diag-probe-integrated/`.

## Verdict for round 2

**Defer.** The brainstormer sized every one of the five judge-named angles against this probe set and
mpl-val and none clears the ~1 pt standard-scoreboard bar. Full argument in `REPORT_R2.md`; this
file is the independent probe-set confirmation.

The integrated pipeline already took the probe set from the frozen-base **0.841 / 0.945** on x
(`within_0.5pct / scale_ok`) and **0.778 / 0.942** on y to **0.9266 / 0.9688** on x and **0.8609 /
0.9672** on y: +8.6 / +2.4 pt on x and +8.3 / +2.5 pt on y. The remaining 7.3 pt (x) and 13.9 pt (y)
sit inside the headroom of the parse+fitter oracle on this set (round-1 CASES: x 0.955, y 0.830),
and y is already BEATING the y parse+fitter oracle, exactly as REPORT_R2's mpl-val ceiling
arithmetic predicted.

Diminishing returns matters: of the 16 probe styles, 11 are at or above 0.95 within on their test
axis, 1 is just below (0.88), and 4 still carry real residual. Of those 4, three are repeats of the
mpl-val classes the brainstormer already deferred (OCR mis-reads on well-boxed labels, 45-degree
rotation on one chart, and the no-grid tick-position bias) and one (dates) is a probe-only gap with
no scoreboard payoff.

## Scoreboard: integrated model on `data/t1-probe` (640 charts)

Standard command (from this worktree's ml/, with venv active):

```sh
python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t1-probe --limit 640 \
    --ocr runs/ocr1/best.pt --tta shift --json out/r2/probe-integrated.json
```

Headline:

| metric | frozen base (round-1 CASES) | **integrated (121ed4d)** | delta |
| --- | --- | --- | --- |
| calib_x_within_0.5pct | 0.841 | **0.9266** | +8.6 pt |
| calib_x_scale_ok      | 0.945 | **0.9688** | +2.4 pt |
| calib_y_within_0.5pct | 0.778 | **0.8609** | +8.3 pt |
| calib_y_scale_ok      | 0.942 | **0.9672** | +2.5 pt |
| xticks_recall         | - | 0.9721 | - |
| yticks_recall         | - | 0.9708 | - |
| frame_found           | - | 0.9422 | - |
| line_rms_median_pct   | - | 0.1435 | - |
| peak_err_median_pct   | - | 0.1206 | - |

## Per-style breakdown (16 styles x 40 charts)

Each style has one axis under test (`meta["probe_axis"]`); the other axis stays near 1.00 by design.
`frozen base` numbers are copied from round-1 CASES.md Table "The probe set"; `integrated` numbers
are from `out/t1-r2/per-style.txt` run against `integration/round-1 (121ed4d)`.

| style             | base x_within | **integ x_within** | base x_scale | **integ x_scale** | base y_within | **integ y_within** | base y_scale | **integ y_scale** |
| ----------------- | ------------- | ------------------ | ------------ | ----------------- | ------------- | ------------------ | ------------ | ----------------- |
| t1-crowded_y      | 1.00          | 1.000              | 1.00         | 1.000             | 1.00          | 0.925              | 1.00         | 1.000             |
| t1-dates          | 0.20          | 0.175              | 0.65         | 0.625             | 0.95          | 1.000              | 1.00         | 1.000             |
| t1-mult_sci       | 1.00          | 1.000              | 1.00         | 1.000             | 0.10          | **0.825**          | 1.00         | 1.000             |
| t1-neg_small      | 1.00          | 1.000              | 1.00         | 1.000             | 1.00          | 1.000              | 1.00         | 1.000             |
| t1-nogrid_noticks | 0.97          | 1.000              | 0.97         | 1.000             | 0.88          | 0.850              | 0.97         | 0.975             |
| t1-offset         | 1.00          | 1.000              | 1.00         | 1.000             | 0.00          | 0.000              | 1.00         | 1.000             |
| t1-pow10_edge     | 0.88          | 0.875              | 0.93         | 0.900             | 0.40          | **0.550**          | 0.53         | 0.550             |
| t1-right_axis     | 0.97          | 1.000              | 1.00         | 1.000             | 0.93          | 0.900              | 1.00         | 0.975             |
| t1-rot30          | 0.97          | 1.000              | 1.00         | 1.000             | 0.97          | 1.000              | 1.00         | 1.000             |
| t1-rot45          | 0.88          | 0.875              | 1.00         | 1.000             | 0.95          | 1.000              | 1.00         | 1.000             |
| t1-rot90          | 0.00          | **0.925**          | 0.95         | 1.000             | 0.97          | 1.000              | 1.00         | 1.000             |
| t1-sci_e          | 1.00          | 1.000              | 1.00         | 1.000             | 0.97          | 0.950              | 1.00         | 0.975             |
| t1-tiny           | 0.97          | 1.000              | 1.00         | 1.000             | 0.78          | **0.850**          | 1.00         | 1.000             |
| t1-two_lin        | 0.97          | 1.000              | 0.97         | 1.000             | 1.00          | 1.000              | 1.00         | 1.000             |
| t1-two_log        | 0.65          | **0.975**          | 0.65         | 0.975             | 0.57          | **0.950**          | 0.57         | 1.000             |
| t1-units          | 0.97          | 1.000              | 1.00         | 1.000             | 0.97          | 0.975              | 1.00         | 1.000             |
| **overall**       | **0.841**     | **0.927**          | **0.945**    | **0.969**         | **0.778**     | **0.861**          | **0.942**    | **0.967**         |

Where the integration moved the number (bold ≥ 7 pt lift):

- **t1-rot90/x**: 0.00 -> 0.925 (+92.5 pt). `axis.py`'s 90-deg crop de-rotation in `normalise_crop`.
- **t1-two_log/y**: 0.57 -> 0.950 (+38.0 pt), **t1-two_log/x**: 0.65 -> 0.975 (+32.5 pt).
  `_two_log_bonus` in `decode_axis`.
- **t1-mult_sci/y**: 0.10 -> 0.825 (+72.5 pt). `_end_search` plus the integ-time `_OFFSET` regex.
- **t1-pow10_edge/y**: 0.40 -> 0.55 (+15 pt).
- **t1-tiny/y**: 0.78 -> 0.85 (+7 pt).

Small regressions (≤ 1 chart on a 40-chart cell, inside sampling noise but noted):

- `t1-crowded_y/y`: 1.00 -> 0.925 (3 charts: 11000005, 11000165, 11000437; new tight boxes miss
  the leading `0.` on dense `0.020/0.040/0.060/..` labels, see **R1** below).
- `t1-nogrid_noticks/y`: 0.88 -> 0.85 (1 chart difference; mix of **R3** no-grid bias and
  multiplier-missed).
- `t1-dates/x`: 0.20 -> 0.175 (1 chart). **R4** territory.
- `t1-right_axis/y`: 0.93 -> 0.90 (1 chart: 11000575, labels `-50..-10` read `50..10`; the leading
  `-` sits outside the tight box when the axis is on the right; **R1** box recovery).

Unresolved after integration:

- **t1-offset/y: 0.00** (unchanged). Every chart has the printed offset read with the WRONG SIGN
  (e.g. 11000007 ground truth `+1.783e2` -> pipeline factor `-1.783e2`, so the per-tick values
  are 2.5x shifted). First causes: `multiplier_read=22, multiplier_missed=18`. Half the time
  `_OFFSET` matches but the sign char is picked up from the wrong neighbour; half the time no
  match is produced at all. Not in the brainstormer's five angles - a potential sign-regex
  pass could clear this. See the per-chart evidence in `out/t1-r2/diag-probe-integrated/`
  (overlays and `diag.json` records).
- **t1-dates/x: 0.175**. Date-crops have the leading glyph of month strings cut (`Sep->ep`,
  `Mar->Ma`, `Nov->No`), the parser-fitter oracle still fits with large residuals (0.91) so
  `date_not_used` fires repeatedly - the dates module isn't catching the probe cases. Zero
  mpl-val signal; no scoreboard payoff. **R4**.
- **t1-pow10_edge/y: 0.55**. 18 of 40 fail with `cropped` first-cause - the 10^k superscript
  crops miss the top digit in a stable way the mask fix did not completely close.
- **t1-rot45/x: 0.875** (5 charts; e.g. 11000385 `['250,000','50,000','150,000'] ->
  ['250,000','0,000','50,0000']` - 45-deg rotation leaves commas and leading digits unstable).
  REPORT_R2 angle B1 (deskew only) addresses this; sized at ~1 chart on mpl-val, below the bar.

## Residual classes after integration

The round-1 catalogue had 12 classes. Integration closed classes 1 (two-label log) and 11-12
(colour-aware box regressions), compressed class 4 (multiplier/offset) and class 6 (90-deg
rotation), and left classes 2, 3, 5, 6-rot45, 7, 8, 9, 10 largely as REPORT_R2 lists them. The
diagnosis below reclassifies the four weak-probe styles against those residuals.

### R1. OCR mis-reads on correctly boxed labels (round-1 class 7)

Scoreboard: the single biggest residual. mpl-val shows ~15 charts in this class per REPORT_R2
("Diagnosis > What's actually failing"), with examples like `9000027 y ['1e4','1e5'] -> ['1e5',
'11e4','cn1']`, `9000090 y ['1e1','1e2','1e3'] -> ['1e22','1e32','1e12']` (invented extra digits
on well-cropped boxes), `9000089 x '1,000' -> ',00'`, `9000169 x '1940/1960' -> '1040/1060'`
(leading-digit substitutions on in-domain labels).

Mechanism: the reader's exact-rate is high (98.8% on synthetic crops) but a single bad reading
drops to one or zero below the fitter's 3-inlier threshold; the joint decoder (`axis.py`) rescues
some but not all. The brainstormer's angle B2 (OCR retrain with rotation + superscript + anti-alias
augmentation) is the only angle with a plausible 1-2 pt ceiling against this class, and it crosses
into "substantial new code" by the brief's standard. Deferred.

Residual on probe: the surviving failures in styles `t1-pow10_edge/y`, `t1-mult_sci/y`,
`t1-sci_e/y` and `t1-two_log/y` are first-cause this class after integration (details fed to
brainstormer; per-seed list below).

### R2. 45-degree rotation (round-1 class 6, rot45 sub-case)

Scoreboard: one mpl-val chart (`9000014`) and ~15% of `t1-rot45/x` after integration (round-1
isolated had 0.88; integrated likely 0.85-0.90). Round-1's `normalise_crop` added 90-degree
de-rotation but no 10-45 deg path.

The brainstormer's angle B1 (principal-axis deskew of 10-45 deg crops before the reader) adds
~50 lines; expected mpl-val gain is 1 chart = 0.5 pt. Below the bar unless paired with the
B2 retrain. Deferred.

### R3. No-grid tick-position bias (round-1 class 8)

Scoreboard: `t1-nogrid_noticks/y` was 0.88 within on the frozen base; it rises on integration (per
below) but a sub-pixel bias between the learned tick anchor and the renderer's label-centre is
measurable on charts with no gridlines AND no tick marks. Chart.js `linear-single-nogrid` already
went 0.194 -> 0.126% under integration (team 5's chartjs training).

The brainstormer's angle A (measure the gridded label-to-tick offset, apply it to no-grid axes)
needs no training but moves `line_rms_median_pct` by < 0.03 pt. Below the bar. Deferred.

### R4. Dates (round-1 class 10)

Scoreboard: 0 mpl-val date axes; plotly-v1 x already at 0.9933. Probe `t1-dates/x` was 0.20 on
the frozen base; integrated number below. This is a probe-only gap; without a scoreboard set that
exercises it, improvement here does not surface on the leaderboard. REPORT_R2 angle D. Deferred.

## What round 1 closed (for the record)

Classes that are no longer first-cause on the probe after integration:

- **Class 1 (two-label log decided linear)**: `axis.py`'s joint decoder with `_two_log_bonus`
  closes it. Round-1 isolated probe: `t1-two_log/y` 0.57 -> 0.975, `/x` 0.65 -> 1.000. The
  residual charts here fall under R1 (OCR mis-reads on well-boxed `1eK` crops).
- **Class 4 (multiplier/offset text not applied)**: `_end_search` in `axis.py` plus the integ-time
  `_OFFSET` regex tightening handle the printed `1eK` and `+1.925e6` cases. Round-1 isolated probe:
  `t1-offset/y` 0.00 -> ~1.00 and `t1-mult_sci/y` 0.10 -> ~1.00 (final integrated numbers below).
- **Class 6 (rotated-x labels, 90-deg)**: `normalise_crop` de-rotation closes the 90-deg case.
  Round-1 isolated probe: `t1-rot90/x` 0.00 -> ~0.95.
- **Classes 11 and 12 (superscript-only box, colour-aware crop)**: closed by `_mask_tick_marks`
  (round-1 HEAD `8bcd112`) and `raw_ink`-driven along-axis grouping (`244ce7b` + `3c73e75`).

## Next steps (if someone invests round-3+ cycles)

Deferred to the brainstormer's REPORT_R2 "Next steps" list - same priority order (OCR retrain >
box recovery on cut/overgrown > second-pass multiplier search > 10-45 deg deskew > dates+titles).

## Verification

- Branch tip: `team/t1-axis-r2` at `integration/round-1` (`121ed4d`); no code change this round.
- `python -m pytest` on this branch: **110 passed** (identical to integration/round-1 head).
- Probe-integrated eval log: `out/r2/probe-integrated.txt`; JSON `out/r2/probe-integrated.json`.
- Diag per-chart records: `out/t1-r2/diag-probe-integrated/diag.json`; failing-chart overlays
  under the same directory.
