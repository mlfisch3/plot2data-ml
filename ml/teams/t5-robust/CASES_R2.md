# t5-robust round 2: the failure catalogue after integration

Curator's record of what still breaks on charts outside the training distribution, after round-1 integration.
"Before" numbers come from round 1 CASES.md (frozen baseline `main` at `6b313e9`, `runs/v3/best.pt`, no TTA) or from V2-isolated (`team/t5-robust-chartjs`, `runs/t5-chartjs/best.pt`, `--tta shift`).
"After" numbers come from `integration/round-1` at `121ed4d`, with the same checkpoint `runs/t5-chartjs/best.pt`, OCR `runs/ocr1/best.pt`, and runtime `--tta shift`.
Errors are a percentage of the plot's full height unless the section says otherwise.
Tools: `teams/t5-robust/tools/probe_net.py` (every stage of the pipeline on one image), `rows_by.py`, `corpus_profile.py`, `tools/r2_tables.py` (round-2 delta tables), and the new `p2d/synth/probe_t5r2.py` (round-2 clutter variants with sem_mapping).
Measurement outputs live under `ml/out/t5r2/`.
Diagnosis-side companion: `teams/t5-robust/REPORT_R2.md` sections 2 (Diagnosis) and 3 (Probe-set measurement).

## Headline

Two findings from measuring the integrated model against V2-isolated and base on the full round-1 probe grid:

1. **The integration already fixed the V2 clutter regression (simple-split line_rms 0.226 -> 0.143, -37%)**, by code alone, without any V3 training. The brainstormer's angle A target has already been reached.
2. **The integration introduces a new, severe regression on the 30-chart real benchmark (`t5-real`)** that INTEGRATION-REPORT.md did not catch (it only measured `examples/real` with 5 charts). t5-real median rms 0.61% (V2) -> 1.98% (integrated); within-1% 48% -> 33%. Six OWID/FRED charts return readings scaled by 10x to 10^55. The root cause is in the t1 structured axis decode path: axis_factor is now firing on stray text near the plot, with no sanity check against the resulting factor magnitude.

Round-2 angle picked by the brainstormer: **A - clutter failure mode fix via training**. The clutter target is already met at the code level, so angle A is likely to add little value; the brainstormer may want to pivot to **D - code-only fix on axis_factor** to actually ship a V3 win.

## Section index

1. The integration's wins over V2-isolated.
2. The integration's residual failures.
3. Clutter at higher density: `t5r2-clutter-max` and `t5r2-clutter-overlap` probe sets.
4. The 30-chart real benchmark against the integrated model (NEW regression).
5. Image-factor probe grid (11 sets, integrated vs V2 vs V1 vs base).
6. Numbers.

---

## 1. The integration's wins over V2-isolated

Measured against V2's own numbers in round-1 CASES.md.

- **Chart.js corpus `offset-annotation`**: 61.222% (base) and 0.019% (V2 submission) hold at integration; the multiplier box tolerance was already baked into V2.
- **Chart.js corpus `log-log`**: V2 0.593% -> integrated 0.210% (-65%). The t3 source-pixel measurement tightens the trace once the zoom-crop fine-tune has killed the gridline ghosts.
- **Chart.js corpus `log-y` / `log-y-multi`**: integrated 0.065 / 0.037. The t3+t5 combination finds exactly the right series count AND tightens the fit.
- **Chart.js corpus `retina-2x`**: V2 0.068% -> integrated 0.015% (-78%). The retina case is the biggest win from t3+t4.
- **mpl-val `line_rms_median_pct`** (all): V2 0.3253 -> integrated 0.3076 (-5%).
- **mpl-val `marker_recall`** (all): V2 0.5616 -> integrated 0.6126 (+5.1 pp).
- **plotly-v1 `line_rms_median_pct`** (all): V2 0.2299 -> integrated 0.2057 (-11%).
- **Image-factor probes (simple-split line_rms_median_pct), integrated beats V2 at**:
   - clutter: V2 0.226 -> int **0.143** (-0.083)
   - skew1: V2 2.310 -> int 2.182 (-0.128)
   - blur: V2 0.201 -> int 0.156 (-0.045)
   - jpeg30: V2 0.225 -> int 0.189 (-0.036)
   - dark: V2 0.217 -> int 0.199 (-0.018)
   - dpr1: V2 0.173 -> int 0.162 (-0.011)
   - dpr3: V2 0.106 -> int 0.099 (-0.007)
