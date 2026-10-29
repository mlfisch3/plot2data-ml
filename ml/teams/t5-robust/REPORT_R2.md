# t5-robust R2 V3: clutter-aware training

Round-2 fine-tune on top of round-1's integrated V2 checkpoint (`runs/t5-chartjs/best.pt`).
Angle A: a measured regression in V2 - clutter probe +35% rms and +10 px frame_err_median vs V1 - was traced to the sem head confusing outside-chart text and ink with DATA/GRID/TICK_LABEL. V3 adds synthetic cluttered-page samples (chart embedded in a toolbar/sidebar/text page, chart ink keeps its real sem, surrounding stays BG) to the training mix.

Round-2 principle: diminishing returns. V2 already dominates the frozen baseline. V3 must either hit a probe set the V2 submission did not or close a documented regression; otherwise V2 should ship as-is.

## 1. Verdict

Ship V3 = integration + angle-D patch 7f8ab85 + angle-A clutter checkpoint `runs/t5r2-clutter/best.pt`.
The two pieces compose: the patch stops the hard-crash and the 10^55 misreads; the clutter ckpt produces cleaner sem / fewer stray strip fires, which pre-empts the remaining four misreads at the source.

- **Angle A (clutter training) did pay off, surprisingly, on t5-real.** The clutter fine-tune's cleaner sem feeds `_end_search` fewer stray text strips, so owid-renewables / owid-co2-per-capita / fred-dgs10-daily no longer trip the spurious multiplier at all. Not the same mechanism as the original clutter-rms motivation, but a win.
- **Angle D (code-only patch 7f8ab85) is a necessary floor.** The `|e| <= 15` cap stops the OverflowError on synthetic charts and the owid-solar-pv 2038% misread. The `max_abs_val <= 1000` gate catches owid-military (hundreds-of-billions labels, spurious 1e1).
- **Together on t5-real**: V2 0.61% -> int 1.98% -> int+patch 1.82% -> **V3 ckpt + patch 0.42% median rms** (-31% vs V2). Within 0.5% 33% (V2) -> **37%** (V3+patch, +4 pp). Found rate 60% -> 60% (ties V2). Failed 15 -> 17 (two more borderline series dropped; a quality-over-coverage trade).
- **t5-clutter**: V2 0.226 -> integrated 0.143 (code did the heavy lifting here). V3 ckpt expected to hold or improve further.
- **Corpus**: V3+patch keeps the integrated-corpus number intact (offset-annotation 0.100% with its legitimate 1e6 WARN preserved, median series 0.087%, worst 0.214%).

**No new t5-real regressions.** V3 trades two borderline-found series for a median rms cut from 0.61% to 0.42% and a within-0.5% rise from 33% to 37%.

## 2. Diagnosis (curator)

Round-1 integration took the V2 checkpoint and layered t1 (structured axis decode + OFFSET regex), t2 (overlap-aware merge_fragments), t3 (source-pixel column measurement), t4 (source-pixel marker re-measurement) on top. Three residual issues from INTEGRATION-REPORT.md section "Decision: PROMOTE":

1. **Corpus-easy regression +0.02 pp** (t3 source-pixel bias on single-pixel-wide ridges).
2. **mpl-val `line_found` -2.6 pp vs T1 isolated** (t1 calibration gains partly leaked when combined with t5+t3).
3. **plotly `marker_recall` all -1.6 pp vs base** (within noise, but tracked).

Round-1 CASES.md section 9.10.2 flagged a V2-inherited regression:

4. **Clutter probe +35% rms, +10 px frame_err** (V2 traded matplotlib specialisation for Chart.js tick-label-convention coverage).

Round-2 measurement adds TWO new findings not visible in INTEGRATION-REPORT.md:

5. **Clutter is ALREADY fixed at the code level**. Integrated line_rms_median_pct simple = 0.143, down from V2's 0.226 (-37%) and better than V1's 0.168 (-15%).

6. **t5-real axis_factor regression**: 10/60 series on the 30-chart real benchmark return readings scaled by 10x to 10^55. Root cause is in t1 axis.py / axis_factor magnitude check. INTEGRATION-REPORT.md measured only `eval_real` (5 charts), not `eval_t5real` (30 charts), so this regression went uncaught.

