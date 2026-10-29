# t5-robust round 2: the failure catalogue after integration

Curator's record of what still breaks on charts outside the training distribution, after round-1 integration.
"Before" numbers come from round 1 CASES.md (frozen baseline `main` at `6b313e9`, `runs/v3/best.pt`, no TTA) or from V2-isolated (`team/t5-robust-chartjs`, `runs/t5-chartjs/best.pt`, `--tta shift`).
"After" numbers come from `integration/round-1` at `121ed4d`, with the same checkpoint `runs/t5-chartjs/best.pt`, OCR `runs/ocr1/best.pt`, and runtime `--tta shift`.
Errors are a percentage of the plot's full height unless the section says otherwise.
Tools: `teams/t5-robust/tools/probe_net.py` (every stage of the pipeline on one image), `rows_by.py`, `corpus_profile.py`, and the new `p2d/synth/probe_t5r2.py` (round-2 clutter variants with sem_mapping).
Measurement outputs live under `ml/out/t5r2/`.
Diagnosis-side companion: `teams/t5-robust/REPORT_R2.md` sections 1 (Diagnosis) and 2 (Probe-set measurement).

## Round-2 principle

Diminishing returns.
The integration already dominates the base scoreboard; a V3 submission should either hit a probe set the V2 submission did not or close a documented regression (corpus-easy +0.02pp, mpl-val line_found -2.6pp vs T1 isolated, plotly marker_recall -1.6pp vs base).
Round-2 angle picked by the brainstormer: **A - clutter failure mode fix** (training patch, add clutter samples to the mix).
This file catalogues the integrated model's residual failures, with new probe sets built for angle A.

## Section index

1. The integration's wins over V2-isolated (what no longer breaks here).
2. The integration's residual failures (what still breaks).
3. Clutter at higher density: `t5r2-clutter-max` and `t5r2-clutter-overlap` probe sets.
4. The 30-chart real benchmark against the integrated model.
5. Image-factor probe grid (11 sets, integrated vs V2 vs base).
6. Numbers.

---

## 1. The integration's wins over V2-isolated

Measured against V2's own numbers in round-1 CASES.md.

- **Chart.js corpus `offset-annotation`**: 61.222% (base) and 0.019% (V2 submission) hold at integration; the multiplier box tolerance was already baked into V2.
- **Chart.js corpus `log-log`**: V2 0.580% -> integrated 0.210% (-64%). The t3 source-pixel measurement tightens the trace once the zoom-crop fine-tune has killed the gridline ghosts.
- **Chart.js corpus `log-y` / `log-y-multi`**: V2 0.580 / 0.100 -> integrated 0.065 / 0.037. The t3+t5 combination finds exactly the right series count AND tightens the fit.
- **Chart.js corpus `retina-2x`**: V2 0.068% -> integrated 0.015% (-78%). The retina case is the biggest wins from t3+t4.
- **mpl-val `line_rms_median_pct`**: V2 0.3253 -> integrated 0.3076 (-5%). Steady improvement with no sign of regression.
- **mpl-val `marker_recall`**: V2 0.5616 -> integrated 0.6126 (+5.1 pp). t4's source-pixel marker re-measurement is paying.
- **plotly-v1 `line_rms_median_pct`**: V2 0.2299 -> integrated 0.2057 (-11%). t3 again.
- **Real-chart dashboard panel1 x/y**: V2 0.87 / 2.75 -> integrated 0.82 / 1.89 (-6% / -31%). t3's source-pixel column rounding helps here too.
- **05-retail-sales**: V2 regressed to 1-line reading; integrated restores V1's 2-line reading with 0.69 px x, 1.94 px y.

## 2. Integration's residual failures

### 2.1 Corpus-easy regression from source-pixel bias (+0.02 pp)

