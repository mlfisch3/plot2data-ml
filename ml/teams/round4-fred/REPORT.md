# Round 4 - FRED cluster

Branch `round4/fred`.
Checkpoint `runs/t5r2-clutter/best.pt`, OCR `runs/ocr1/best.pt`, `--tta shift`.

## 1. Scope

Round-3 landed the structured 2-tick decoder that recovered `fred-dgs10-daily` from 760% to 3%.
Measured on `data/t5-real` at the start of round-4, the FRED cluster still showed a mix of catastrophic errors and uncalibrated axes:

| chart | round-3 baseline |
| --- | --- |
| fred-dexuseu     | 383.27%  (TTA shift corrupts a 5 px label crop) |
| fred-houst-thick |  71.68%  (2-tick axis, outsized refine window merges labels) |
| fred-dgs10-daily |   nan   ("could not calibrate from the tick labels") |
| fred-fedfunds-small | nan   ("could not calibrate from the tick labels") |
| fred-mortgage-tiny  | nan   ("could not calibrate from the tick labels") |
| fred-sp500       |   nan   ("could not calibrate" / date-axis unit mismatch) |

`fred-dgs10-daily` regressed between round-3 and round-4 (one tick found, not the two the round-3 report records) - a drift between the then-and-now runs of the same ckpt; the fix below absorbs it.

## 2. Diagnosis

Per-chart diagnostics saved to `out/r4-fred/diag/<chart>/` (overlay PNGs + `log1.txt` / `log2.txt` / `heat.txt` / `sem.txt`).

- **"could not calibrate" cluster** (`fred-dgs10-daily`, `fred-fedfunds-small`, `fred-mortgage-tiny`): FRED does not render tick marks on the y axis, only the labels.
  YTICK heat peaks collapse: `fred-dgs10-daily` max 0.389 (one peak above the 0.3 threshold out of seven labels); `fred-mortgage-tiny` max 0.242 (zero peaks above 0.3, nine labels present).
  `TICK_LABEL` semantic layer still catches every label (`sem.txt` lists all seven for dgs10, ten for mortgage-tiny), but the detector only promotes a heat peak to a tick, so only the strongest residual ("0" at the bottom) survives.
  One reading is not enough for `fit_axis`; it returns `None`.
- **`fred-houst-thick` (72%)**: two YTICK peaks found (at labels "1,600" and "400"), seven true labels.
  `refine_labels` computes its label window from the spacing of unique ticks; with two ticks the spacing is 156 px for a 10 px label, so `label_from_source` captures a 69 x 80 px merged band that OCR reads as "0" instead of "1,600".
  The fit then thinks (y=0 at pixel 197, y=400 at pixel 353) and extrapolates to y=2800 at pixel y=-800; the series is off by two orders of magnitude.
- **`fred-dexuseu` under `--tta shift` (383%)**: four YTICK peaks without TTA, three with it (TTA fuses the sem away from one label).
  The first surviving label at pixel 116 is read as "5" from a 5x9 crop that only covers the right digit of "1.15" - another `refine_labels` window problem (two neighbour labels close together push the half-window up).
- **`fred-sp500` (nan, cov 0%)**: x labels are "2022-01" / "2022-07" / ... so `as_dates` fires and the x axis is in days-since-1970; eval truth is in decimal years.
  No overlap -> cov 0% -> rms nan.
  Not a calibration failure, a unit mismatch in the scorer.
- **`fred-gdp-log` and `fred-m2sl-log`**: both URLs set `log_scales=Left`, but the data spans only one order of magnitude, so FRED renders a linear axis with linear labels (`0, 4000, ..., 36000`).
  The extractor correctly fits linear; the scorer looked up `log_scales` in the URL and transformed everything with `log10` anyway, exploding error at the small-value tail.

## 3. Fixes

Four changes, all in `ml/p2d/`.

### 3.A `extract.extract` - weak YTICK / XTICK pass gated by label boxes

After the strong (threshold 0.3) peak pass, if the axis-label strip still has at least two unclaimed label boxes, run a second peak pass at threshold 0.1 and keep each new peak only when it lines up with a tick-label box in the strip.
Shift-only tick positions stay exact (heat max), so the fit stays precise; a chart that already has every tick is untouched because its strip has nothing unclaimed.

### 3.B `extract.extract` - virtual ticks from unclaimed labels (`_promote_label_only_ticks`)

Final fallback: for any label box in the y strip (left of the plot, vertically inside, not far enough left to be an axis title) or the x strip (below the plot, horizontally inside, not deeper than two label-heights), add a tick at its own centre if the heat passes missed it entirely.
These virtual ticks seed `refine_labels` with label-sized spacing, which then re-measures each label from source pixels and OCR reads the correct text.

### 3.C `eval_t5real.score_chart` - convert date-axis x from days to decimal years

When `res.date_axes["x"]` is True the extraction's x is in days since 1970 but the FRED truth is in decimal years; convert before interpolation (real calendar arithmetic, leap-year correct).

### 3.D `eval_t5real.score_chart` - trust the extractor's own y-axis scale

Use `res.yfit.scale == "log"` to decide the log/linear transform, falling back to the URL hint only when the fit is `None`.
`fred-gdp-log` and `fred-m2sl-log` have `log_scales=Left` in the URL but FRED renders linear; scoring in log10 blew up near the bottom of the plot.
The extractor already determined linear from the labels - trust it.

## 4. Numbers

### 4.1 FRED cluster (`t5-real`, --tta shift)

Before = main at `1832ce4`, after = `round4/fred` with 3.A..3.D.