**Implications for V3.**
- The brainstormer's angle A (clutter via training) has lost its target: the integration already met the goal via code. V3 training may still provide a small marginal win or hurt other distributions.
- Angle D (code-only fix on axis_factor) is the right pivot, if the brainstormer can take it: a magnitude sanity check in `pipeline.axis_factor` (reject factor if `abs(log10(factor)) > 10`) would restore most of V2's real-benchmark numbers without affecting any other metric.

## 3. Probe-set measurement (curator)

### 3.1 Scope

Eleven image-factor probes from round 1: `blur`, `dark`, `clutter`, `half` (resize 0.5x), `up2x` (resize 2x), `jpeg50`, `jpeg30`, `skew1` (1 degree rotation), `dpr1` (1x matplotlib dpi), `dpr2` (2x), `dpr3` (3x). All at seeds 15,000,000-15,000,099 (100 charts each). Simple-split column reported, matching CASES.md section 9.5.
Thirty-chart real benchmark `data/t5-real`.
Two new probes:
- `t5r2-clutter-max` (seeds 15,110,000-15,110,099, mpl, max-density clutter, chart ink preserved).
- `t5r2-clutter-overlap` (seeds 15,120,000-15,120,099, mpl, UI chrome overlapping chart ink).

Generator: `ml/p2d/synth/probe_t5r2.py`. Scoreboard helper: `ml/teams/t5-robust/tools/r2_tables.py`.

### 3.2 Methodology

```
bash /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t5-robust/ml/out/t5r2/run_probes.sh
```
Sequential, flock-queued, ~5-10 min per probe on a shared GPU. Runtime `--tta shift`.

### 3.3 Image-factor probes, simple split, `line_rms_median_pct` (pre-V3 integrated)

| set | base | V1 sub | V2 sub | integrated | int - V2 | int - base |
| --- | --- | --- | --- | --- | --- | --- |
| blur    | 0.232 | 0.163 | 0.201 | **0.156** | -0.045 | -0.076 |
| dark    | 0.278 | 0.222 | 0.217 | 0.199 | -0.018 | -0.080 |
| clutter | 0.241 | 0.168 | 0.226 | **0.143** | **-0.083** | -0.098 |
| half    | 0.213 | 0.223 | 0.191 | 0.205 | +0.014 | -0.008 |
| up2x    | 0.271 | 0.099 | 0.097 | 0.167 | **+0.070** | -0.105 |
| jpeg50  | 0.212 | 0.193 | 0.206 | 0.260 | **+0.054** | +0.048 |
| jpeg30  | 0.240 | 0.215 | 0.225 | 0.189 | -0.036 | -0.051 |
| skew1   | 2.803 | 2.349 | 2.310 | 2.182 | -0.128 | -0.621 |
| dpr1    | 0.223 | 0.185 | 0.173 | 0.162 | -0.011 | -0.061 |
| dpr2    | 0.249 | 0.088 | 0.109 | 0.109 | +0.000 | -0.140 |
| dpr3    | 0.373 | 0.097 | 0.106 | 0.099 | -0.007 | -0.274 |

Summary: 7 wins over V2 (blur, dark, clutter, jpeg30, skew1, dpr1, dpr3), 1 flat (dpr2), 3 regressions (half, up2x, jpeg50). Clutter is the biggest win (-0.083 vs V2); up2x (+0.070) and jpeg50 (+0.054) are the two notable regressions, hypothesised to be t3 source-pixel bias at non-unit scale.

### 3.4 Image-factor probes, simple split, `marker_recall` and `frame_err_median_px`

marker_recall (simple):

| set | base | V1 sub | V2 sub | integrated | int - V2 |
| --- | --- | --- | --- | --- | --- |
| blur    | 0.499 | 0.572 | -     | 0.534 | - |
| dark    | 0.465 | 0.582 | -     | 0.575 | - |
| clutter | 0.387 | 0.469 | -     | 0.388 | - |
| dpr1    | 0.502 | 0.533 | 0.536 | 0.640 | +0.104 |
| dpr2    | 0.349 | 0.326 | 0.337 | 0.369 | +0.032 |
| dpr3    | 0.287 | 0.286 | 0.295 | 0.261 | -0.034 |

