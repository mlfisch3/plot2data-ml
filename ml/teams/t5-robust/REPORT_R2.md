# t5-robust R2 V3: clutter-aware training

Round-2 fine-tune on top of round-1's integrated V2 checkpoint (`runs/t5-chartjs/best.pt`).
Angle A: a measured regression in V2 - clutter probe +35% rms and +10 px frame_err_median vs V1 - was traced to the sem head confusing outside-chart text and ink with DATA/GRID/TICK_LABEL. V3 adds synthetic cluttered-page samples (chart embedded in a toolbar/sidebar/text page, chart ink keeps its real sem, surrounding stays BG) to the training mix.

Round-2 principle: diminishing returns. V2 already dominates the frozen baseline. V3 must either hit a probe set the V2 submission did not or close a documented regression; otherwise V2 should ship as-is.

## 1. Verdict

TBD after measurement.

## 2. Diagnosis (curator)

Round-1 integration took the V2 checkpoint and layered t1 (structured axis decode + OFFSET regex), t2 (overlap-aware merge_fragments), t3 (source-pixel column measurement), t4 (source-pixel marker re-measurement) on top. The result dominated the frozen base on every scoreboard. Three known residual issues from INTEGRATION-REPORT.md section "Decision: PROMOTE":

1. **Corpus-easy regression +0.02 pp** (t3 source-pixel bias on single-pixel-wide ridges).
2. **mpl-val `line_found` -2.6 pp vs T1 isolated** (t1 calibration gains partly leaked when combined with t5+t3).
3. **plotly `marker_recall` all -1.6 pp vs base** (within noise, but tracked).

Round-1 CASES.md section 9.10.2 flags one further regression that the integration INHERITED from V2 and did not touch:

4. **Clutter probe +35% rms, +10 px frame_err** (V2 traded matplotlib specialisation for Chart.js tick-label-convention coverage; cluttered inputs regressed).

The brainstormer picked angle **A (clutter failure mode fix via training)** for V3. Fix target: residual issue 4. The hope is to also hold or slightly improve on the other three.

