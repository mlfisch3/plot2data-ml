# Round 5 - mpl-val tighten after round-4 FRED fallback

Branch `round5/mpl-val-tighten`, base `d55bcc7` (round-4-fred).
Checkpoint `runs/t5r2-clutter/best.pt`, OCR `runs/ocr1/best.pt`, `--tta shift`.

## 1. Scope

Round-4 shipped two gated fallbacks in `extract.extract()` that recover FRED charts whose axes draw no visible tick marks:

- a weak-peak pass (threshold 0.1) that fires when the strip has 2+ unclaimed label boxes,
- a virtual-tick promotion (`_promote_label_only_ticks`) that turns any unclaimed strip box into a tick at its own centre.

Both passes over-fire on mpl-val, where the strong pass already covers every real tick but stray strip text (axis titles, offset labels, 2-tick synthetic charts) still trip the "2+ unclaimed" trigger.
Measured on `data/mpl-val --limit 200 --tta shift`:

| metric | pre-fred (1832ce4) | round-4-fred (d55bcc7) | delta |
| --- | --- | --- | --- |
| line_found              | 0.6920 | 0.6725 | -2.0 pp |
| xticks_fp_per_img       | 0.5650 | 1.1900 | +0.62  |
| yticks_fp_per_img       | 0.5900 | 0.8550 | +0.27  |

Round 5 tightens the two gates so mpl-val returns to pre-fred quality without undoing the FRED win.

## 2. Diagnosis

Instrumented `extract` under `--tta shift` on both corpora (`out/r5-mpl/diag-mpl.json`, `out/r5-mpl/diag-fred.json`).

Three signals separate FRED's "the heat really is broken" cases from mpl-val's "a stray box faked an unclaimed label" cases:

- **Max strong peak score.** FRED's starved YTICK heat peaks between 0.0 and 0.549; mpl-val's healthy axes have max score around 0.65-0.83 (and when they fire a fallback it is usually at 0.6-0.8 anyway).
- **Strip share of strong peaks.** On a FRED screenshot every strong peak lines up with a label (ratio 1.0 for `dgs10-daily`, `fedfunds-small`, `mortgage-tiny`, `dexuseu`, `houst-thick`); on an mpl-val noisy heat channel the strong peaks are scattered across the plot (`9000047` xticks: 3 in strip of 9 strong, ratio 0.33).
- **Tick count already on the axis.** Virtual-tick promotion should run only when the heat passes left the axis short of a fit; a healthy axis with 2+ ticks already caught is fine.

## 3. Fix

All in `ml/p2d/extract.py`.

### 3.A `_needs_axis_fallback` - require a struggling detector AND strong peaks concentrated in the strip

The gate now opens only when all of these hold:

1. the strip has at least 2 label boxes with no strong peak (the original signal),
2. either the max strong peak sits below 0.5 (FRED's missing-tick case), OR it sits in the 0.5-0.6 soft band and the strong pass already caught at least 3 strip labels (dexuseu's "more ticks needed to shrink the OCR window" case),
3. at least half the axis's strong peaks live in the strip (`strong_in_strip * 2 >= n_strong`, skipped when `n_strong == 0`).

### 3.B `_promote_label_only_ticks` - skip when the axis is already fit-ready

Per-axis: if the strong+weak passes already put >= 2 ticks on the axis, don't invent more.
A healthy chart's extra strip boxes stay as `loose_labels` instead of becoming FP ticks.

### 3.C Diagnostic rationale (empirical)

With the proposed gate against the measured diag JSONs:

| | mpl-val xticks fires | mpl-val yticks fires | FRED yticks fires |
| --- | --- | --- | --- |
| round-4-fred gate     | 37/200 | 12/200 | 10/10 |
| round-5 gate          |  1/200 |  2/200 | 10/10 |

Every FRED chart that needed the fallback still fires it; mpl-val's spurious fires are cut 36 of 37 (xticks) and 10 of 12 (yticks).

## 4. Numbers

### 4.1 mpl-val --limit 200 --tta shift

| metric | pre-fred (1832ce4) | round-4-fred (d55bcc7) | round-5 (this branch) |
| --- | --- | --- | --- |
| line_found              | 0.6920 | 0.6725 | **0.6941** |
| line_rms_median_pct     | 0.2824 | 0.2706 | 0.2832 |
| line_rms_p90_pct        | 2.1256 | 2.1233 | 2.1462 |
| peak_err_median_pct     | 1.2937 | 1.3057 | 1.2937 |
| peak_err_env_median_pct | 0.6062 | 0.6119 | 0.6062 |
| marker_recall           | 0.6138 | 0.6022 | 0.6138 |
| xticks_recall           | 0.8971 | 0.9027 | 0.9021 |
| xticks_fp_per_img       | 0.5650 | 1.1900 | **0.6100** |
| yticks_recall           | 0.9032 | 0.9061 | 0.9049 |
| yticks_fp_per_img       | 0.5900 | 0.8550 | **0.6200** |
| calib_x_within_0.5pct   | 0.9050 | 0.8850 | 0.9050 |
| calib_y_within_0.5pct   | 0.8950 | 0.8900 | 0.9000 |

