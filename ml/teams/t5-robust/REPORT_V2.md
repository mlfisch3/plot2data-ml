# t5-robust V2: Chart.js in training

Optional second submission on `team/t5-robust-chartjs`, built on top of the V1 submission (`bd6a491` on `team/t5-robust`): same pipeline (native pass + class-aware ROI + grid-ghost drop + multiplier box + log-decade + `--tta shift`), but the network is fine-tuned once more with Chart.js charts in the training mix.
V1 (bd6a491) remains the primary submission; this report describes a strictly-further step on `team/t5-robust-chartjs`.

## 1. Claim

The hypothesis: Chart.js is a renderer no training set contained; its tick-label convention differs from matplotlib's (em-box centred vs. digit centred), its gridlines use a greyer stroke, and its layout places labels against the plot edges rather than centred on anchors.
V1 handles Chart.js through runtime machinery (frame-independent snap, TTA shift, grid-ghost drop); V2 teaches the network the convention directly from 4,000 Chart.js charts (`data/t5-chartjs`, Chrome-rendered through the Chart.js API, seeds 15,100,000+).

Expected effect: fix the `nogrid` 1-pixel label bias on y-axes (`corpus/linear-single-nogrid` 0.19% -> target 0.06%), tighten the chartjs-val probe set calibration, close the `frame_found` 0.89 -> ~0.93 gap on Chart.js charts.
Risk: a drift on matplotlib convention; measured below.

TBD-VERDICT

## 2. Training

Branched `team/t5-robust-chartjs` off `bd6a491` (V1 submission).

Fine-tune from `runs/t5-zoom/best.pt` on `data/mpl-v1 + data/mpl-v2 + data/plotly-train-x8 + data/t5-chartjs` (67,385 samples; the Chart.js portion is 4,000 = 5.9% of the mix), 3,000 iters, `--zoom 0.35`, `--eval-every 1000`, batch 8, lr 6e-4 cosine, ResNet-34 encoder, serialised through the GPU lock.
No code changes from V1.
Runtime remains native pass + `--tta shift`.

Training trajectory (val loss on `data/mpl-val`):

| iter | train loss | val loss |
| --- | --- | --- |
| V1 (t5-zoom) 3000 | ~2.40 | 2.49 |
| V2 (t5-chartjs) 1000 | 3.01 | 3.21 |
| V2 (t5-chartjs) 2000 | 2.74 | 2.83 |
| V2 (t5-chartjs) 3000 | 2.51 | 2.59 |

Val is measured on matplotlib only, so a +0.10 nats offset at 3000 iters is expected: V2 pays matplotlib capacity to also fit Chart.js.
Whether that offset shows on the scoreboard, and whether the Chart.js side pays for it, is section 3.

## 3. Scoreboard

Full numbers under `teams/t5-robust/CASES.md` section 9 (V1) and this file (V2).

### 3.1 End-to-end, mpl-val (200), `--tta shift`

| metric | base (v3+6b313e9) | V1 (bd6a491) | V2 (t5-chartjs) | V2-V1 |
| --- | --- | --- | --- | --- |
| line_found | 0.5466 | 0.5727 | TBD | TBD |
| line_rms_median_pct | 0.4411 | 0.2802 | TBD | TBD |
| line_rms_p90_pct | 2.8578 | 2.0716 | TBD | TBD |
| peak_err_median_pct | 2.2898 | 1.7603 | TBD | TBD |
| marker_recall | 0.4811 | 0.5697 | TBD | TBD |
| marker_precision | 0.6395 | 0.7189 | TBD | TBD |
| frame_found | 0.89 | 0.89 | TBD | TBD |
| frame_err_median_px | 1.42 | 0.96 | TBD | TBD |
| calib_x_within_0.5pct | 0.845 | 0.870 | TBD | TBD |
| calib_y_within_0.5pct | 0.775 | 0.810 | TBD | TBD |

### 3.2 End-to-end, plotly-v1 (150), `--tta shift`