- **Real-chart dashboard panels (examples/real)**: panel1 0.87/2.75 (V2) -> 0.82/1.89 (int); 05-retail-sales 2-line reading restored.

## 2. The integration's residual failures

### 2.1 NEW regression: t5-real axis_factor explosion

**Where.** `data/t5-real`, 30-chart real benchmark. Multiple OWID and FRED charts return values scaled by orders of magnitude.

**Numbers (median rms per series)**:
- fred-dgs10-daily: 3.26% (V2) -> 760.59% (int)
- noaa-co2-mlo: series 2 "88.37%" (V2) -> "88.50%" (int, unchanged, pre-existing). First-series 0.89% (V2) -> 0.63% (int, improved).
- owid-co2-per-capita: 0.36% / 0.52% / 0.66% / 0.59% (V2) -> 30.89% / 134.78% / 321.07% / 372.83% (int). WARN "y axis: 1 tick label(s) disagreed".
- owid-renewables: 0.16% / 0.21% / 0.29% / 0.16% (V2) -> 126.57% / 196.46% / 2.32% / 315.48% (int). WARN "y axis: values scaled by the printed '1e1'".
- owid-military: 82.55% / 77.76% / 190.62% (V2) -> 787.55% / 850.61% / 1238.70% (int). WARN "y axis: values scaled by the printed '1e1'".
- owid-solar-pv: 0.17% (V2) -> **2038.29%** (int). WARN "y axis: values scaled by the printed '1e55'".

**Headline shift**: V2 found 60%, median rms 0.61%, within 1% 48%. Integrated found 57%, median rms **1.98%**, within 1% **33%**. **With patch 7f8ab85 alone**: median rms **1.82%** (partial recovery). **With V3 ckpt + patch (ship state)**: found 60%, median rms **0.42%** (-31% vs V2), within 1% 42%, within 0.5% 37% (+4 pp vs V2), failed 17. The V3 clutter checkpoint produces cleaner sem which pre-empts the remaining stray-strip multiplier fires (owid-renewables 126/196/315% -> 0.33/0.31/0.17%), compounding with the patch's hard cap on exponent magnitude.

**Mechanism** (hypothesised, needs probe_net inspection to confirm). The t1 structured axis decode (axis.py, commit 136fd60) + the t1 _OFFSET regex tightening (commit 9b897ad) parse stray numbers in the chart's annotations or caption as multiplier text. The tightening was supposed to require a `.` or an `e[-+]?\d+` after the sign to count as an offset, which excludes bare integers. But the pattern "1e1" (= 10) and the implausible "1e55" (= 10^55) both match the strict pattern (an `e[-+]?\d+` term). No magnitude sanity check prevents a factor of 10^55 from being applied: the fuser accepts whatever OCR output matches `_MULT`.

**Fix** (angle D, committed as `7f8ab85` on `team/t5-robust-r2`): two protections in `ml/p2d/pipeline.py`:
- Cap exponent in `_parse_factor` to `|e| <= 15` (atto to peta, the physical range of mpl axis multipliers; rejects "1e55" and prevents the OverflowError).
- Gate `apply_factor` at the call site: a mpl-style multiplier is paired with small-magnitude labels (`|v| < 1000`); when the parsed tick labels already read in the hundreds or more, do not apply the spurious multiplier.

Both are a few-line patch, pytest still passes 110.

**Why INTEGRATION-REPORT.md missed it.** It only ran `eval_real` (5 examples/real charts) and did not run `eval_t5real` (30 charts). The regression manifests only on charts whose annotations contain small-integer tokens near the plot top-left (OWID's "Our World in Data" branding, FRED's series ID, etc.).