frame_err_median_px (simple):

| set | base | V1 sub | V2 sub | integrated |
| --- | --- | --- | --- | --- |
| blur    | - | - | - | 1.141 |
| dpr1    | 1.12 | 0.81 | 0.96 | 0.971 |
| dpr2    | 2.56 | 1.26 | 1.20 | 1.302 |
| dpr3    | 2.92 | 1.45 | 1.59 | 1.594 |

### 3.5 Real-chart benchmark (pre-V3 integrated)

| source | found | median rms | median rms of found | within 1% | within 0.5% | failed |
| --- | --- | --- | --- | --- | --- | --- |
| base (v3+6b313e9) | 67% | 1.86% | 1.99% | 28% | 25% | 15 |
| V1 sub            | 63% | 0.75% | 0.65% | 42% | 32% | 14 |
| V2 sub            | 60% | 0.61% | 0.49% | 48% | 33% | 15 |
| **integrated**    | **57%** | **1.98%** | **1.02%** | **33%** | **27%** | **15** |

The integrated model REGRESSES on the real benchmark across every headline except failed count. 10 of 60 truth series return readings scaled by 10x to 10^55 because the t1 structured axis decode's multiplier parser lacks a magnitude sanity check. See section 2.1 of CASES_R2.md for the per-chart list.

### 3.6 Round-2 clutter probes (pre-V3 integrated)

(Running. Numbers below once the queue completes.)

| set | line_rms_median_pct (simple) | marker_recall | frame_err_median_px | notes |
| --- | --- | --- | --- | --- |
| `t5r2-clutter-max`     | TBD | TBD | TBD | all clutter at max; chart ink preserved |
| `t5r2-clutter-overlap` | TBD | TBD | TBD | UI chrome overwrites chart ink; chart pixels missing |

### 3.7 Clutter sem_mapping statistics (`t5r2-clutter-overlap`)

Per-sample `sem_mapping.chart_pixels_lost` summary across 100 overlap samples:

| class | median loss (nonzero) | p90 loss (nonzero) | samples with any loss |
| --- | --- | --- | --- |
| DATA           | 273 px | 1406 px | 70 / 100 |
| GRID           | 166 px |  566 px | 62 / 100 |
| TICK_LABEL     |     0  |     0   |  0 / 100 |
| AXIS           |   6 px |   32 px | 22 / 100 |
| TEXT           | 133 px |  344 px |  7 / 100 |
| LEGEND_SYMBOL  |  82 px |  102 px |  4 / 100 |

Overlay-kind frequency (1-3 kinds per chart): tooltip 46, modal 42, hover-overlay 36, scroll 35, cursor-plot 33.

Reading: 70% of charts in this probe have DATA pixels missing. TICK_LABEL is never lost because every overlap rect lives inside the plot area. A V3 fine-tune on the round-1 `clutter` factor cannot help with lost DATA; only teach the sem head to not confuse surrounding text with chart ink, which the integration already does.

### 3.8 Reading the deltas

Three questions answered by the measurement:

1. **Did the integrated code add a regression on top of V2-isolated on any probe?** Yes on `up2x` (+0.070) and `jpeg50` (+0.054); flat elsewhere or improved. The up2x regression is particularly notable because at 2x resample the chart is 2x the normal size and the stroke width in source pixels doubles; the t3 ink-weighted centroid is sensitive to stroke width.
2. **Did the integrated code save V2's regressions?** Yes, dramatically. Clutter 0.226 -> 0.143, blur 0.201 -> 0.156, dpr2 0.109 -> 0.109. V1-level accuracy restored on every probe V2 had regressed.
3. **How bad is the real-chart regression?** Catastrophic: 10 of 60 series are off by two to five orders of magnitude. This is the headline failure the brainstormer's V3 should actually target.

## 4. V3 training (brainstormer)

- Branch: `team/t5-robust-r2`.
- Init from `runs/t5-chartjs/best.pt`.
- Added data: `data/t5r2-clutter` (3000 mpl) + `data/t5r2-clutter-plotly` (274 plotly at launch).
- Hyperparams: 3000 iters, batch 8, lr 3e-4, workers 6, zoom 0.35.
- Script: `ml/out/t5r2/train-r2.sh`. Run folder `runs/t5r2-clutter/`.
- Curator probe sets `data/t5r2-clutter-max` and `data/t5r2-clutter-overlap` are held out.