| metric | base | V1 | V2 | V2-V1 |
| --- | --- | --- | --- | --- |
| line_found | 0.7540 | 0.7896 | TBD | TBD |
| line_rms_median_pct | 0.2504 | 0.2335 | TBD | TBD |
| peak_err_median_pct | 1.3376 | 1.0457 | TBD | TBD |
| marker_recall | 0.4184 | 0.4075 | TBD | TBD |
| marker_precision | 0.7715 | 0.8515 | TBD | TBD |
| frame_found | 0.9400 | 0.9400 | TBD | TBD |
| calib_x_within_0.5pct | 0.9467 | 0.9733 | TBD | TBD |
| calib_y_within_0.5pct | 0.8600 | 0.8933 | TBD | TBD |

### 3.3 Chart.js corpus (eval_corpus; 18 charts, held-out renderer, `--tta shift`)

| chart | base | V1 | V2 |
| --- | --- | --- | --- |
| linear-single-solid | 0.033% | 0.072% | TBD |
| linear-single-nogrid | 0.194% | 0.196% | TBD |
| linear-thin-line | 0.031% | 0.031% | TBD |
| linear-thick-line | 0.042% | 0.035% | TBD |
| linear-dashed | 0.067% | 0.068% | TBD |
| linear-multi | 0.037 / 0.046 / 0.017 | 0.077 / 0.045 / 0.017 | TBD |
| dark-theme | 0.047 / 0.017 | 0.063 / 0.017 | TBD |
| log-y | found 4/1, 0.170% | 1/1, 0.170% | TBD |
| log-y-multi | 5/2, 0.177 / 0.021 | 2/2, 0.177 / 0.024 | TBD |
| scatter-markers | 0.060% | 0.060% | TBD |
| scatter-halo-colours | 4/4 | 4/4 | TBD |
| jpeg-compressed | 0.034% | 0.083% | TBD |
| offset-annotation | 61.222% | 0.020% | TBD |
| retina-2x | 0.109% | 0.062% | TBD |
| log-log | 2/1, 1.326% | 1/1, 0.580% | TBD |
| sawtooth-sharp | 0.268% | 0.234% | TBD |
| narrow-peaks | 0.211% | 0.240% | TBD |
| narrow-small | 0.066% | 0.066% | TBD |
| **median** | 0.067% | 0.072% | TBD |
| **worst** | 61.222% | 0.580% | TBD |
| **failed** | 0 | 0 | TBD |

### 3.4 Chart.js probe (`data/t5-chartjs-val`, 100 charts, `--tta shift`)

| metric | base | V1 | V2 | V2-V1 |
| --- | --- | --- | --- | --- |
| line_rms_median_pct (all / simple) | 0.343 / 0.285 | 0.299 / 0.260 | TBD | TBD |
| line_found | 0.773 | 0.784 | TBD | TBD |
| peak_err_median_pct (all / simple) | 0.636 / 0.408 | 0.494 / 0.271 | TBD | TBD |
| marker_precision | 0.813 | 0.873 | TBD | TBD |
| yticks_err_median_px | 0.751 | 0.690 | TBD | TBD |
| frame_found | 0.920 | 0.890 | TBD | TBD |
| frame_err_p90_px | 26.8 | 16.7 | TBD | TBD |
| calib_y_within_0.5pct | 0.84 | 0.81 | TBD | TBD |

### 3.5 Real-chart benchmark (`data/t5-real`, 30 charts, 60 series, `--tta shift`)

| metric | base (v3) | V1 | V2 | V2-V1 |
| --- | --- | --- | --- | --- |
| found (cov>=80%) | 67% | 63% | TBD | TBD |
| median rms (%) | 1.86 | 0.75 | TBD | TBD |
| median rms of found | 1.99 | 0.65 | TBD | TBD |
| within 1% | 28% | 42% | TBD | TBD |
| within 0.5% | 25% | 32% | TBD | TBD |
| failed | 15 | 14 | TBD | TBD |