Risks the curator sees:
- **Risk 1**: catastrophic forgetting on matplotlib (V2 already lost a point on mpl-val vs V1-isolated). lr 3e-4 (half of V2's) over 3000 iters is probably safe, but worth measuring.
- **Risk 2**: the fine-tune might also cost Chart.js specialisation, in which case the fix would be a wash (chart.js regresses symmetrically to clutter improvement).
- **Risk 3**: `clutter-overlap` cannot be rescued by training on the round-1 `clutter` factor alone: in that factor the chart is painted LAST, so the model never sees chart pixels missing during training. That failure mode will still exist in V3; the probe `t5r2-clutter-overlap` gives the pre-training number for a potential V4.

Diagnosis plan: measure the integrated model (121ed4d + runs/t5-chartjs + --tta shift) on every probe set round-1 reported, plus two new probes keyed to angle A, before V3 training begins. The pre-V3 baseline is the integrated-code numbers in section 3 below, NOT the V2-isolated ones; the brainstormer uses these as the "before" for V3 comparison.

## 3. Probe-set measurement (curator)

### 3.1 Scope

Eleven image-factor probes from round 1: `blur`, `dark`, `clutter`, `half` (resize 0.5x), `up2x` (resize 2x), `jpeg50`, `jpeg30`, `skew1` (1 degree rotation), `dpr1` (1x matplotlib dpi), `dpr2` (2x), `dpr3` (3x). All at seeds 15,000,000-15,000,099 (100 charts each). Simple-split column reported, matching CASES.md section 9.5.
Thirty-chart real benchmark `data/t5-real` (12 OWID, 16 FRED, 1 NASA GISS, 1 NOAA Mauna Loa).
Two new probes:
- `t5r2-clutter-max` (seeds 15,110,000-15,110,099, mpl, max-density clutter, chart ink preserved).
- `t5r2-clutter-overlap` (seeds 15,120,000-15,120,099, mpl, UI chrome overlapping chart ink).

Generator: `ml/p2d/synth/probe_t5r2.py`. Scoreboard helper: `ml/teams/t5-robust/tools/r2_tables.py` (reads `out/t5r2/*.txt`, prints the delta tables below).

### 3.2 Methodology

Each probe:
```
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt \
    --data data/t5-$name --tta shift > out/t5r2/$name.txt
```
Driver script: `ml/out/t5r2/run_probes.sh` (sequential, under flock, ~5-10 min per probe depending on load).

### 3.3 Image-factor probes, simple split, `line_rms_median_pct` (pre-V3 integrated)

Table rows: integrated vs V2-isolated vs V1-isolated vs base. `int - V2` is the merge's effect at the same checkpoint; `int - base` is the full R1 delta.

| set | base (v3+6b313e9) | V1 sub (zoom+a7aed7d) | V2 sub (chartjs+a7aed7d) | integrated (chartjs+121ed4d) | int - V2 | int - base |
| --- | --- | --- | --- | --- | --- | --- |
| blur    | 0.232 | 0.163 | 0.201 | **0.156** | -0.045 | -0.076 |
| dark    | 0.278 | 0.222 | 0.217 | TBD | TBD | TBD |
| clutter | 0.241 | 0.168 | 0.226 | TBD | TBD | TBD |
| half    | 0.213 | 0.223 | 0.191 | TBD | TBD | TBD |
| up2x    | 0.271 | 0.099 | 0.097 | TBD | TBD | TBD |
| jpeg50  | 0.212 | 0.193 | 0.206 | TBD | TBD | TBD |
| jpeg30  | 0.240 | 0.215 | 0.225 | TBD | TBD | TBD |
| skew1   | 2.803 | 2.349 | 2.310 | TBD | TBD | TBD |
| dpr1    | 0.223 | 0.185 | 0.173 | TBD | TBD | TBD |
| dpr2    | 0.249 | 0.088 | 0.109 | TBD | TBD | TBD |
| dpr3    | 0.373 | 0.097 | 0.106 | TBD | TBD | TBD |

(Full table generated with `python teams/t5-robust/tools/r2_tables.py --metric line_rms_median_pct --split simple` once the queue finishes.)

### 3.4 Image-factor probes, `marker_recall` and `frame_err_median_px` (pre-V3 integrated)

TBD. See r2_tables.py.

### 3.5 Real-chart benchmark (pre-V3 integrated)

| source | found | median rms | within 1% | within 0.5% | failed |
| --- | --- | --- | --- | --- | --- |
| base (v3+6b313e9) | 67% | 1.86% | 28% | 25% | 15 |
| V1 sub            | 63% | 0.75% | 42% | 32% | 14 |
| V2 sub            | 60% | 0.61% | 48% | 33% | 15 |
| integrated        | TBD | TBD   | TBD | TBD | TBD |

### 3.6 Round-2 clutter probes (pre-V3 integrated)

The integrated model has not seen clutter at any density during training (same checkpoint as V2). These are the "before training" baseline for V3.

| set | line_rms_median_pct (simple) | marker_recall | frame_err_median_px | notes |
| --- | --- | --- | --- | --- |
| `t5r2-clutter-max`     | TBD | TBD | TBD | all clutter at max; chart ink preserved |
| `t5r2-clutter-overlap` | TBD | TBD | TBD | UI chrome overwrites chart ink; some chart pixels are physically missing |

### 3.7 Clutter sem_mapping statistics (`t5r2-clutter-overlap`)

Per-sample `sem_mapping.chart_pixels_lost` summary across the 100 overlap samples (seeds 15,120,000-15,120,099). Measured by `python teams/t5-robust/tools/r2_tables.py --sem-mapping data/t5r2-clutter-overlap`.

| class | median loss (nonzero) | p90 loss (nonzero) | samples with any loss |
| --- | --- | --- | --- |
| DATA           | 273 px | 1406 px | 70 / 100 |
| GRID           | 166 px |  566 px | 62 / 100 |
| TICK_LABEL     |     0  |     0   |  0 / 100 |
| AXIS           |   6 px |   32 px | 22 / 100 |
| TEXT           | 133 px |  344 px |  7 / 100 |
| LEGEND_SYMBOL  |  82 px |  102 px |  4 / 100 |

Overlay-kind frequency (one chart may carry 1-3 kinds):

- `tooltip`: 46 charts
- `modal`: 42 charts
- `hover-overlay`: 36 charts
- `scroll`: 35 charts
- `cursor-plot`: 33 charts

Reading: 70% of charts in this probe have DATA pixels missing (median 273 px, up to 1406 at p90). TICK_LABEL is never lost because every overlap rect lives inside the plot area; tick labels sit outside. A V3 fine-tune on the round-1 `clutter` factor (chart painted last, no chart pixels lost) cannot help with the lost DATA; it can only teach the sem head to not confuse surrounding text with chart ink, which is what the brainstormer is after.

### 3.8 Reading the deltas (curator interpretation)

Three questions the measurement should answer:

1. **Did the integrated code (121ed4d) ADD a regression on top of V2-isolated on any probe?** For each row, `int - V2` should be small and preferably negative. A row with `int - V2 > 0.05 pp` on `line_rms` is a regression introduced by the merge, not by V2 the checkpoint.
2. **Did the integrated code SAVE a V2 regression that V1-isolated already handled?** For rows where V2 is clearly worse than V1 (clutter +34%, blur +23%, dpr2 +24%, jpeg50 +7%, jpeg30 +5%), does the integration recover any of that? Blur has already answered yes: integrated 0.156 vs V1 0.163 vs V2 0.201 - the merge recovered the entire V2 regression and then some, before any V3 training. If this pattern repeats on the other rows, the V3 fine-tune's job narrows to clutter specifically.
3. **How bad is `t5r2-clutter-max` vs `t5-clutter`?** Max-density only mildly worse means "V2's regression is about surrounding furniture presence, not density". Max-density dramatically worse means "the failure mode scales with density, and the V3 training mix should over-represent high-density cases".

Full reading in a later revision, after the queue finishes.

## 4. V3 training (brainstormer)

- Branch: `team/t5-robust-r2`.
- Init from `runs/t5-chartjs/best.pt` (V2, round-1 integrated base).
- Added data: `data/t5r2-clutter` (3000 mpl, seeds 15,100,000+) and `data/t5r2-clutter-plotly` (1000 plotly, seeds 15,200,000+), both from `probe_t5.make(..., factor='clutter', ...)`. 4000 clutter samples total, 5.6% of a 71,385-sample mix.
- Hyperparams: 3000 iters, batch 8, lr 3e-4 cosine (half of V2's 6e-4, chosen as a gentle fine-tune since the V2 ckpt is already well converged), workers 6, zoom 0.35, encoder resnet34.
- Script: `ml/out/t5r2/train-r2.sh`. Run folder `runs/t5r2-clutter/`. Checkpoint `runs/t5r2-clutter/best.pt`.
- Runtime remains native pass + `--tta shift`.
- Round-2 probe sets `data/t5r2-clutter-max` and `data/t5r2-clutter-overlap` (curator's) are held out, not included in training.

## 5. V3 scoreboard

Measured on `--tta shift` with `runs/t5r2-clutter/best.pt` + `runs/ocr1/best.pt`.
Pre-V3 "integrated" numbers in section 3 above come from the curator; V3 columns to be filled in once training finishes.

### 5.1 Clutter probe (`data/t5-clutter`)

Primary target.

| metric | base (v3) | V1 (bd6a491) | V2 (t5-chartjs) | integrated | **V3 (t5r2-clutter)** |
| --- | --- | --- | --- | --- | --- |
| line_rms_median_pct | 0.241 | 0.168 | 0.226 | TBD | TBD |
| frame_err_median_px | 5.71 | 17.6 | 28.2 | TBD | TBD |

Target: V3 drops rms back to or below V1's 0.168 and frame_err back below V1's 17.6 px, without a regression on the other probes below.

### 5.2 Other image-factor probes (same 10 as section 3.3, V3 column)

| set | metric | integrated | **V3** |
| --- | --- | --- | --- |
| blur    | line_rms_median_pct | 0.156 | TBD |
| dark    | line_rms_median_pct | TBD | TBD |
| dark    | frame_err_median_px | TBD | TBD |
| half    | line_rms_median_pct | TBD | TBD |
| up2x    | line_rms_median_pct | TBD | TBD |
| up2x    | peak_err_median_pct | TBD | TBD |
| jpeg50  | line_rms_median_pct | TBD | TBD |
| jpeg30  | line_rms_median_pct | TBD | TBD |
| skew1   | line_rms_median_pct | TBD | TBD |
| dpr1    | line_rms_median_pct | TBD | TBD |
| dpr2    | line_rms_median_pct | TBD | TBD |
| dpr3    | line_rms_median_pct | TBD | TBD |

Guard: V3 must not regress any of these by more than +0.03 pp rms vs the integrated column.

### 5.3 End-to-end, mpl-val 200, plotly-v1 150, chartjs-val 100

From REPORT_V2.md sections 3.1, 3.2, 3.4, plus the integration numbers from INTEGRATION-REPORT.md and the V3 column.

**mpl-val 200**

| metric | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| line_found             | 0.5466 | 0.5727 | 0.5857 | 0.6616 | TBD |
| line_rms_median_pct    | 0.4411 | 0.2802 | 0.3253 | 0.3076 | TBD |
| peak_err_median_pct    | 2.2898 | 1.7603 | 1.4138 | 1.35   | TBD |
| marker_recall          | 0.4811 | 0.5697 | 0.5616 | 0.6126 | TBD |
| frame_found            | 0.89   | 0.89   | 0.91   | 0.940  | TBD |
| calib_y_within_0.5pct  | 0.775  | 0.810  | 0.800  | 0.895  | TBD |

**plotly-v1 150**

| metric | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| line_found             | 0.7540 | 0.7896 | 0.7994 | 0.8252 | TBD |
| line_rms_median_pct    | 0.2504 | 0.2335 | 0.2299 | 0.2057 | TBD |
| peak_err_median_pct    | 1.3376 | 1.0457 | 1.0823 | 1.01   | TBD |
| marker_precision       | 0.7715 | 0.8515 | 0.8692 | 0.7951 | TBD |

**chartjs-val 100** (V2 target, must not regress)

| metric | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| line_rms_median_pct (all / simple) | 0.343 / 0.285 | 0.299 / 0.260 | 0.250 / 0.200 | TBD |
| peak_err_median_pct (all / simple) | 0.636 / 0.408 | 0.494 / 0.271 | 0.427 / 0.229 | TBD |
| yticks_err_median_px               | 0.751 | 0.690 | 0.428 | TBD |
| frame_err_p90_px                   | 26.8  | 16.7  | 5.77  | TBD |

### 5.4 Chart.js corpus (`eval_corpus`)

| chart | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| linear-single-nogrid | 0.194% | 0.196% | 0.123% | 0.126% | TBD |
| offset-annotation    | 61.222% | 0.020% | 0.019% | 0.100% | TBD |
| log-y-multi          | 0.177/0.021 | 0.177/0.024 | 0.177/0.022 | 0.037 | TBD |
| log-log              | 1.326% | 0.580% | 0.593% | 0.210% | TBD |
| median               | 0.067% | 0.072% | 0.068% | 0.087% | TBD |
| worst                | 61.222% | 0.580% | 0.593% | 0.214% | TBD |

### 5.5 Real-chart benchmarks

| metric | base (v3) | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| found (cov >= 80%) | 67% | 63% | 60% | TBD | TBD |
| median rms (%)     | 1.86 | 0.75 | 0.61 | TBD | TBD |
| median rms of found | 1.99 | 0.65 | 0.49 | TBD | TBD |
| within 1%          | 28% | 42% | 48% | TBD | TBD |
| failed             | 15 | 14 | 15 | TBD | TBD |

examples/real: integrated holds the 5-series linear x on 03-women-men-percent and the 2 lines on 05-retail-sales-monthly (both wins the integration recovered). V3 must not reintroduce the 1-line retail-sales regression.

### 5.6 Round-2 probe sets (V3)

| set | line_rms_median_pct (simple) | marker_recall | frame_err_median_px | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| `t5r2-clutter-max`     | TBD | TBD | TBD | TBD | TBD |
| `t5r2-clutter-overlap` | TBD | TBD | TBD | TBD | TBD |

Interpretation hint: if V3 drops `clutter-max` substantially but `clutter-overlap` barely moves, the fix generalises to density but not to physical pixel loss (expected, per section 2 risk 3). If V3 moves both, the fine-tune is also doing some occluded-ridge inpainting.

## 6. Verification commands

From `ml/`, with `../.venv/bin/activate`, through `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

- `bash out/t5r2/run_probes.sh` (curator pre-V3 integrated numbers; 11 image-factor + real + 2 r2 probes)
- `bash out/t5r2/eval-r2.sh runs/t5r2-clutter/best.pt r2` (brainstormer V3 scoreboard)
- `python -m pytest -q` (expect 110 passed on `team/t5-robust-r2`)

## 7. Status

- Clutter dataset generated: 3000 mpl in `data/t5r2-clutter`, 274 plotly in `data/t5r2-clutter-plotly` (plotly set capped at 274 at training launch).
- Curator round-2 probe sets generated: 100 in `data/t5r2-clutter-max`, 100 in `data/t5r2-clutter-overlap`.
- Pytest at HEAD of `team/t5-robust-r2`: 110 passed.
- Integrated probe queue: launched 01:24 EDT, 1 of 11 image-factor probes complete (blur). Expected completion ~03:00 EDT.
- V3 training: launched 01:35 EDT, queued behind curator's eval queue. Expected GPU start when curator queue clears.