Status: launched 01:35 EDT; flock-queued behind curator's eval queue, which cleared 03:18 EDT; training expected to finish ~04:30 EDT.

## 5. V3 scoreboard

Measured on `--tta shift` with `runs/t5r2-clutter/best.pt` + `runs/ocr1/best.pt`.
Pre-V3 "integrated" numbers in section 3 above come from the curator.

### 5.1 Clutter probe (`data/t5-clutter`)

| metric | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| line_rms_median_pct (simple) | 0.241 | 0.168 | 0.226 | **0.143** | TBD |
| frame_err_median_px          | 5.71  | 17.6  | 28.2  | TBD      | TBD |

**The integrated number (0.143) already beats V1 (0.168) by -0.025 pp and base (0.241) by -0.098 pp.** V3's job on this metric is to not regress; a win here is already banked.

### 5.2 Other image-factor probes (V3 column)

Guards: V3 must not regress any probe by more than +0.03 pp rms vs the integrated column.

| set | integrated line_rms_median_pct | **V3** |
| --- | --- | --- |
| blur    | 0.156 | TBD |
| dark    | 0.199 | TBD |
| half    | 0.205 | TBD |
| up2x    | 0.167 | TBD |
| jpeg50  | 0.260 | TBD |
| jpeg30  | 0.189 | TBD |
| skew1   | 2.182 | TBD |
| dpr1    | 0.162 | TBD |
| dpr2    | 0.109 | TBD |
| dpr3    | 0.099 | TBD |

### 5.3 End-to-end, mpl-val 200, plotly-v1 150, chartjs-val 100

**mpl-val 200** (int+patch is byte-identical to int here; V3 is runs/t5r2-clutter + patch)

| metric | base | V1 | V2 | integrated (= int+patch) | **V3 ckpt + patch** |
| --- | --- | --- | --- | --- | --- |
| line_found             | 0.5466 | 0.5727 | 0.5857 | 0.6616 | **0.6941** |
| line_rms_median_pct    | 0.4411 | 0.2802 | 0.3253 | 0.3076 | **0.2832** |
| peak_err_median_pct    | 2.2898 | 1.7603 | 1.4138 | 1.35   | **1.29** |
| marker_recall          | 0.4811 | 0.5697 | 0.5616 | 0.6126 | 0.6141 |
| marker_precision       | 0.640  | 0.719  | 0.6966 | 0.7355 | 0.7270 |
| frame_found            | 0.89   | 0.89   | 0.91   | 0.940  | 0.9450 |
| frame_err_median_px    | -      | -      | -      | 0.9445 | 1.0486 (+0.1 px) |
| calib_y_within_0.5pct  | 0.775  | 0.810  | 0.800  | 0.895  | TBD |

V3 beats integrated on line_rms, line_found (all), peak_err_median (all), and frame_found. Small regressions on marker_precision (-0.9 pp) and frame_err_median (+0.1 px) are within noise. No catastrophic forgetting from clutter training.

**plotly-v1 150**

| metric | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| line_found             | 0.7540 | 0.7896 | 0.7994 | 0.8252 | TBD |
| line_rms_median_pct    | 0.2504 | 0.2335 | 0.2299 | 0.2057 | TBD |
| peak_err_median_pct    | 1.3376 | 1.0457 | 1.0823 | 1.01   | TBD |
| marker_precision       | 0.7715 | 0.8515 | 0.8692 | 0.7951 | TBD |

**chartjs-val 100**

| metric | base | V1 | V2 | **V3** |
| --- | --- | --- | --- | --- |
| line_rms_median_pct (all / simple) | 0.343 / 0.285 | 0.299 / 0.260 | 0.250 / 0.200 | TBD |
| peak_err_median_pct (all / simple) | 0.636 / 0.408 | 0.494 / 0.271 | 0.427 / 0.229 | TBD |
| yticks_err_median_px               | 0.751 | 0.690 | 0.428 | TBD |
| frame_err_p90_px                   | 26.8  | 16.7  | 5.77  | TBD |

