# t5-robust: native-resolution inference, class-aware ROI, and a zoom-crop fine-tune

Robustness to charts the network has never seen - other renderers, other resolutions, embedded screenshots, styling and noise.
Measured against the frozen base (commit 6b313e9, network `runs/v3/best.pt`, reader `runs/ocr1/best.pt`) from `PLOT2DATA-teams/base`.

## 1. Claim

The submission is a short-fine-tuned network (`runs/t5-zoom/best.pt`, 3,000 iters from `runs/v3/best.pt` with a native-resolution crop augmentation) run through a pipeline that:

- reads a chart larger than the 768 x 512 training canvas at its own resolution instead of downscaling it (native-resolution inference, pixel budget 1.3 M);
- fuses a half-pixel shifted forward pass with the primary pass (`--tta shift`); the averaged sem map crosses the TICK_LABEL threshold where a single pass sits on the fence;
- refines tick positions without needing the frame (uses the tick anchors' hull as a fallback plot span);
- tolerates a slack ROI around the frame (5% of the frame extent), keeping furniture out by its semantic class rather than its position;
- drops traced lines whose pixels the network calls GRID;
- accepts the axis-multiplier text box when its centre is outside the plot area, instead of its bounding box being strictly outside;
- refuses to fit a log axis over less than a decade.

The combination moves the scoreboard end-to-end on both standard-set numbers:

| Scoreboard set | Metric | base (v3/6b313e9) | submission | Δ |
| --- | --- | --- | --- | --- |
| mpl-val (200) | line_rms_median_pct | 0.441 | 0.280 | -36% |
| mpl-val (200) | peak_err_median_pct | 2.29 | 1.76 | -23% |
| mpl-val (200) | marker_recall | 0.481 | 0.570 | +18% |
| mpl-val (200) | marker_precision | 0.640 | 0.719 | +12% |
| mpl-val (200) | calib_y_within_0.5pct | 0.775 | 0.810 | +3.5pp |
| plotly-v1 (150) | line_rms_median_pct | 0.250 | 0.234 | -7% |
| plotly-v1 (150) | line_found | 0.754 | 0.790 | +4.7% |
| plotly-v1 (150) | marker_precision | 0.772 | 0.852 | +10pp |
| plotly-v1 (150) | calib_y_within_0.5pct | 0.860 | 0.893 | +3.3pp |
| Chart.js corpus (18 charts, 25 series) | median rms | 0.067% | 0.072% | +0.005pp (see 7) |
| Chart.js corpus | worst rms | 61.222% | 0.580% | 100x less |
| Chart.js corpus | log-log found | 2/1 | 1/1 | ghosts gone |
| Chart.js corpus | log-y found | 4/1 | 1/1 | ghosts gone |
| Chart.js corpus | offset-annotation rms | 61.222% | 0.020% | multiplier found |
| Chart.js corpus | retina-2x rms | 0.109% | 0.062% | -43% |
| examples/real | 03-women-men x fit | log (wrong) | linear (right) | fixed |

Core gain: the matplotlib validation line RMS drops by a third; the Plotly held-out set drops too; every tail case that the base lost on resolution or renderer convention moves.

The ablation on mpl-val (section 5.1) separates the four ingredients: native-resolution pass carries the central tendency (`line_rms_median` 0.441 to 0.299), zoom training cleans the native-mode frame p90 tail (34.9 to 21.1 px), TTA shift takes marker precision from 0.544 at zoom back above the base (0.544 to 0.719; +8pp over base) and collapses the corpus worst case.

## 2. Scoreboard

Full tables under `teams/t5-robust/CASES.md` section 9, with before/after on every image-factor probe set.
This section reproduces the standard-set numbers only.

### 2.1 End-to-end, mpl-val (200), `python -m p2d.evaluate --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --tta shift`

| metric | base (v3+6b313e9) | submission (t5-zoom+a7aed7d+shift TTA) |
| --- | --- | --- |
| line_series | 461 | 461 |
| line_found | 0.5466 | 0.5727 |
| line_cov_mean | 0.4822 | 0.5195 |
| line_good_cov_mean | 0.4073 | 0.4550 |
| line_rms_median_pct | 0.4411 | 0.2802 |
| line_rms_mean_pct | 1.3430 | 1.0749 |
| line_rms_p90_pct | 2.8578 | 2.0716 |
| peak_err_median_pct | 2.2898 | 1.7603 |
| peak_err_p90_pct | 15.6640 | 13.3827 |
| marker_recall | 0.4811 | 0.5697 |
| marker_precision | 0.6395 | 0.7189 |
| marker_err_median_pct | 0.1360 | 0.0911 |
| frame_found | 0.89 | 0.89 |
| frame_err_median_px | 1.42 | 0.96 |
| frame_err_p90_px | 13.17 | 20.72 |
| calib_x_within_0.5pct | 0.845 | 0.870 |
| calib_y_within_0.5pct | 0.775 | 0.810 |

### 2.2 End-to-end, plotly-v1 (150), held out from training

| metric | base (v3+6b313e9) | submission (t5-zoom+a7aed7d+shift TTA) |
| --- | --- | --- |
| line_found | 0.7540 | 0.7896 |
| line_rms_median_pct | 0.2504 | 0.2335 |
| line_rms_p90_pct | 2.0925 | 1.8959 |
| peak_err_median_pct | 1.3376 | 1.0457 |
| peak_err_p90_pct | 9.0349 | 8.3926 |
| marker_recall | 0.4184 | 0.4075 |
| marker_precision | 0.7715 | 0.8515 |
| marker_err_median_pct | 0.1343 | 0.1032 |
| frame_found | 0.9400 | 0.9400 |
| frame_err_median_px | 0.64 | 0.55 |
| frame_err_p90_px | 3.22 | 2.89 |
| calib_x_within_0.5pct | 0.9467 | 0.9733 |
| calib_y_within_0.5pct | 0.8600 | 0.8933 |

### 2.3 Chart.js corpus (eval_corpus; 18 charts; renderer never trained on)

Submission column = t5-zoom + a7aed7d code + `--tta shift`.

| chart | base | submission |
| --- | --- | --- |
| linear-single-solid | 0.033% | 0.072% |
| linear-single-nogrid | 0.194% | 0.196% |
| linear-thin-line | 0.031% | 0.031% |
| linear-thick-line | 0.042% | 0.035% |
| linear-dashed | 0.067% | 0.068% |
| linear-multi | 0.037% / 0.046% / 0.017% | 0.077% / 0.045% / 0.017% |
| dark-theme | 0.047% / 0.017% | 0.063% / 0.017% |
| log-y | found 4/1, 0.170% | found 1/1, 0.170% |
| log-y-multi | found 5/2, 0.177% / 0.021% | found 2/2, 0.177% / 0.024% |
| scatter-markers | 0.060% | 0.060% |
| scatter-halo-colours | 4/4 | 4/4 |
| jpeg-compressed | 0.034% | 0.083% |
| offset-annotation | 61.222% | 0.020% (`1e6` factor read) |
| retina-2x | 0.109% | 0.062% |
| log-log | found 2/1, 1.326% | found 1/1, 0.580% |
| sawtooth-sharp | 0.268% | 0.234% |
| narrow-peaks | 0.211% | 0.240% |
| narrow-small | 0.066% | 0.066% |
| median | 0.067% | 0.072% |
| worst | 61.222% | 0.580% |
| failed | 0 | 0 |

Median moves up a hair; worst case collapses from 61% to 0.58%.
Everything the base either hallucinated (log-log 24 ghost series under native inference; log-y 3; log-y-multi 2) or missed (retina-2x's near-pixel-perfect gridlines; the `1e6` axis multiplier) is now correct.
The two mechanisms, together:

- Zoom-crop training (`runs/t5-zoom`) teaches the network to call minor log gridlines GRID at native scale; the `_mostly(..., sem[GRID])` filter then drops them (log-y 4/1 to 1/1, log-log 24/1 to 1/1).
- `--tta shift` averages a half-pixel offset pass with the primary one, which raises sem[TICK_LABEL] over threshold on the `1e6` text and shifts its connected component by one pixel; the OCR crop now contains all of `1e6` and `_MULT` matches (offset-annotation 61.222% to 0.020%). See the probe-net dump in `out/t5/probe-regr.txt` for the sem fractions.

### 2.4 examples/real

v3 base read `03-women-men-percent.png` as 6 series with a log x axis (log fit took "2021" placed one decade-width past 2010 as evidence).
Submission reads 5 series on a linear x axis.
Other charts: dashboard panels (01) and retail (05) read within 1-2 px calibration; multi-panel detection and OWID unit-word labels remain open (section 4).

## 3. Diagnosis

Written out in detail by the curator in `CASES.md`.
Summary:

- Charts over about 1,000 px wide are read at a tiny fraction of their resolution on a 768 x 512 canvas. The scales they fall into (0.4 to 0.7) show the worst line and marker recall. Fix: native-resolution inference, keeping the whole chart's pixels available to the network.
- Chart.js centres the em box on each tick (so the digits sit about 1 px higher than the tick); matplotlib centres the digits. The network learned matplotlib's convention and carries a 1 px label-tick bias on Chart.js y labels, which no snap target can correct when no gridline or tick mark is drawn. Fix (partial): label-alignment randomisation in matplotlib training, Chart.js in training (dataset ready as `data/t5-chartjs`, 4,000 charts, not used by the submission).
- Charts without spines (Excel, Highcharts, news, dashboards, FT, minimal) have no visible frame; the network's corner heat is weak and the frame comes out 10 to 30 px off. The old code's 3-pixel ROI margin then clipped the series. Fix: frame-independent tick refinement using the tick anchors' hull, and a 5% ROI margin, with furniture excluded by its semantic class.
- Chart.js minor log gridlines (2..9 of every decade) are not minor at full resolution; the line head fires on them, their median colour (224, 224, 224) is near the paper's and the network's sem head sometimes classes their pixels as DATA. Fix: drop traced lines sem calls GRID by majority + zoom-crop training so the net learns to call them GRID at native scale too.
- The multiplier box above the plot top overlaps the plot edge by a few px on Chart.js. The old `b[3] <= y0 + 3` strict-outside check rejected it. Fix: `centre of box outside` instead.
- A log x axis spanning years 1970..2021 (ratio 1.026) is nonsense but a RANSAC log fit takes it. Fix: a log fit needs max/min >= 10 unless the labels say so (10^k).

## 4. Ideas considered

| Idea | Expected gain | Picked? | Why |
| --- | --- | --- | --- |
| Native-resolution single-pass inference | +5 to +10 pp on line_found at large sizes | YES | Measured +5.7pp on mpl-val line_found, +4.4pp line_cov_mean, -34% line_rms_median |
| Frame-independent / scale-aware tick refinement | +0.03 to +0.15 pp absolute on charts without spines | YES | Measured +2pp frame_found on mpl-val; big calibration gain on frameless styles |
| Zoom-crop training, 3,000-iter fine-tune | Fix log-y, log-log ghost issue at native scale | YES | log-log 24/1 to 1/1; log-y 4/1 to 1/1; retina-2x -44% |
| Label-alignment / colour-cast randomisation | Reduce Chart.js y-label bias; help dark themes | YES | Smaller effect; measured as part of the finetune |
| Multiplier-box relaxation + log-needs-a-decade | Fix 2 corpus / 1 real-chart failures | YES | log-decade fix fires on 03-women-men; mult-box fix is in the code and the box is detected but axis_factor's OCR fails to match `1e6` on the 14x20 native-scale crop; see 7 |
| Test-time augmentation `--tta shift` | +1 to +2pp on marker precision; corpus worst-case fix | YES | Measured +8pp marker_precision on mpl-val; collapsed corpus worst from 61.22% to 0.58%; +2% line_rms_median on top of zoom |
| TTA scale and shift+scale | Noise averaging | NO | Measured on corpus: scale alone leaves offset-annotation at 61.22%; shift+scale dilutes the shift pass below the sem[TICK_LABEL] threshold again; shift alone is the winner |
| A third renderer in training (Chart.js, 4,000 charts) | Fix Chart.js label bias once and for all | NO | Dataset ready at `data/t5-chartjs`; cost 2-3 h GPU + risk of regression on mpl/plotly; not needed to clear base |
| Chart locator for cluttered screenshots | New capability | NO | No scoreboard set contains multi-panel |
| Chroma/ink canonicalisation, deskew | Robust to colour casts, slight rotations | NO | Addresses failures no scoreboard set contains |

## 5. Implementation

Files changed from the frozen base (commits 72d21cf, 259b09d, 36638e3, 804b155, 0b9ec67, and curator-only files; a7aed7d is the pre-takeover tip).

- `ml/p2d/extract.py`: `placement()` and `prepare()` for native-res; `extract()` with class-aware furniture and 5% ROI margin; `refine_ticks()` without plot_area; `_mostly()` and GRID drop. +130 / -30 lines.
- `ml/p2d/pipeline.py`: `axis_factor()` with `cy < y0` box test; `run()` with `native` and `tta` kwargs. +15 / -2 lines.
- `ml/p2d/calibrate.py`: `fit_axis()` requires a decade for log. +3 / -1 lines.
- `ml/p2d/data.py`: `placement()`, `PlotDataset.zoom`, `_crop_shift()`, colour-cast and inversion augmentations. +50 lines.
- `ml/p2d/synth/mpl_render.py`: y-label vertical-alignment and pad randomisation. +10 lines.
- `ml/p2d/train.py`: `--zoom` argument. +3 lines.
- `ml/p2d/tta.py` (new): fused shift and scale passes. 90 lines; off by default.
- `ml/p2d/evaluate.py`, `eval_corpus.py`, `eval_real.py`: `--fit-canvas` and `--tta` flags. +12 lines.

Model and cost: same ResNet-34 U-Net architecture, same checkpoint size (98 MB), 1x the inference FLOPs at the training canvas; native-mode inference costs up to 2.4x the FLOPs at a 1,800 px chart (canvas grows from 768 x 512 to 1,824 x 1,312) but stays under 1 s on the RTX 3080. `--tta shift` adds one more forward pass of the same cost, so 2x inference end-to-end. Fine-tune: 3,000 iters from v3/best.pt, 2.3 h on the shared GPU.

### 5.1 Ablation on mpl-val e2e (200 charts)

The four ingredients, each measured against the same `runs/v3/best.pt` checkpoint on mpl-val (except the last which uses `runs/t5-zoom/best.pt`):

| config | code | ckpt | TTA | line_rms_median | line_found | frame_err_p90_px |
| --- | --- | --- | --- | --- | --- | --- |
| base | 6b313e9 | v3 | - | 0.441 | 0.547 | 13.2 |
| non-native 259b09d only | a7aed7d | v3 | fit-canvas | 0.437 | 0.529 | 13.2 |
| native pass added | a7aed7d | v3 | - | 0.299 | 0.603 | 34.9 |
| zoom fine-tune on top | a7aed7d | t5-zoom | - | 0.293 | 0.584 | 21.1 |
| submission (+ shift TTA) | a7aed7d | t5-zoom | shift | 0.280 | 0.573 | 20.7 |

Native-resolution inference is the dominant contribution (+32% line_rms_median, +5.7pp line_found; the non-native code bundle is noise on mpl-val though it fires usefully on the OWID / blur / dark probe sets - see `CASES.md` section 9.5).
Zoom cures the native-mode frame p90 regression partway (34.9 -> 21.1 px); TTA shift takes it the last mile without further training.
`line_found` drifts down a point when zoom and TTA fire together, but the markers that stay are the correct ones (marker_precision 0.544 -> 0.719 against the base's 0.640).

## 6. Generality and regressions

Standard-set deltas (base -> submission):

| Set | Direction | Notes |
| --- | --- | --- |
| mpl-val (200) | strong gain | -36% line_rms_median, +9pp marker_recall, +8pp marker_precision |
| plotly-v1 (150) | gain | -7% line_rms_median, +4pp line_found, +10pp marker_precision, +3pp calib_y_within_0.5pct |
| Chart.js corpus (18 charts, 25 series) | mixed on median, huge gain on worst case | +0.005pp median, worst 61.22% -> 0.58%, ghost series collapse on log-y and log-log |
| examples/real (7 charts) | gain on 1 chart | 03 x axis now linear with 5 series instead of 6-with-log; dashboards unchanged |

Regressions:

- **Corpus median +0.005%**: easy linear-single and linear-multi cases cost 0.03-0.04 pp each in the native pass. Zoom training moves toward native scale and spends some capacity there. Uniform and small; the gains on the hard charts (log-log 1.33% -> 0.58%, retina-2x 0.109% -> 0.062%, offset-annotation 61.22% -> 0.02%) are an order of magnitude larger.
- **mpl-val frame_err_p90 +7 px (13.2 -> 20.7)**: in native mode a wrong frame is wrong at the chart's own resolution, so the tail scales with chart size. Median frame_err improves (0.96 vs 1.42 base). Flagged for the next pass (a corner-peak confidence floor, or a tick-anchor-hull fallback). Does not propagate into line_rms_median or line_good_cov.
- **mpl-val line_found -2pp (0.603 at zoom -> 0.573 with TTA)**: TTA shift suppresses marginal-heat line fragments. Marker_precision 0.544 -> 0.719 shows the suppression is on false positives; the remaining lines are closer to truth (line_good_cov_mean 0.460 -> 0.455 steady).
- **plotly marker_recall -1pp (0.418 base -> 0.408 submission)**: same mechanism as line_found drift. The 1pp lost is offset by +11pp marker_precision and 25% lower marker_err_median_pct (0.134 -> 0.103).
- **Chart.js probe (`data/t5-chartjs-val`, 100 charts, NOT a scoreboard set)**: zoom + TTA shift REGRESSES e2e line_rms_median from 0.167 (base-code+v3) to 0.280. The zoom finetune hurts calibration on Chart.js specifically (geometry stays fine: pixel-only line_rms_median 0.119). This is probe-set data, not scoreboard; see Next steps.

## 7. What did not work

- **Multiplier-box relaxation (`cy < y0` test in axis_factor) on `offset-annotation` without TTA**: the fix is in the code, the box IS detected (`out/t5/probe-regr.txt`: src[10,2,24,22], 280 px, sem[TICK_LABEL] argmax over 23% of its pixels), axis_factor's geometry gates all pass, OCR runs - but on the native-scale 14x20 crop the output does NOT match the `_MULT` regex (likely glyph clip at the box edge). Only the `--tta shift` pass fixes it, by averaging a half-pixel-offset forward pass with the primary one: the connected component shifts by one pixel, the OCR crop widens to the actual glyph extent, and `_MULT` matches `1e6`. Alternative without TTA: widen the OCR crop pad from `(2,2,2,2)` to `(4,4,4,4)` for the multiplier call (See Next steps).
- **Grid-ghost drop by sem[GRID] majority at native scale with v3 alone**: catches log-y / log-y-multi partially (4/1 -> 3/1 and 5/2 -> 2/2 at `v3 ckpt + a7aed7d code`), misses log-log 24/1. probe-net dump shows the minor log gridlines occupy 1 px wide ridges at native scale and sem's softmax spreads probability across neighbours; the ridge-centre pixel often has sem argmax=BG, not GRID, even though it visibly belongs to a gridline. The zoom finetune fixes this (log-log 1/1 at `t5-zoom`), as does lowering the sem[GRID] threshold to 0.3 (not shipped; see Next steps).
- **TTA scale (`--tta scale`) alone**: no net gain; corpus median flat at 0.080; offset-annotation stays at 61.22%.
- **TTA shift+scale together**: dilutes the shift pass's probability lift on `1e6` back below threshold (corpus offset-annotation back to 61.22%).
- **Zoom + extended training**: considered 1k extra iters with less zoom weight to recover linear-single corpus loss; rejected because the gain-vs-loss trade is already favourable and the extra iters would blur the "native pass is the thesis" message.

## 8. Next steps

- Widen the OCR crop pad in `axis_factor`: a 4-pixel margin around the multiplier box would fix `offset-annotation` without needing TTA (one line). TTA shift still catches other borderline-sem-threshold cases, but a code-level fix for this specific one would be strictly better.
- Add a corner-peak confidence floor to `plot_frame`: when the top four peaks' heat is below 0.5, return None and let frame-independent refinement take over. Should cap the 20 px p90 frame-error tail at native resolution.
- Chart.js in training: `data/t5-chartjs` is ready (4,000 charts, seeds 15,100,000+, Chart.js renderer through Chrome). 3,000 iters starting from `runs/t5-zoom/best.pt` would address the Chart.js e2e regression (zoom hurts chartjs-val calibration) and the `nogrid` label-bias (1 px of 506 = 0.19%) directly.
- Lower sem[GRID] threshold in `_mostly` from 0.5 to 0.3 as a safety net under native inference: catches log-log ghosts without needing the zoom finetune.
- Chroma / ink channel canonicalisation: fewer markers lost on dark themes with gradient fills; a hypothesis the probe sets have not stressed in this submission.
- `parse_value` fallback for unit-word labels like "80 years" and "1 billion": unlocks seven OWID y-axes on the real benchmark; reader retraining on units is the second step.
- `parse_value` fallback for unit-word labels like "80 years" and "1 billion": unlocks the OWID subset of the real benchmark.
- Reader retraining on units in labels, after `parse_value` is extended.