### 3.6 examples/real (hand-measured; `--tta shift`)

| chart | V1 | V2 |
| --- | --- | --- |
| 03-women-men-percent | 5 series linear x | TBD |
| 01-dashboard panels / 05 retail | within 1-2 px | TBD |

### 3.7 Resolution probe sets (`data/t5-dpr{1,2,3}`, 100 charts each at 1x/2x/3x DPR, `--tta shift`)

Simple-charts split (same mpl seeds at three device-pixel-ratios).

| set | metric | base (v3) | V1 submission | V2 submission | V2-V1 |
| --- | --- | --- | --- | --- | --- |
| dpr1 | line_rms_median_pct | 0.233 | TBD | TBD | TBD |
| dpr1 | marker_recall | 0.451 | TBD | TBD | TBD |
| dpr1 | calib_y_within_0.5pct | 0.820 | TBD | TBD | TBD |
| dpr2 | line_rms_median_pct | 0.221 | 0.148 | TBD | TBD |
| dpr2 | marker_recall | 0.309 | 0.324 | TBD | TBD |
| dpr2 | calib_y_within_0.5pct | 0.690 | 0.770 | TBD | TBD |
| dpr3 | line_rms_median_pct | 0.217 | TBD | TBD | TBD |
| dpr3 | marker_recall | 0.274 | TBD | TBD | TBD |
| dpr3 | calib_y_within_0.5pct | 0.640 | TBD | TBD | TBD |

### 3.8 Image-factor probe sets (same 100 mpl seeds, one factor changed, `--tta shift`)

| set | metric | base (v3) | V1 submission | V2 submission | V2-V1 |
| --- | --- | --- | --- | --- | --- |
| blur | line_rms_median_pct | 0.228 | 0.174 | TBD | TBD |
| blur | marker_precision | 0.668 | 0.792 | TBD | TBD |
| dark | line_rms_median_pct | 0.294 | TBD | TBD | TBD |
| dark | calib_y_within_0.5pct | 0.770 | TBD | TBD | TBD |
| clutter | line_rms_median_pct | 0.206 | TBD | TBD | TBD |
| clutter | frame_err_median_px | 5.56 | TBD | TBD | TBD |
| half | line_rms_median_pct | 0.275 | TBD | TBD | TBD |
| up2x | line_rms_median_pct | 0.220 | TBD | TBD | TBD |
| jpeg50 | line_rms_median_pct | 0.218 | TBD | TBD | TBD |
| jpeg30 | line_rms_median_pct | 0.241 | TBD | TBD | TBD |
| skew1 | line_rms_median_pct | 2.400 | TBD | TBD | TBD |

Interpretation (expected): V2 adds Chart.js to the training mix and loses a little matplotlib capacity, so DPR and image-factor numbers (all matplotlib-rendered) should sit at or just under V1's.
The Chart.js-side gain is in section 3.4 (probe) and 3.5 (real).

## 4. Verdict

TBD-VERDICT

## 5. Verification commands

From `ml/`, with `../.venv/bin/activate`, through `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

- `python -m p2d.eval_corpus --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt --tta shift`
- `python -m p2d.eval_real --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt --tta shift`
- `python -m p2d.eval_t5real --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt --tta shift`
- `python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --tta shift`
- `python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt --tta shift`
- `python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t5-chartjs-val --limit 100 --ocr runs/ocr1/best.pt --tta shift`
- `python -m pytest tests/test_core.py`

Branch HEAD: `team/t5-robust-chartjs` (SHA filled on final commit).
V1 submission: `team/t5-robust` at `bd6a491` (untouched, primary submission if V2 regresses).

## 6. Status

- Training completed at 19:38 EDT; `runs/t5-chartjs/best.pt` saved (`log.jsonl` records VAL 3000 loss 2.588).
- Scoreboard eval launched by resumer at 20:08 EDT via `out/t5/chartjs-eval.sh`.
- Numbers and verdict to land once all six measurements complete.