**Where.** `linear-single-solid` (0.033% base, 0.082% integrated); `linear-thin-line` (0.031 -> 0.091); `linear-thick-line` (0.042 -> 0.076); `scatter-markers` (0.060 -> 0.087); `scatter-halo` avg (0.088 -> 0.117).

**What happens.** Source-pixel measurement (t3) + TTA shift (t5) averaged are biased by ~half a pixel on already pixel-perfect ridges in the corpus's easy single-solid line charts: the TTA shift pass sees a half-pixel-shifted ridge, the two forward passes fuse at a value slightly off the integer centre. The net effect is a ~30% rise in median rms on the simplest cases, swapped for the giant worst-case wins.

**Fix hypothesis.** Weight the native pass higher than the shifted one, or do bias correction after fusing when the ridge is a solid single pixel wide (if-easy-leave-alone).

### 2.2 mpl-val `line_found` behind T1 isolated (-2.6 pp)

**Where.** Integrated 0.6616 vs T1 isolated 0.6876. T5 V2 was 0.5857 (integrated beats it by 7.6 pp), but T1 isolated reads 2.6 pp more lines.

**What happens.** T1's structured-axis-decode changes calibration; combined with t3's source-pixel shifts, a few lines fall just below the detector's confidence floor at the edge, resulting in slightly fewer "found" lines even though the ones it does find are more accurate.

**Diagnosis candidate.** Compare `line_rms_median` x `line_found` on the mpl-val set between integrated and T1 isolated at the same simple/all split: integrated likely has tighter rms on fewer lines, which is the right trade for a precision-oriented reader but costs the headline count.

### 2.3 plotly `marker_recall` behind base (-1.6 pp)

**Where.** 309-series set. Integrated 0.4028 vs base 0.4184 (`all`); on simple it is 0.8240 vs 0.7620 (+6.2 pp), so this is noise-dominated on `all`.

**What happens.** t4's source-pixel marker re-measurement makes markers more precise (precision +2.4 pp) but drops a handful of borderline ones; on simple charts (which dominate the user story) markers improve.

### 2.4 Clutter: V2 regressed by +35% rms

**Where.** `t5-clutter` probe set. Base 0.241 / V1-sub 0.168 / V2-sub 0.226 / integrated TBD (section 5).

**What happens.** V2's checkpoint traded a bit of matplotlib specialisation for Chart.js tick-label-convention coverage; the net never saw charts inside a page of furniture, so the sem head on cluttered inputs sometimes calls text TICK_LABEL and misses the chart's own labels.

**Fix hypothesis** (brainstormer, round 2): fine-tune on `data/t5r2-clutter` + `data/t5r2-clutter-plotly` with the clutter fraction at ~5-8% of the mix, from `runs/t5-chartjs/best.pt`. Keep the integrated code; swap only the checkpoint.

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

Overlay viz: `out/t5r2/clutter-max-sample.png` (seed 15110000), `clutter-max-sample-sem.png` (sem rendered at *36 for visibility).

Why this variant. The round-1 `t5-clutter` had a mild clutter mix (clutter margins uniformly random up to 260/160, half the time with a second chart, less than half with a scrollbar/cursor). V2 regressed on it by +35% rms. `clutter-max` runs the same seeds in the extreme setting of every single clutter parameter: it tells us whether V2's regression is driven by density (fix will scale with training clutter) or just by any clutter at all (fix saturates fast).

### 3.2 `clutter-overlap`: UI chrome painted on top of the chart

Random mix of 1-3 overlapping elements per chart:
- `modal`: a dialog rectangle (80-220 x 60-140 px) in a random chart corner.
- `scroll`: a vertical scrollbar strip (10 px wide, full plot height) overlapping the right edge of the plot area.
- `cursor-plot`: a mouse cursor landing inside the plot area.
- `tooltip`: a labelled rectangle (80-150 x 30-50 px) in the top-right of the plot.
- `hover-overlay`: a 2-px-high horizontal guide across the plot.