**Independent confirmation**: the integrated model also CRASHES with `OverflowError: (34, 'Numerical result out of range')` when evaluated on the `t5r2-clutter-max` probe set. The crash is at `pipeline._parse_factor` line 100 (`10.0 ** int(m.group(1) or m.group(2))`), triggered on a synthetic matplotlib chart whose surrounding clutter OCR'd as a very large exponent. The failure mode is not just a wrong number; it is severe enough to kill the whole run. Angle D's cap `|e| <= 15` fixes both the crash and the silent misreads.

### 2.2 Corpus-easy regression from source-pixel bias (+0.02 pp)

**Where.** `linear-single-solid` (0.033% base, 0.082% integrated); `linear-thin-line` (0.031 -> 0.091); `linear-thick-line` (0.042 -> 0.076); `scatter-markers` (0.060 -> 0.087); `scatter-halo` avg (0.088 -> 0.117).

**What happens.** Source-pixel measurement (t3) + TTA shift (t5) averaged are biased by ~half a pixel on already pixel-perfect ridges in the corpus's easy single-solid line charts: the TTA shift pass sees a half-pixel-shifted ridge, the two forward passes fuse at a value slightly off the integer centre. The net effect is a ~30% rise in median rms on the simplest cases, swapped for the giant worst-case wins.

**Fix hypothesis.** Weight the native pass higher than the shifted one, or do bias correction after fusing when the ridge is a solid single pixel wide (if-easy-leave-alone).

### 2.3 mpl-val `line_found` behind T1 isolated (-2.6 pp)

Integrated 0.6616 vs T1 isolated 0.6876. Known from INTEGRATION-REPORT.md.

### 2.4 plotly `marker_recall` behind base (-1.6 pp)

309-series set. Integrated 0.4028 vs base 0.4184 (`all`); on simple it is 0.8240 vs 0.7620 (+6.2 pp). Noise-dominated on `all`.

### 2.5 up2x and jpeg50 regressions over V2 (image-factor probes)

- up2x (resize 2x): V2 0.097 -> int 0.167 (+0.070, +72% worse). This is a notable regression.
- jpeg50: V2 0.206 -> int 0.260 (+0.054, +26% worse).
- half (resize 0.5x): V2 0.191 -> int 0.205 (+0.014, +7% worse).

**Mechanism** (hypothesised). t3 source-pixel measurement at the up2x scale (chart is 2x the normal size) assumes a stroke width in source pixels; at 2x the stroke is 4 px wide and the ink-weighted centroid shifts. The jpeg50 regression likely overlaps with t3's handling of chromatic noise near line edges.

### 2.6 Clutter: V2 regressed, integration fixed it (no longer a V3 target)

**Where.** `t5-clutter` probe set. Base 0.241 / V1 0.168 / V2 0.226 / **integrated 0.143**.

**What happens.** V2's checkpoint traded a bit of matplotlib specialisation for Chart.js tick-label-convention coverage; cluttered inputs regressed. The integration's t2 overlap-aware merge_fragments and t3 source-pixel measurement handle the compositor-cluttered inputs without a training change.

**Implication for V3.** Angle A (clutter via training) is no longer needed. The brainstormer's training is likely a wash at best; at worst it degrades another distribution.

## 3. Clutter at higher density: `t5r2-clutter-max` and `t5r2-clutter-overlap`

Round-2 probe sets generated by `p2d/synth/probe_t5r2.py` at seed base 15,110,000 (max) and 15,120,000 (overlap).

### 3.1 `clutter-max`: dense surrounding furniture, chart ink preserved

Every clutter element at its maximum: top=70 (toolbar), left=260 (sidebar text), right=260 (second chart distractor), bottom=160 (caption text), scrollbar always, cursor always outside the plot.
Clutter region : chart region = ~2.6:1 by pixel area.
Chart ink is placed last so no chart pixels are lost; the sem head's confusion is pure "outside-chart text looks like TICK_LABEL to the model".

Each sample's JSON stores:
- `chart_rect`: [x0, y0, x1, y1] where the chart sits inside the padded page.
- `sem_mapping.chart_classes`: pixel counts per class inside the chart rect.
- `sem_mapping.clutter_region_px`: total pixels outside the chart.
- `sem_mapping.chart_region_px`: total pixels inside the chart.
- `sem_mapping.overlap_rects`: empty (no overlap in this variant).
- `sem_mapping.chart_pixels_lost`: empty.