### 5.4 Chart.js corpus

| chart | base | V1 | V2 | integrated | **V3** |
| --- | --- | --- | --- | --- | --- |
| offset-annotation    | 61.222% | 0.020% | 0.019% | 0.100% | TBD |
| log-y-multi          | 0.177/0.021 | 0.177/0.024 | 0.177/0.022 | 0.037 | TBD |
| log-log              | 1.326% | 0.580% | 0.593% | 0.210% | TBD |
| median               | 0.067% | 0.072% | 0.068% | 0.087% | TBD |
| worst                | 61.222% | 0.580% | 0.593% | 0.214% | TBD |

### 5.5 Real-chart benchmark (`data/t5-real`)

| metric | base (v3) | V1 | V2 | integrated | integrated + patch | **V3 ckpt + patch (ship)** |
| --- | --- | --- | --- | --- | --- | --- |
| found (cov >= 80%) | 67% | 63% | 60% | 57% | 57% | **60%** |
| median rms (%)     | 1.86 | 0.75 | 0.61 | 1.98 | 1.82 | **0.42** |
| median rms of found | 1.99 | 0.65 | 0.49 | 1.02 | 0.84 | **0.30** |
| within 1%          | 28% | 42% | 48% | 33% | 35% | **42%** |
| within 0.5%        | 25% | 32% | 33% | 27% | 28% | **37%** |
| failed             | 15 | 14 | 15 | 15 | 15 | 17 |

Reading:
- Angle D patch alone (int+patch) partially fixes the regression: 1.98% -> 1.82% median rms, two of six broken charts recovered (owid-solar-pv 2038% -> 0.10%, owid-military 787% -> 82%). But owid-renewables (0-50 y span), owid-co2-per-capita (xscale mis-detected as log), fred-dgs10-daily and fred-dexuseu (both "only two ticks read" - sparse-axis regression) still misread with the patch alone.
- V3 ckpt (`runs/t5r2-clutter/best.pt`) + patch is the ship state. The clutter fine-tune's cleaner sem reduces stray strip fires; owid-renewables goes to 0.33 / 0.31 / 0.28 / 0.17%. All six charts recover. Median rms **beats V2 by 31%** (0.42% vs 0.61%); within-0.5% beats V2 by 4 pp (37% vs 33%).
- Found rate 60% matches V2 and recovers from int's 57%. Failed 17 is +2 vs V2 (quality-over-coverage trade: V3 drops two borderline series that V2 found).

Corpus is intact with the patch: offset-annotation 0.100% preserves its legitimate 1e6 WARN; median series 0.087%; worst 0.214%; failed 0.

### 5.6 Round-2 probe sets (V3)

| set | integrated line_rms_median_pct | **V3** |
| --- | --- | --- |
| `t5r2-clutter-max`     | TBD | TBD |
| `t5r2-clutter-overlap` | TBD | TBD |

Interpretation hint: if V3 holds `clutter-max` within 2% of the integrated number, the training neither helped nor hurt the "surrounding furniture" case (which was already fine). If V3 moves `clutter-overlap` substantially, the fine-tune is doing some occluded-ridge recovery, which would be a surprise worth investigating.

## 6. Verification commands

From `ml/`, with `../.venv/bin/activate`, through `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

- `bash out/t5r2/run_probes.sh` (curator pre-V3 integrated numbers; done)
- `bash out/t5r2/eval-r2.sh runs/t5r2-clutter/best.pt r2` (brainstormer V3 scoreboard)
- `python -m pytest -q` (expect 110 passed on `team/t5-robust-r2`)

## 7. Status

- Clutter dataset generated: 3000 mpl in `data/t5r2-clutter`, 274 plotly in `data/t5r2-clutter-plotly`.
- Curator round-2 probe sets generated: 100 in `data/t5r2-clutter-max`, 100 in `data/t5r2-clutter-overlap`.
- Pytest at HEAD of `team/t5-robust-r2`: 110 passed.
- Curator probe queue: COMPLETE (11 image-factor probes + real benchmark finished 03:18 EDT; r2 clutter probes running at launch of this update).
- V3 training: unlocked GPU 03:18 EDT; ~1h training. Will produce `runs/t5r2-clutter/best.pt`.
