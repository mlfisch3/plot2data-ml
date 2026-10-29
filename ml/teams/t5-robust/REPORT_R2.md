# t5-robust R2 V3: clutter-aware training

Round-2 fine-tune on top of round-1's integrated V2 checkpoint (`runs/t5-chartjs/best.pt`).
Angle A: a measured regression in V2 - clutter probe +35% rms and +10 px frame_err_median vs V1 - was traced to the sem head confusing outside-chart text and ink with DATA/GRID/TICK_LABEL. V3 adds synthetic cluttered-page samples (chart embedded in a toolbar/sidebar/text page, chart ink keeps its real sem, surrounding stays BG) to the training mix.

## 1. Verdict

TBD after measurement.

## 2. Training

- Branch: `team/t5-robust-r2`
- Init from `runs/t5-chartjs/best.pt` (V2, round-1 integrated base).
- Added data: `data/t5r2-clutter` (3000 mpl, seeds 15,100,000+) and `data/t5r2-clutter-plotly` (1000 plotly, seeds 15,200,000+), both from `probe_t5.make(..., factor='clutter', ...)`. 4000 clutter samples total, 5.6% of a 71,385-sample mix.
- Hyperparams: 3000 iters, batch 8, lr 3e-4 cosine (half of V2's 6e-4, chosen as a gentle fine-tune since the V2 ckpt is already well converged), workers 6, zoom 0.35, encoder resnet34.
- Script: `ml/out/t5r2/train-r2.sh`. Run folder `runs/t5r2-clutter/`. Checkpoint `runs/t5r2-clutter/best.pt`.
- Runtime remains native pass + `--tta shift`.

## 3. Scoreboard

Measured on `--tta shift` with `runs/t5r2-clutter/best.pt` + `runs/ocr1/best.pt`.
V2 numbers come from `REPORT_V2.md` sections 3.1-3.8; base from `v3/best.pt` on the frozen base tree.

### 3.1 Clutter probe (`data/t5-clutter`, 100 mpl charts in cluttered pages)

The primary target. From REPORT_V2.md section 3.8:

| metric | base (v3) | V1 (bd6a491) | V2 (t5-chartjs) | **V3 (t5r2-clutter)** |
| --- | --- | --- | --- | --- |
| line_rms_median_pct | 0.241 | 0.168 | 0.226 | TBD |
| frame_err_median_px | 5.71 | 17.6 | 28.2 | TBD |

Target: V3 drops rms back to or below V1's 0.168 and frame_err back below V1's 17.6 px, without a regression on the other probes below.

### 3.2 Other image-factor probes (`data/t5-{blur,dark,half,up2x,jpeg50,jpeg30,skew1,dpr1,dpr2,dpr3}`)

From REPORT_V2.md section 3.8:

| set | metric | base (v3) | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- | --- |
| blur    | line_rms_median_pct | 0.232 | 0.163 | 0.201 | TBD |
| dark    | line_rms_median_pct | 0.278 | 0.222 | 0.217 | TBD |
| dark    | frame_err_median_px | 1.21 | 1.14 | 0.91 | TBD |
| half    | line_rms_median_pct | 0.213 | 0.223 | 0.191 | TBD |
| up2x    | line_rms_median_pct | 0.271 | 0.099 | 0.097 | TBD |
| up2x    | peak_err_median_pct | 0.332 | 0.170 | 0.143 | TBD |
| jpeg50  | line_rms_median_pct | 0.212 | 0.193 | 0.206 | TBD |
| jpeg30  | line_rms_median_pct | 0.240 | 0.215 | 0.225 | TBD |
| skew1   | line_rms_median_pct | 2.803 | 2.349 | 2.310 | TBD |
| dpr1    | line_rms_median_pct | 0.223 | 0.185 | 0.173 | TBD |
| dpr2    | line_rms_median_pct | 0.249 | 0.088 | 0.109 | TBD |
| dpr3    | line_rms_median_pct | 0.373 | 0.097 | 0.106 | TBD |

Guard: V3 must not regress any of these by more than +0.03 pp rms vs V2.

### 3.3 End-to-end, mpl-val 200, plotly-v1 150, chartjs-val 100

From REPORT_V2.md sections 3.1, 3.2, 3.4:

**mpl-val 200**

| metric | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| line_found | 0.5466 | 0.5727 | 0.5857 | TBD |
| line_rms_median_pct | 0.4411 | 0.2802 | 0.3253 | TBD |
| peak_err_median_pct | 2.2898 | 1.7603 | 1.4138 | TBD |
| marker_recall | 0.4811 | 0.5697 | 0.5616 | TBD |
| frame_found | 0.89 | 0.89 | 0.91 | TBD |
| calib_y_within_0.5pct | 0.775 | 0.810 | 0.800 | TBD |

**plotly-v1 150**

| metric | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| line_found | 0.7540 | 0.7896 | 0.7994 | TBD |
| line_rms_median_pct | 0.2504 | 0.2335 | 0.2299 | TBD |
| peak_err_median_pct | 1.3376 | 1.0457 | 1.0823 | TBD |
| marker_precision | 0.7715 | 0.8515 | 0.8692 | TBD |

**chartjs-val 100** (V2 target, must not regress)

| metric | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| line_rms_median_pct (all / simple) | 0.343 / 0.285 | 0.299 / 0.260 | 0.250 / 0.200 | TBD |
| peak_err_median_pct (all / simple) | 0.636 / 0.408 | 0.494 / 0.271 | 0.427 / 0.229 | TBD |
| yticks_err_median_px | 0.751 | 0.690 | 0.428 | TBD |
| frame_err_p90_px | 26.8 | 16.7 | 5.77 | TBD |

### 3.4 Chart.js corpus (`eval_corpus`)

From REPORT_V2.md section 3.3:

| chart | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| linear-single-nogrid | 0.194% | 0.196% | 0.123% | TBD |
| offset-annotation | 61.222% | 0.020% | 0.019% | TBD |
| log-y-multi | 0.177 / 0.021 | 0.177 / 0.024 | 0.177 / 0.022 | TBD |
| log-log | 1.326% | 0.580% | 0.593% | TBD |
| median | 0.067% | 0.072% | 0.068% | TBD |
| worst | 61.222% | 0.580% | 0.593% | TBD |

### 3.5 Real-chart benchmarks (`data/t5-real`, 30 charts) and examples/real

From REPORT_V2.md section 3.5:

| metric | base (v3) | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| found (cov >= 80%) | 67% | 63% | 60% | TBD |
| median rms (%) | 1.86 | 0.75 | 0.61 | TBD |
| median rms of found | 1.99 | 0.65 | 0.49 | TBD |
| within 1% | 28% | 42% | 48% | TBD |
| failed | 15 | 14 | 15 | TBD |

examples/real: V1 and the integrated reader hold the 5-series linear x on 03-women-men-percent and the 2 lines on 05-retail-sales-monthly.
V2 isolated regressed retail-sales to 1 line; V3 must not reintroduce that.

## 4. Verification commands

From `ml/`, with `../.venv/bin/activate`, through `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

- `bash out/t5r2/eval-r2.sh runs/t5r2-clutter/best.pt r2`
- `python -m pytest tests/test_core.py` (expect 110 passed on `team/t5-robust-r2`)

## 5. Status

- Clutter dataset generated: TBD files in `data/t5r2-clutter`, TBD in `data/t5r2-clutter-plotly`.
- Training run `runs/t5r2-clutter/`: TBD iters.
- Measurement complete: TBD.