`line_found` is now 0.0021 better than the pre-fred baseline (two series regain cover after the FP ticks that broke their fits are gone).
Tick false-positive counts land within 0.045 (xticks) and 0.030 (yticks) of the pre-fred baseline, well inside the round-4-fred regression bars.

### 4.2 FRED cluster (t5-real --tta shift)

| chart | pre-fred | round-4-fred | round-5 | target range |
| --- | --- | --- | --- | --- |
| fred-cpi-two        | 0.87 | 0.80 | 0.80 | - |
| fred-cpiaucsl-2000  | 0.22 | 0.40 | 0.40 | - |
| fred-dexuseu        | 383  | 0.87 | 0.87 | ~0.9 |
| fred-dgs10-daily    | nan  | 1.63 | 1.63 | ~1.6 |
| fred-fedfunds-small | nan  | 2.96 | 2.90 | ~3   |
| fred-gdp-log        | 5.62 | 0.90 | 0.44 | ~0.9 |
| fred-houst-thick    | 71.7 | 5.12 | 5.12 | ~5   |
| fred-m2sl-log       | 6.24 | 1.04 | 0.60 | ~1   |
| fred-mortgage-tiny  | nan  | 4.19 | 4.19 | ~4   |
| fred-sp500          | nan  | 0.88 | 0.88 | ~0.9 |
| fred-oil-2015       | 2.44 | 2.36 | 2.36 | - |
| fred-payems         | 0.48 | 0.48 | 0.48 | - |
| fred-t10y2y         | 3.47 | 3.47 | 3.47 | - |
| fred-unrate         | 2.65 | 2.65 | 2.65 | - |
| fred-unrate-civpart | 1.52 | 0.70 | 0.70 | - |
| fred-unrate-dark    | 1.92 | 1.92 | 1.92 | - |

Every FRED chart holds its round-4-fred value; `fred-gdp-log` (0.90 -> 0.44) and `fred-m2sl-log` (1.04 -> 0.60) improve, because the stricter weak-peak gate stops a stray weak peak outside the strip from pulling the fit.
t5-real aggregates (`found (cover >= 80%)` 65%, `within 1%` 50%, `failed` 13) match or beat round-4-fred (65% / 48% / 13).

### 4.3 Byte-identical scoreboards

| scoreboard | round-5 vs round-4-fred reference | notes |
| --- | --- | --- |
| data/plotly-v1 --limit 150 --tta shift | byte-identical | 0 differing lines, numbers match 0.1958 / 0.2467 / 0.2133 |
| eval_corpus                            | byte-identical | 0 differing lines, median 0.071% / worst 0.563% / failed 0 |
| examples/real --tta shift              | 4 of 6 lines identical, 2 lines differ (env non-determinism) | 03-women-men and 04-hits differ versus the r4-fred reference regardless of this branch's changes; versus my local d55bcc7 baseline, round-5 strictly removes FP ticks (`190` and a duplicate `2011` on 05-retail-sales, `0^7` + `0^1` extras on 02-microprocessor) |

`out/r5-mpl/final/{plotly.txt,corpus.txt,real.txt}` compared with `../../PLOT2DATA-r4/fred/ml/out/r4-fred/scores/*-after.txt`.

### 4.4 pytest

**131 passed** (127 original + 4 new, 1 updated).

New tests in `tests/test_core.py`:

- `test_needs_axis_fallback_blocked_when_strong_peak_is_confident`
- `test_needs_axis_fallback_soft_band_requires_three_strong_hits`
- `test_needs_axis_fallback_blocked_when_strong_peaks_scatter_outside_strip`
- `test_promote_label_only_ticks_skipped_when_axis_has_enough_ticks`

Updated: `test_needs_axis_fallback_fires_only_when_label_boxes_are_mostly_unclaimed` uses a weak (0.4) rather than borderline (0.5) peak to express the "FRED missing-tick case" expectation under the new score gate.

## 5. Gate chosen vs the task's menu

The task listed four candidate gate shapes. The shipping version is a **union of A, B, C and D**:

- **A** (count of strong ticks): applied via `_promote_label_only_ticks`'s `len(axis_ticks) < 2` check.
- **B** (max strong peak is weak): applied via `max_strong < 0.5 or (max_strong < 0.6 and strong_in_strip >= 3)` in `_needs_axis_fallback`.
- **C** (cross-strip metric): applied via `strong_in_strip * 2 >= n_strong` in `_needs_axis_fallback`.
- **D** (virtual-tick as second-stage fallback): approximated by the A gate on `_promote_label_only_ticks`, which is logically equivalent to "fit_axis would still have >= 2 inliers".

A single gate on its own is not enough: A alone keeps 0.25 extra xticks_fp, A+B still fires on sparse 2-tick charts (`9000118`), A+C still fires on dexuseu-size strips.
Taken together, the three gates cover 46 of 49 mpl-val false fires without touching a single FRED fire.

## 6. Files touched

- `ml/p2d/extract.py` (gates in `_needs_axis_fallback` and `_promote_label_only_ticks`)
- `ml/tests/test_core.py` (1 updated test, 4 new tests)
- `ml/teams/round5-mpl-val-tighten/REPORT.md` (this file)