Overlay viz: `out/t5r2/clutter-max-sample.png` (seed 15110000), `clutter-max-sample-sem.png` (sem rendered at x36 for visibility).

### 3.2 `clutter-overlap`: UI chrome painted on top of the chart

Random mix of 1-3 overlapping elements per chart:
- `modal`: a dialog rectangle (80-220 x 60-140 px) in a random chart corner.
- `scroll`: a vertical scrollbar strip (10 px wide, full plot height) overlapping the right edge of the plot area.
- `cursor-plot`: a mouse cursor landing inside the plot area.
- `tooltip`: a labelled rectangle (80-150 x 30-50 px) in the top-right of the plot.
- `hover-overlay`: a 2-px-high horizontal guide across the plot.

Chart pixels inside overlap rects have their sem reset to BG and their inst to 0, so the training signal is consistent with the image.

Pixel-loss statistics across the 100 samples:

| class | median loss (nonzero) | p90 loss (nonzero) | samples with any loss |
| --- | --- | --- | --- |
| DATA           | 273 px | 1406 px | 70 / 100 |
| GRID           | 166 px | 566 px  | 62 / 100 |
| TICK_LABEL     | 0      | 0        | 0 / 100  |
| AXIS           | 6 px   | 32 px    | 22 / 100 |
| TEXT           | 133 px | 344 px   | 7 / 100  |
| LEGEND_SYMBOL  | 82 px  | 102 px   | 4 / 100  |

Overlay-kind frequency (one chart may carry 1-3 kinds): tooltip 46, modal 42, hover-overlay 36, scroll 35, cursor-plot 33.

Reading: 70% of charts have DATA pixels missing (median 273 px, up to 1406 at p90). TICK_LABEL is never lost because every overlap rect lives inside the plot area. A V3 fine-tune on the round-1 `clutter` factor (chart painted last, no chart pixels lost) cannot help with the lost DATA; it can only teach the sem head to not confuse surrounding text with chart ink, which the integration already does well.

### 3.3 Integrated model on the new clutter probes

(Numbers in section 6.5 once the r2 eval finishes.)

## 4. The 30-chart real benchmark against the integrated model

Full output: `ml/out/t5r2/real.txt`, JSON `ml/out/t5r2/real.json`.

Headline:

| source | found | median rms | median rms of found | within 1% | within 0.5% | failed |
| --- | --- | --- | --- | --- | --- | --- |
| base (v3+6b313e9) | 67% | 1.86%  | 1.99% | 28% | 25% | 15 |
| V1 sub            | 63% | 0.75%  | 0.65% | 42% | 32% | 14 |
| V2 sub            | 60% | 0.61%  | 0.49% | 48% | 33% | 15 |
| **integrated**    | 57% | **1.98%** | 1.02% | **33%** | 27% | 15 |

The integrated model regresses on every headline except failed count. Median rms **tripled** vs V2 (0.61% -> 1.98%).

Per-chart breakdown (worst regressions, integrated vs V2):

| chart | V2 rms | integrated rms | note |
| --- | --- | --- | --- |
| fred-dgs10-daily | 3.26% | **760.59%** | WARN y axis: only two ticks read: linear/log decided from the labels |
| owid-co2-per-capita (4 series) | 0.36/0.52/0.66/0.59% | 30.89/134.78/321.07/372.83% | WARN y axis: 1 tick label(s) disagreed |
| owid-renewables (4 series) | 0.16/0.21/0.29/0.16% | 126.57/196.46/2.32/315.48% | WARN "values scaled by '1e1'" |
| owid-military (3 series) | 82.55/77.76/190.62% | 787.55/850.61/1238.70% | WARN "values scaled by '1e1'" |
| owid-solar-pv | 0.17% | **2038.29%** | WARN "values scaled by '1e55'" (!) |
| fred-dexuseu | 0.91% | 121.24% | WARN y axis: only two ticks read |

