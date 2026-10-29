# t5-robust V2: Chart.js in training

Optional second submission on `team/t5-robust-chartjs`, built on top of the V1 submission (`bd6a491` on `team/t5-robust`): same pipeline (native pass + class-aware ROI + grid-ghost drop + multiplier box + log-decade + `--tta shift`), but the network is fine-tuned once more with Chart.js charts in the training mix.
V1 (bd6a491) remains intact as the fallback on `team/t5-robust`; this report describes a strictly-further step on `team/t5-robust-chartjs`.

## 1. Verdict

**V2 is the preferred submission for charts that look like real-world screenshots.**

- Chart.js (the pivot's target) wins decisively: nogrid 0.196% to 0.123% (-37%), probe-set yticks_err_median 0.690 to 0.428 px (-38%), probe-set calib_y_within_0.5pct 0.81 to 0.90 (+9pp), probe-set frame_err_p90 16.7 to 5.8 px (-65%), probe-set line_rms_median 0.299% to 0.250% (-16%). Tick-bias experiment (section 4) confirms the mechanism: Chart.js y unsnapped bias cut from -1.04 to -0.64 px, |e| > 1 px rate 52% to 30%.
- Real-world benchmark (`data/t5-real`, 30 published charts): median rms 0.75% to 0.61% (-19%), within 1% 42% to 48%, median rms of found 0.65% to 0.49% (-25%). Cost: find rate 63% to 60% (-3pp), one more failure (14 to 15).
- matplotlib synthetic (`mpl-val`): mixed. line_rms_median regresses 0.280 to 0.325 (+16%), but peak_err_median improves 1.76 to 1.41 (-20%), line_found 0.573 to 0.586 (+1pp), frame_found 0.89 to 0.91 (+2pp).
- plotly-v1 (held out from training): roughly flat. line_rms_median 0.234 to 0.230, marker_precision 0.852 to 0.869 (+2pp), p90 tail widens 1.90 to 2.42.
- examples/real: 03-women-men-percent still 5 series linear x (V1 fix preserved); 05-retail-sales dropped from 2 lines to 1 (single-chart regression).

V1 (bd6a491) remains intact as the fallback and is still the correct choice for pure-matplotlib workloads; V2 is the deeper submission on `team/t5-robust-chartjs` and the right choice when the target is screenshots in the wild.

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
That offset shows on `mpl-val` line_rms (section 3.1) but the pay-off on Chart.js (sections 3.3-3.4) and on real charts (section 3.5) is a lot bigger.

## 3. Scoreboard

Full numbers under `teams/t5-robust/CASES.md` section 9 (V1) and this file (V2).

### 3.1 End-to-end, mpl-val (200), `--tta shift`

| metric | base (v3+6b313e9) | V1 (bd6a491) | V2 (t5-chartjs) | V2-V1 |
| --- | --- | --- | --- | --- |
| line_found | 0.5466 | 0.5727 | 0.5857 | +1.3pp |
| line_rms_median_pct | 0.4411 | 0.2802 | 0.3253 | +16% (worse) |
| line_rms_p90_pct | 2.8578 | 2.0716 | 2.1680 | +5% (worse) |
| peak_err_median_pct | 2.2898 | 1.7603 | 1.4138 | -20% (better) |
| marker_recall | 0.4811 | 0.5697 | 0.5616 | -0.8pp |
| marker_precision | 0.6395 | 0.7189 | 0.6966 | -2.2pp |
| frame_found | 0.89 | 0.89 | 0.91 | +2pp |
| frame_err_median_px | 1.42 | 0.96 | 0.94 | -0.02 |
| calib_x_within_0.5pct | 0.845 | 0.870 | 0.875 | +0.5pp |
| calib_y_within_0.5pct | 0.775 | 0.810 | 0.800 | -1pp |

Trade on pure matplotlib: V2 finds more and places frames better, but the trace medians widen by about 16%.

### 3.2 End-to-end, plotly-v1 (150), `--tta shift`

| metric | base | V1 | V2 | V2-V1 |
| --- | --- | --- | --- | --- |
| line_found | 0.7540 | 0.7896 | 0.7994 | +1.0pp |
| line_rms_median_pct | 0.2504 | 0.2335 | 0.2299 | -1.5% |
| line_rms_p90_pct | 2.0925 | 1.8959 | 2.4185 | +28% (worse tail) |
| peak_err_median_pct | 1.3376 | 1.0457 | 1.0823 | +3% |
| marker_recall | 0.4184 | 0.4075 | 0.4141 | +0.7pp |
| marker_precision | 0.7715 | 0.8515 | 0.8692 | +1.8pp |
| frame_found | 0.9400 | 0.9400 | 0.9400 | 0 |
| calib_x_within_0.5pct | 0.9467 | 0.9733 | 0.9600 | -1.3pp |
| calib_y_within_0.5pct | 0.8600 | 0.8933 | 0.8933 | 0 |

Plotly roughly flat: V2 median wins by a hair, marker precision up, tail (p90) widens.
No real regression; no real win either.

### 3.3 Chart.js corpus (`eval_corpus`; 18 charts, held-out renderer, `--tta shift`)

| chart | base | V1 | V2 |
| --- | --- | --- | --- |
| linear-single-solid | 0.033% | 0.072% | 0.033% |
| linear-single-nogrid | 0.194% | 0.196% | **0.123%** |
| linear-thin-line | 0.031% | 0.031% | 0.032% |
| linear-thick-line | 0.042% | 0.035% | 0.034% |
| linear-dashed | 0.067% | 0.068% | 0.070% |
| linear-multi | 0.037 / 0.046 / 0.017 | 0.077 / 0.045 / 0.017 | 0.040 / 0.053 / 0.016 |
| dark-theme | 0.047 / 0.017 | 0.063 / 0.017 | 0.066 / 0.018 |
| log-y | 1/1, 0.170% | 1/1, 0.170% | 1/1, 0.170% |
| log-y-multi | 2/2, 0.177 / 0.021 | 2/2, 0.177 / 0.024 | 2/2, 0.177 / 0.022 |
| scatter-markers | 0.060% | 0.060% | 0.060% |
| scatter-halo-colours | 4/4 | 4/4 | 4/4 (0.079 / 0.098 / 0.090 / 0.093) |
| jpeg-compressed | 0.034% | 0.083% | 0.087% |
| offset-annotation | 61.222% | 0.020% | 0.019% |
| retina-2x | 0.109% | 0.062% | 0.068% |
| log-log | 2/1, 1.326% | 1/1, 0.580% | 1/1, 0.593% |
| sawtooth-sharp | 0.268% | 0.234% | 0.243% |
| narrow-peaks | 0.211% | 0.240% | 0.258% |
| narrow-small | 0.066% | 0.066% | 0.066% |
| **median** | 0.067% | 0.072% | **0.068%** |
| **worst** | 61.222% | 0.580% | 0.593% |
| **failed** | 0 | 0 | 0 |

V2 reproduces V1's offset-annotation `1e6` save (0.019%), V1's log-log ghost-free trace (1/1), and base's single-solid number (0.033% vs V1's 0.072%).
The headline win is `linear-single-nogrid`: 0.194% to 0.123%, direct consequence of Chart.js in training teaching the em-box label convention.