Each sample's JSON stores:
- `chart_rect`: [x0, y0, x1, y1].
- `sem_mapping.overlap_rects`: list of {x0, y0, x1, y1, pre_classes} (pre_classes = sem-class pixel counts BEFORE the overlap was painted).
- `sem_mapping.chart_pixels_lost`: {class_id: pixel_count} summed across all overlap rects, chart ink only.
- `clutter.kinds`: which UI chrome variants are present.

Chart pixels inside overlap rects have their sem reset to BG and their inst to 0, so the training signal is consistent with the image (the chart ink that got painted over is no longer "ground truth to be found"; it is gone).

Why this variant. Separates "sem confused by nearby text" (brainstormer's R2 fix should help) from "chart pixels actually missing" (needs a different approach - cannot reconstruct what the overlay hides). Measuring the integrated model on `clutter-overlap` tells us: of the chart lines lost, how many did the model find elsewhere via neighbour context, and how many did it miss entirely?

### 3.3 Example sem_mapping values

From a few sample runs:

```
seed 15110000 clutter-max
  chart_rect = [260, 70, 718, 395]
  clutter_region_px / chart_region_px = 2.65
  sem classes present in chart rect: 7 (all of BG, DATA, LEGEND_SYMBOL, AXIS, GRID, TICK_LABEL, TEXT)

seed 15120000 clutter-overlap
  kinds = [tooltip]
  overlap_rects = 1
  chart_pixels_lost = {DATA: 111, GRID: 158}

seed 15120001 clutter-overlap
  kinds = [cursor-plot, hover-overlay, modal]
  overlap_rects = 3
  chart_pixels_lost = {DATA: 714, AXIS: 2}
```

The `DATA` loss is the one that matters for RMS: a modal dialog over a chart corner can occlude 500-1000 px of data ridge, which `extract` cannot recover.

## 4. The 30-chart real benchmark against the integrated model

Measured by `p2d.eval_t5real --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt --tta shift`.
Baseline numbers from CASES.md section 9.10.3 (V2-isolated submission).

(numbers in section 6.4 once the eval finishes)

## 5. Image-factor probe grid

All 11 image-factor probes re-measured against the integrated model.
Compared against:
- `base` from CASES.md section 9.5 (frozen main at 6b313e9 + runs/v3/best.pt, no TTA)
- `V1 sub` from CASES.md section 9.5 (runs/t5-zoom + a7aed7d code + --tta shift)
- `V2 sub` from CASES.md section 9.10.2 (runs/t5-chartjs + a7aed7d code + --tta shift)
- `integrated` from this round (runs/t5-chartjs + integrated code + --tta shift)

(numbers in section 6.1-6.3 once the queue finishes)

## 6. Numbers

### 6.1 Image-factor probes, simple split, `line_rms_median_pct` (pending eval queue)

### 6.2 Image-factor probes, simple split, `marker_recall` (pending)

### 6.3 Image-factor probes, simple split, `frame_err_median_px` (pending)

### 6.4 Real-chart benchmark (`data/t5-real`) (pending)

### 6.5 Round-2 clutter probes, integrated model (pending)

### 6.6 Clutter sem_mapping statistics on `t5r2-clutter-overlap` (pending)

### Measurement commands

```
# Image-factor probes
for n in blur dark clutter half up2x jpeg50 jpeg30 skew1 dpr1 dpr2 dpr3; do
  flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
    python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt \
      --data data/t5-$n --tta shift > out/t5r2/$n.txt 2> out/t5r2/$n.err
done

# Real-chart benchmark
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.eval_t5real --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt \
    --data data/t5-real --tta shift --json out/t5r2/real.json > out/t5r2/real.txt 2> out/t5r2/real.err

# Round-2 clutter probes
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt \
    --data data/t5r2-clutter-max --tta shift > out/t5r2/clutter-max.txt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt \
    --data data/t5r2-clutter-overlap --tta shift > out/t5r2/clutter-overlap.txt
```