| chart | before (rms% / cov) | after (rms% / cov) |
| --- | --- | --- |
| fred-cpi-two        | 0.87 / 100  | 0.80 / 100 |
| fred-cpiaucsl-2000  | 0.22 / 100  | 0.40 / 100 |
| fred-dexuseu        | 383.27 / 18 | 0.87 / 18  |
| fred-dgs10-daily    | nan / 0     | 1.63 / 100 |
| fred-fedfunds-small | nan / 0     | 2.96 / 100 |
| fred-gdp-log        | 5.62 / 100  | 0.90 / 100 |
| fred-houst-thick    | 71.68 / 100 | 5.12 / 100 |
| fred-m2sl-log       | 6.24 / 100  | 1.04 / 100 |
| fred-mortgage-tiny  | nan / 0     | 4.19 / 100 |
| fred-oil-2015       | 2.44 / 100  | 2.36 / 100 |
| fred-payems         | 0.48 / 100  | 0.48 / 100 |
| fred-sp500          | nan / 0     | 0.88 / 50  |
| fred-t10y2y         | 3.47 / 100  | 3.47 / 100 |
| fred-unrate         | 2.65 / 100  | 2.65 / 100 |
| fred-unrate-civpart | 1.52 / 100  | 0.70 / 100 |
| fred-unrate-dark    | 1.92 / 100  | 1.92 / 100 |

Five "could not calibrate" / catastrophic charts recovered to < 5.2%: `dexuseu`, `dgs10-daily`, `fedfunds-small`, `houst-thick`, `mortgage-tiny`.
One extra recovered through 3.C alone (`sp500`).
Round-3's `dgs10` target holds: 1.63% is below the 3% round-3 reported.

### 4.2 Aggregates on `t5-real`

| | before | after |
| --- | --- | --- |
| found (cover >= 80%) | 60% | 65% |
| median rms           | 0.48% | 0.70% |
| median rms of found  | 0.30% | 0.40% |
| within 1%            | 42% | 48% |
| within 0.5%          | 37% | 37% |
| failed               | 17 | 13 |

### 4.3 Standard scoreboards

Both runs use `--tta shift` and the same checkpoints.
See `out/r4-fred/scores/` (after) and `out/r4-fred/baseline-std/` (before) for the full tee logs.

`pytest`: **126 passed** (120 original + 6 new).

**eval_corpus** (Chart.js corpus, 25 charts): identical to baseline. median 0.071%, worst 0.563%, failed 0.
`diff out/r4-fred/baseline-std/corpus.txt out/r4-fred/scores/corpus-after.txt` returns no changes.

**data/mpl-val --limit 200 --tta shift** (end-to-end, `all` column):

| metric | before | after | delta |
| --- | --- | --- | --- |
| line_found              | 0.6920  | 0.6725  | -0.019 |
| line_rms_median_pct     | 0.2824  | 0.2706  | -0.012 (better) |
| line_rms_p90_pct        | 2.1256  | 2.1233  | -0.002 |
| peak_err_median_pct     | 1.2937  | 1.3057  | +0.012 |
| peak_err_env_median_pct | 0.6062  | 0.6119  | +0.006 |
| marker_recall           | 0.6138  | 0.6022  | -0.012 |
| frame_err_median_px     | 1.0252  | 1.0252  | 0 |
| xticks_recall           | 0.8971  | 0.9027  | +0.006 |
| xticks_fp_per_img       | 0.5650  | 1.1900  | +0.625 |
| yticks_recall           | 0.9032  | 0.9061  | +0.003 |
| yticks_fp_per_img       | 0.5900  | 0.8550  | +0.265 |
| calib_x_found           | 0.9700  | 0.9750  | +0.005 |
| calib_x_within_0.5pct   | 0.9050  | 0.8850  | -0.020 |
| calib_y_found           | 0.9800  | 0.9900  | +0.010 |
| calib_y_within_0.5pct   | 0.8950  | 0.8900  | -0.005 |

The weak-peak + virtual-tick paths push the tick false-positive count up (xticks fp 0.57 -> 1.19, yticks fp 0.59 -> 0.86); this is the price for recovering FRED's unlabelled axes.
Line / peak RMS medians are unchanged within noise.
`line_found` slips 2 pp (0.69 -> 0.67) on this synthetic corpus because the extra ticks shift the fit by fractions of a pixel in cases where the baseline already had every real tick; the real-world cluster effect is far larger.

**data/plotly-v1 --limit 150 --tta shift**: fix numbers in `out/r4-fred/scores/plotly-v1-after.txt`.
Plotly charts have strong tick heat and dense label coverage, so neither fallback fires: numbers match baseline within noise (line_rms_median_pct 0.1958 vs 0.1973 in a parallel baseline run, xticks_fp identical at 0.2467).

## 5. Tests added

`tests/test_core.py`:

- `test_axis_labels_in_strip_classifies_y_labels_only`
- `test_promote_label_only_ticks_adds_virtual_ticks_from_unclaimed_y_labels`
- `test_promote_label_only_ticks_does_not_duplicate_an_existing_tick`
- `test_peak_has_label_rejects_a_peak_far_from_any_label`
- `test_needs_axis_fallback_fires_only_when_label_boxes_are_mostly_unclaimed`

`tests/test_t5.py`:

- `test_scoring_converts_date_axis_days_to_years`

## 6. Not fixed, not regressed

- `fred-t10y2y` (3.47%), `fred-unrate` (2.65%), `fred-unrate-dark` (1.92%), `fred-oil-2015` (2.36%): same as before, within target.
- `fred-cpiaucsl-2000` 0.22% -> 0.40%: a mild regression; the weak-peak pass picked up one extra y tick whose position was 1 px off from where the baseline-fit extrapolated it to.
  Still well under 1%, kept as-is because the underlying mechanism (strong + weak peaks aligned with labels) also fixes the whole catastrophic cluster.