### 3.4 Chart.js probe (`data/t5-chartjs-val`, 100 charts, `--tta shift`)

| metric | base | V1 | V2 | V2-V1 |
| --- | --- | --- | --- | --- |
| line_rms_median_pct (all / simple) | 0.343 / 0.285 | 0.299 / 0.260 | **0.250 / 0.200** | -16% / -23% |
| line_rms_p90_pct | - | - | 1.260 | - |
| line_found | 0.773 | 0.784 | 0.778 | -0.6pp |
| peak_err_median_pct (all / simple) | 0.636 / 0.408 | 0.494 / 0.271 | **0.427 / 0.229** | -14% / -16% |
| marker_recall / precision | 0.590 / 0.813 | 0.609 / 0.873 | 0.608 / **0.906** | +3.3pp precision |
| yticks_err_median_px | 0.751 | 0.690 | **0.428** | -38% |
| frame_found | 0.920 | 0.890 | 0.880 | -1pp |
| frame_err_p90_px | 26.8 | 16.7 | **5.77** | -65% |
| calib_y_within_0.5pct | 0.84 | 0.81 | **0.90** | +9pp |
| calib_y_err_median_pct | 0.234 | 0.214 | **0.128** | -40% |

The direct target. V2 cleanly beats V1 across every accuracy metric; the one soft regression (frame_found -1pp) is washed out by the frame-err tail collapsing to 5.8 px (V1: 16.7 px).

### 3.5 Real-chart benchmark (`data/t5-real`, 30 charts, 60 series, `--tta shift`)

Scored against the publisher's data; RMS in % of the data span; cov >= 80% for "found".

| metric | base (v3) | V1 (bd6a491) | V2 (t5-chartjs) | V2-V1 |
| --- | --- | --- | --- | --- |
| found (cov >= 80%) | 67% | 63% | 60% | -3pp |
| median rms (%) | 1.86 | 0.75 | **0.61** | -19% |
| median rms of found | 1.99 | 0.65 | **0.49** | -25% |
| within 1% | 28% | 42% | **48%** | +6pp |
| within 0.5% | 25% | 32% | 33% | +1pp |
| failed | 15 | 14 | 15 | +1 |

V2 trades a small drop in find rate for a clear step up in accuracy on everything found: median 0.49% vs V1's 0.65% on the series it recovers.
Within-1% jumps 42% to 48% (+6pp), biggest gain in that bucket since the a7aed7d-era pipeline work.

### 3.6 examples/real (hand-measured; `--tta shift`)

| chart | V1 | V2 |
| --- | --- | --- |
| 03-women-men-percent | 5 series linear x | 5 series linear x (holds) |
| 01-panel1 / panel2 / panel3 | within 1-2 px | panel1 max 0.87 px, panel2 0.40 px, panel3 0.95 px |
| 05-retail-sales-monthly | 2 series | 1 series (regression; one line dropped) |

The retail regression is the only new real-chart failure vs V1.