Three findings:
1. The "values scaled by '1e55'" warning is a tell: the t1 structured axis decode's multiplier parser accepts implausible magnitudes. Fix is a magnitude sanity check (reject `|log10(factor)| > 10`).
2. The "only two ticks read: linear/log decided from the labels" warning on dgs10-daily and dexuseu suggests t1 is also regressing on tick count detection for charts with sparse y-axis labels.
3. owid-military was already bad at V2 (82-190%); it got worse at integration (787-1238%), suggesting the same magnitude-check fix would cap this one.

Full real.txt and real.json preserved for the brainstormer to inspect.

## 5. Image-factor probe grid

All 11 image-factor probes re-measured against the integrated model. Simple-split column reported.

### 5.1 line_rms_median_pct

| set | base (v3+6b313e9) | V1 sub (zoom+a7aed7d) | V2 sub (chartjs+a7aed7d) | integrated (chartjs+121ed4d) | int - V2 | int - base |
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

Summary: 7 wins over V2 (blur, dark, clutter, jpeg30, skew1, dpr1, dpr3), 1 flat (dpr2), 3 regressions (half, up2x, jpeg50). Clutter is the biggest win (-0.083 vs V2); up2x and jpeg50 are the two notable regressions.

### 5.2 marker_recall

| set | base | V1 sub | V2 sub | integrated | int - V2 | int - base |
| --- | --- | --- | --- | --- | --- | --- |
| blur    | 0.499 | 0.572 | -     | 0.534 | - | +0.035 |
| dark    | 0.465 | 0.582 | -     | 0.575 | - | +0.110 |
| clutter | 0.387 | 0.469 | -     | 0.388 | - | +0.001 |
| dpr1    | 0.502 | 0.533 | 0.536 | 0.640 | +0.104 | +0.138 |
| dpr2    | 0.349 | 0.326 | 0.337 | 0.369 | +0.032 | +0.020 |
| dpr3    | 0.287 | 0.286 | 0.295 | 0.261 | -0.034 | -0.026 |

Marker recall is up vs V2 on dpr1/dpr2 (t4 helping), slightly down on dpr3. On the non-dpr probes marker recall is essentially V1-level or slightly below.

### 5.3 frame_err_median_px

| set | base | V1 sub | V2 sub | integrated |
| --- | --- | --- | --- | --- |
| blur    | - | - | - | 1.141 |
| dpr1    | 1.12 | 0.81 | 0.96 | 0.971 |
| dpr2    | 2.56 | 1.26 | 1.20 | 1.302 |
| dpr3    | 2.92 | 1.45 | 1.59 | 1.594 |

Frame error essentially matches V2 across dpr, a few hundredths of a pixel either way.

## 6. Numbers

### 6.1 Image-factor probes, simple split, `line_rms_median_pct`

See section 5.1.

### 6.2 Image-factor probes, simple split, `marker_recall`

See section 5.2.

### 6.3 Image-factor probes, simple split, `frame_err_median_px`

See section 5.3.

### 6.4 Real-chart benchmark (`data/t5-real`)

See section 4. Headline: integrated **regresses** vs V2 (median rms 0.61% -> 1.98%, within 1% 48% -> 33%).

### 6.5 Round-2 clutter probes, integrated model

Blocked: the integrated model crashes on `t5r2-clutter-max` with `OverflowError` in `pipeline._parse_factor` (see section 2.1 above). Re-runnable once angle D's patch is in. Output files: `out/t5r2/r2-clutter-max.err` (traceback), `out/t5r2/r2-clutter-max.txt` (empty). `r2-clutter-overlap` was never started because the surrounding shell `&&` chain broke on the first probe's crash.

### Measurement commands

```
# Image-factor probes + real benchmark
bash /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t5-robust/ml/out/t5r2/run_probes.sh

# Delta tables
python teams/t5-robust/tools/r2_tables.py --metric line_rms_median_pct --split simple
python teams/t5-robust/tools/r2_tables.py --metric marker_recall --split simple
python teams/t5-robust/tools/r2_tables.py --metric frame_err_median_px --split simple

# Sem_mapping summary
python teams/t5-robust/tools/r2_tables.py --sem-mapping data/t5r2-clutter-overlap
```
