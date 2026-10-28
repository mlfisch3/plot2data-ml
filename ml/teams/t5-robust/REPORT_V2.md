# t5-robust V2: Chart.js in training

Optional second submission on `team/t5-robust-chartjs`, built on top of the V1 submission (`bd6a491` on `team/t5-robust`): same pipeline (native pass + class-aware ROI + grid-ghost drop + multiplier box + log-decade + `--tta shift`), but the network is fine-tuned once more with Chart.js charts in the training mix.
V1 (bd6a491) remains the primary submission; this report describes a strictly-further step on `team/t5-robust-chartjs`.

## 1. Claim

The hypothesis: Chart.js is a renderer no training set contained; its tick-label convention differs from matplotlib's (em-box centred vs. digit centred), its gridlines use a greyer stroke, and its layout places labels against the plot edges rather than centred on anchors.
V1 handles Chart.js through runtime machinery (frame-independent snap, TTA shift, grid-ghost drop); V2 teaches the network the convention directly from 4,000 Chart.js charts (`data/t5-chartjs`, Chrome-rendered through the Chart.js API, seeds 15,100,000+).

Expected effect: fix the `nogrid` 1-pixel label bias on y-axes (`corpus/linear-single-nogrid` 0.19% -> target 0.06%), tighten the chartjs-val probe set calibration, close the `frame_found` 0.89 -> ~0.93 gap on Chart.js charts.
Risk: a drift on matplotlib convention; measured below.

TBD: numbers once `runs/t5-chartjs/best.pt` completes.

## 2. Scoreboard (TBD)

| metric | base (v3/6b313e9) | V1 submission (bd6a491) | V2 submission (t5-chartjs) |
| --- | --- | --- | --- |
| mpl-val line_rms_median_pct | 0.441 | 0.280 | TBD |
| mpl-val marker_precision | 0.640 | 0.719 | TBD |
| plotly-v1 line_rms_median_pct | 0.250 | 0.234 | TBD |
| plotly-v1 marker_precision | 0.772 | 0.852 | TBD |
| corpus median | 0.067% | 0.072% | TBD |
| corpus worst | 61.22% | 0.580% | TBD |
| corpus `linear-single-nogrid` | 0.194% | 0.196% | TBD (target <0.10%) |
| chartjs-val line_rms_median_pct | 0.343 | 0.299 | TBD |
| examples/real 03 x axis | log | linear | TBD |

## 3. Implementation

Branch `team/t5-robust-chartjs` off `bd6a491`.
Training: `runs/t5-chartjs/best.pt` fine-tuned from `runs/t5-zoom/best.pt` on `data/mpl-v1 + data/mpl-v2 + data/plotly-train-x8 + data/t5-chartjs` (67,385 samples), `--iters 3000`, `--zoom 0.35`, `--eval-every 1000`, serialised through the GPU lock.
No code changes from V1.
Runtime remains native pass + `--tta shift`.

## 4. Comparison to V1 (TBD)

Will fill in once numbers land.
Chart.js convention is now trained in: expect y-tick label bias to drop and the `nogrid` corpus case to collapse below 0.1%.
If a matplotlib or plotly regression appears, V2 is held and V1 (bd6a491) remains the submission.

## 5. Status

- Training launched at `out/t5/chartjs-train.sh`, log `out/t5/chartjs-train.log`.
- Expected 90-150 min on the shared GPU (zoom finetune took 140 min).
- Evaluation script `out/t5/chartjs-eval.sh` runs the four scoreboard sets plus `data/t5-chartjs-val` at submission config (`--tta shift`) once training lands.