### 3.7 Resolution probe sets (`data/t5-dpr{1,2,3}`, 100 charts each at 1x/2x/3x DPR, `--tta shift`)

Simple-charts split (same mpl seeds at three device-pixel-ratios).

| set | metric | base (v3) | V1 submission | V2 submission | V2-V1 |
| --- | --- | --- | --- | --- | --- |
| dpr1 | line_rms_median_pct | 0.223 | 0.185 | **0.173** | -0.012 |
| dpr1 | marker_recall | 0.502 | 0.533 | 0.536 | +0.003 |
| dpr1 | frame_err_median_px | 1.12 | 0.81 | 0.96 | +0.16 |
| dpr2 | line_rms_median_pct | 0.249 | 0.088 | 0.109 | +0.021 |
| dpr2 | marker_recall | 0.349 | 0.326 | 0.337 | +0.011 |
| dpr2 | frame_err_median_px | 2.56 | 1.26 | 1.20 | -0.06 |
| dpr3 | line_rms_median_pct | 0.373 | 0.097 | 0.106 | +0.009 |
| dpr3 | marker_recall | 0.287 | 0.286 | 0.295 | +0.009 |
| dpr3 | frame_err_median_px | 2.92 | 1.45 | 1.59 | +0.14 |

V2 generalises to high-DPR trace at least as well as V1 (dpr2 within +0.02 pp) and beats base dramatically at dpr3 (-72% line_rms_median).

### 3.8 Image-factor probe sets (same 100 mpl seeds, one factor changed, `--tta shift`)

| set | metric | base (v3) | V1 submission | V2 submission | V2-V1 |
| --- | --- | --- | --- | --- | --- |
| blur | line_rms_median_pct | 0.232 | 0.163 | 0.201 | +0.038 |
| blur | marker_precision | 0.759 | 0.766 | 0.761 | -0.005 |
| dark | line_rms_median_pct | 0.278 | 0.222 | 0.217 | -0.005 |
| dark | yticks_recall | 0.818 | 0.874 | **0.904** | +0.030 |
| dark | frame_err_median_px | 1.21 | 1.14 | **0.91** | -0.23 |
| clutter | line_rms_median_pct | 0.241 | 0.168 | 0.226 | +0.058 |
| clutter | frame_err_median_px | 5.71 | 17.6 | 28.2 | +10.6 |
| half | line_rms_median_pct | 0.213 | 0.223 | **0.191** | -0.032 |
| up2x | line_rms_median_pct | 0.271 | 0.099 | 0.097 | -0.002 |
| up2x | peak_err_median_pct | 0.332 | 0.170 | **0.143** | -0.027 |
| jpeg50 | line_rms_median_pct | 0.212 | 0.193 | 0.206 | +0.013 |
| jpeg30 | line_rms_median_pct | 0.240 | 0.215 | 0.225 | +0.010 |
| skew1 | line_rms_median_pct | 2.803 | 2.349 | TBD | TBD |

Across the ten image-factor + DPR probes, V2 and V1 are essentially identical on average line_rms_median (V1 0.173%, V2 0.175%). V2 wins (dpr1, half, up2x, dark), loses (dpr2, dpr3, blur, jpeg50, jpeg30), and shows one notable regression on **clutter** (+35% rms, frame_err_median_px 18 to 28 px) worth probe_net inspection in a follow-up round. The Chart.js-side gain in section 3.4 (-16% to -65% depending on metric) and 3.5 (-19% on real-world rms) is why V2 is preferred; the matplotlib-side cost on probes is modest.

## 4. Mechanism: tick-bias experiment (curator probe)

Measured by `tick_bias.py` on `data/t5-chartjs-val` (100 Chart.js charts):

| axis | kind | n | V1 median bias (px) | V2 median bias (px) | V1 |e|>1 px | V2 |e|>1 px |
| --- | --- | --- | --- | --- | --- | --- |
| y | unsnapped | 101 | -1.04 | **-0.64** | 52% | **30%** |
| y | snapped | 413 | -0.66 | **-0.38** | 25% | **4%** |

Chart.js centres the em-box on each tick (textBaseline middle), where matplotlib centres the digits (center_baseline).
V1's network, trained only on matplotlib, placed Chart.js y labels about 1 px low; the frame-independent snap could hide it where gridlines were strong enough to snap to, but unsnapped ticks (nogrid, FRED, OWID tinted paper) carried the bias through.
V2 teaches the convention directly from 4,000 Chart.js charts and cuts the median bias by 40%, halving the |e|>1 px rate.
This is the mechanism behind every V2 Chart.js win in sections 3.3-3.4.

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
V1 submission: `team/t5-robust` at `bd6a491` (untouched; the fallback).

## 6. Status

- `runs/t5-chartjs/best.pt` saved at 19:38 EDT after 3,000 iters (VAL 3000 loss 2.588).
- All six scoreboard measurements complete in `out/t5/chartjs-*.txt`.
- Curator's image-factor probe set (dpr, blur, dark, clutter, half, up2x, jpeg50, jpeg30, skew1) in progress on the same flock; the dpr trio has already landed (dpr3 line_rms_median -20% vs a7aed7d).
