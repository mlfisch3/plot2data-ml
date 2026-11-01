# Architecture

How plot2data-ml turns a chart image into the numbers that drew it.

## 1. The problem

A publication-quality line, scatter or line-plus-markers chart is a sparse map from an underlying numeric table to coloured pixels on a rectangular axis system.
The chart is often all that survives: a screenshot in a PDF, a figure in a paper, a dashboard panel in a bug report, a photographed slide.
The job is to recover the numeric table as faithfully as the rasterisation allows, on an unseen rendering.

## 2. Pipeline at a glance

```
  image.png
      |
      v
+--------------+   +--------------+   +-------------+   +----------+
|  placement   |-->|   PlotNet    |-->|  decoding   |-->| source-  |
| (fit canvas) |   |  U-Net heads |   | (peaks,     |   | pixel    |
+--------------+   |  sem/heat/   |   |  clusters,  |   | refine   |
                   |  emb)        |   |  chains)    |   +----------+
                   +--------------+   +-------------+        |
                                                             v
   +------------+   +--------------+   +--------------+   +----------+
   |   output   |<--|   sampling   |<--| calibration  |<--| tick     |
   |  CSV, PNG, |   | (auto step)  |   | (RANSAC +    |   | labels   |
   |  JSON      |   +--------------+   |  axis.py     |   | (OCR)    |
   +------------+                      |  structured  |   +----------+
                                       |  decode)     |
                                       +--------------+
```

Each step maps a geometric or symbolic structure onto its next representation.
The network does the perceptual work; everything downstream is deterministic numerics.

## 3. Component by component

### 3.1 Placement (`ml/p2d/data.py:fit_transform`, `extract.prepare`)

The source image is placed on a 768 × 512 canvas by one affine transform that fits the long side.
Everything the pipeline measures - peaks, ridges, labels, frame corners - comes back through the inverse of this transform at the end, so results are reported in the source image's pixel space.

As of round-2's integration, images large enough to fit at native scale are not downscaled: the network runs on them at their original resolution and the fit transform becomes a crop plus pad.
This matters for high-DPR screenshots and retina charts, which previously lost half their resolution.

Pixel convention everywhere in `ml/`: the centre of pixel column i is x = i.

### 3.2 PlotNet (`ml/p2d/model.py`)

The learned front end.
A U-Net with an ImageNet-pretrained ResNet-34 encoder and a full-resolution stem (3 → 16 channels) that is fused with the decoder's output through a 3 × 3 conv to 32 channels so the final heads have access to original-resolution evidence.
Three heads, each a single 3 × 3 conv:

- `sem` - 7 classes per pixel: background, data ink, legend symbol, axis, grid or reference line, tick label, other text.
  "Data ink" is where the series lives even through antialiasing and semi-transparency; the other classes decide what should be excluded from the pipeline's attention.
- `heat` - 6 heat maps at full resolution:
  1. series centre line (drawn through dashed gaps and occlusions)
  2. marker centre
  3. polyline vertex
  4. labelled x tick
  5. labelled y tick
  6. plot-frame corner
- `emb` - an 8-dimensional per-pixel embedding trained with a discriminative loss (within-cluster compact, between-cluster separated) so that pixels of a single series cluster together and overlapping series separate even when they share a colour range.

The network sees a 768 × 512 input (or native resolution if the chart fits).
Outputs are at full resolution for `sem` and `heat`, and at /2 for `emb` (dense pixel-level embeddings would be too heavy).

Training: AdamW, warmup 500 then cosine, bf16 autocast, channels_last, batch 8.
Loss: weighted cross-entropy for `sem`, quality-focal loss for `heat` normalised per-channel by batch-level mass, discriminative loss for `emb`.

Current production checkpoint `runs/t5r2-clutter/best.pt` is a 3,000-iter fine-tune of `runs/t5-chartjs/best.pt`, which was itself a 3,000-iter fine-tune of `runs/t5-zoom/best.pt`, which came from the main training on matplotlib + Plotly plus the house-style presets.
The clutter fine-tune added UI-chrome overlay samples and chart-with-surrounding-furniture samples to teach the sem head to call outside-chart text BG even when it looks axis-like.

### 3.3 Decoding (`ml/p2d/extract.py`)

Takes the network output and returns a dict of frame, ticks, series, markers in canvas pixels.

- **Sub-pixel peak refinement** fits a parabola through the log heat around each argmax; the parabola's vertex gives the sub-pixel location (exact for an isotropic Gaussian, close enough otherwise).
- **Frame** is the four plot corners from the corner heat map.
- **Label boxes** are connected components of the `TICK_LABEL` sem class, dilated and filtered for size.
- **Tick positions** are the sub-pixel maxima of the x-tick and y-tick heat maps; labels are grouped to the nearest tick along the axis.
- **Series** are found by clustering the embedding (with per-image key offsets so pixels from one chart stay separate from another).
  Each cluster's data pixels are projected per column; peaks are chained into a trace by a column-tracker with a cost that penalises large jumps.
  Fragments of the same cluster are merged.
- **Markers** are peaks of the marker heat map, grouped into series by colour similarity on the source pixels and then by embedding.

As of round 2, the merge-fragments stage uses an overlap-aware join via Hungarian assignment, allowing chain pieces that overlap in x to merge rather than being treated as duplicates (crossing curves, parallel runs).

### 3.4 Line refinement on source pixels (`ml/p2d/measure.py`, called by `extract.refine_lines`)

For each line series, every source-image column that the trace covers is remeasured on the original pixels (not the heat map).
The measurement is the ink-weighted centroid of pixels whose colour lies on the paper-to-series-colour blend segment: pure antialiasing is counted at its light-ink fractional weight.
Line stroke width is estimated from the column mass over sqrt(1 + slope²), and used as a prior on the measurement window.
At polyline vertices, where a column centroid averages both flanks of a peak, two straight lines are fit to the flanks and intersected to recover the sub-pixel apex.

This is where the round-3 `measure.py` rewrite lives.
It replaced an earlier window-centroid approach that was neutral on the median but regressed on vertex-heavy and anti-aliased charts.

### 3.5 Marker measurement (`ml/p2d/markers.py`)

For each marker series, each heat-map peak is re-measured on the source pixels: a Gaussian mixture is fit over the peak's local heat and the markers' centres come from the fit's component means.
Isolated marker shape is classified by a size-and-shape test, and the measurement is the ink centroid for symmetric markers, the shape's canonical anchor for asymmetric ones.
Overlapping markers (dense scatters, marker rows along a line) are split by the mixture; a dash veto removes false positives from line stroke.

Round-4 added a `sem[TEXT]` veto to reject digit false positives that look like markers at low size.

### 3.6 Tick label reading (`ml/p2d/ocr.py`)

Each tick's label crop goes through a small convolutional CTC recogniser (TickReader).
The crop is normalised (resize to 32 × 192, Agg stamp detection, 90-degree rotation for tall crops introduced in round 1).
`parse_value` turns the text into a number, handling `1,000`, `-2.5`, `45%`, `$1.2M`, `3e5`, `10^3`, `2x10^4`, `25 t`, `500 billion t`, `10b`, unicode minus signs, and the common OCR corruptions ("`0^3`" when the "1" was lost, "`1,000 1 `" when a trailing "t" misreads to "1").
A strict path accepts clean canonical labels; a lax path (round-5) runs when strict yielded fewer than two values on an axis, extracting the leading number from garbled OCR of composite labels like "0 births" or "80,000 kWh" while treating single-letter SI prefixes touching a letter tail as unit-word initials, not multipliers.

### 3.7 Axis structured decode (`ml/p2d/axis.py`)

The round-1 win from team 1.
Each axis is decoded jointly over all its ticks: beam-search top-k CTC readings per label, RANSAC over pairs for linear or log fits, scoring each hypothesis by (a) number of inlier labels, (b) nice-step bonus, (c) expected-text penalty on labels the fit forced to be something not in the beam, (d) log-decade enforcement (log fits must span at least one decade), (e) alignment-to-step prior (ticks on a locator's grid are preferred over ticks consistently offset by a non-nice amount).
Round-3 added a nice-step tiebreak for 2-tick axes that rejects leading-zero integer readings a tick locator would never print (fred-dgs10-daily's "1" misread as "13").
Round-5 added a sub-decade log penalty (log cannot win over linear when the chosen values span less than one decade; 03-women-men's five years).

### 3.8 Calibration (`ml/p2d/calibrate.py`)

The RANSAC-plus-least-squares fit of value to pixel position, with linear and log both tried and the one that explains more ticks kept.
A fallback for 2-tick axes decides linear or log from label content when the fit alone cannot.

### 3.9 Axis-factor detection (`ml/p2d/pipeline.py axis_factor`)

Reads the printed multiplier at an axis end (`×10^6`, `+1.2e3`, `in millions`).
Scans a strip near the axis spine for text components the sem didn't surface, decodes each with the OCR, and recognises patterns like `1e6`.
Round-2 added strip-end scanning for text that is NOT in a sem component (needed for `offset-annotation`'s `1e6` touching the top tick label).
Round-5 added a spine-margin filter (reject matches whose x-centre is beyond 10% of the axis width from the spine; stops legend text from being read as a factor) and a plausibility gate (skip the factor if existing tick labels already cover magnitude > 1000; mpl prints a multiplier only for small-magnitude labels).

### 3.10 Sampling (`ml/p2d/sampling.py`)

A marker series returns one point per drawn marker.
A line series is resampled uniformly in x with an automatically chosen step: the coarsest step whose linear reconstruction stays within the trace's uncertainty everywhere, so the finest feature on the curve sets the step for the whole curve.
Caller can override with `--step-px`.

### 3.11 Test-time augmentation (`ml/p2d/tta.py`)

`--tta shift` makes the network run on both the original image and a half-pixel-shifted copy, then fuses the heat maps.
This pulls sub-threshold connected components over threshold (the Chart.js `1e6` multiplier case) and reduces false-negative markers on halo scatters.
The TTA pass is the default in the shipped CLIs (`p2d.serve` and `p2d.pipeline`); pass `--tta off` to disable.

## 4. Process flow for a single image

```
                  original image
                        |
                 fit_transform (768 x 512 or native)
                        |
                      canvas
                        |
        +---------------+---------------+
        |                               |
     TTA shift                     original pass
        |                               |
        +---------------+---------------+
                        |
                    heat maps,
                    sem map,
                    embeddings
                        |
                        v
             +-------------------------+
             | extract.extract(...)    |
             +-------------------------+
             | - plot_frame -> frame   |
             | - label_boxes -> boxes  |
             | - peaks + group_labels  |
             |   -> ticks per axis     |
             | - cluster_embeddings    |
             |   -> series ids         |
             | - column_runs +         |
             |   peel_chains           |
             |   -> raw traces         |
             | - merge_fragments       |
             |   (Hungarian overlap)   |
             | - drop_duplicates       |
             | - refine_markers        |
             | - refine_lines ->       |
             |     measure.measure     |
             | - refine_ticks (joint-  |
             |   affine) + bias snap   |
             +-------------------------+
                        |
                 Extraction (canvas space)
                        |
          +-------------+-------------+
          |                           |
      pipeline.read_ticks        pipeline.axis_factor
          |                           |
       (OCR per tick)            (strip-end scan + regex)
          |                           |
          v                           v
     tick values, texts          multiplier/offset text
          |                           |
          +-------------+-------------+
                        |
                        v
              axis.decode_axis per axis
          (joint beam-decode + log/linear fit)
                        |
                        v
                 x fit, y fit (linear or log)
                        |
                        v
             to_data(ex, xfit, yfit)
          (map canvas -> value, auto-sample)
                        |
                        v
             Result: series, warnings,
             axis info, tick reads
                        |
                        v
                CSV, overlay PNG, JSON
```

Everything upstream of `axis.decode_axis` is pure geometry on canvas pixels.
Everything downstream is numeric interpretation (OCR + fitting + sampling).
The decoupling matters: the geometric gains from round-2's merge_fragments compose cleanly with the numeric gains from round-5's lax parse_value and sub-decade log penalty.

## 5. Deployment

Three ways to run the extractor today:

### 5.1 Local test bench

```sh
cd ml
source ../.venv/bin/activate
python -m p2d.serve --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt
# open http://localhost:8417, drop or paste a chart image
```

The server page runs the extractor on your machine; nothing is uploaded.
It is a test bench, not the production UI.

### 5.2 Command line

```sh
python -m p2d.pipeline chart.png \
   --ckpt runs/t5r2-clutter/best.pt \
   --ocr runs/ocr1/best.pt \
   --csv out.csv \
   --overlay out.png
```

CLI output is a JSON summary to stdout, a CSV to `--csv`, and an overlay PNG to `--overlay`.
Pass `--tta off` to drop the TTA fusion for a 2× speed-up at the cost of some precision; pass `--step-px N` to override the automatic resampling step.

### 5.3 Browser app (classical engine; ML models planned)

The repo root (`src/`, `index.html`) is the browser app inherited from the classical `plot2data` project, which still runs the hand-tuned extraction entirely in the browser.
The intended migration path is to export the PlotNet and TickReader to ONNX (`p2d.export` already does this) and run the models via `onnxruntime-web` inside the same browser app, replacing the classical engine while keeping the same UX (crop, calibrate, export CSV/XLSX).
Not yet shipped.

## 6. Repository layout

- `ml/p2d/` - the production pipeline. Each stage above is one or two files.
- `ml/p2d/synth/` - synthetic chart generators (matplotlib with house-style presets, Plotly through kaleido, Chart.js through Chrome puppeteer).
- `ml/data/` - datasets.
  - `mpl-v1`, `mpl-v2`, `mpl-val` - matplotlib training and validation.
  - `plotly-v1` - 12,000 Plotly training charts.
  - `t5-chartjs` - 4,000 Chart.js charts for the t5-chartjs training.
  - `t5-clutter` - clutter-augmented samples for t5r2-clutter.
  - `t5-real`, `t5-real-100` - the 30-chart and 110-chart real-world benchmarks (publisher charts with published numeric truth).
  - Dozens of per-team probe sets (`t1-probe`, `t2-cross`, `t3-ticks-r2`, `t4r2-linemk`, ...) for diagnosing specific failure modes.
- `ml/runs/` - training outputs.
  - `v1`, `v2`, `v3` - the pre-contest training sequence.
  - `t5-zoom`, `t5-chartjs`, `t5r2-clutter` - the round-1/round-2 fine-tunes that produced the current production checkpoint.
  - `ocr1` - the tick reader (unchanged across the contest).
- `ml/tests/` - 178 pytest cases; every substantive change in the pipeline adds a test.
- `ml/teams/` - per-team catalogues and reports from the research contest.
- `src/`, `index.html` - the inherited browser app and its classical engine (kept as baseline, not production target).
- `corpus/` - the classical engine's Chart.js corpus (18 charts, used by `eval_corpus`).
- `examples/real/` - 5 real screenshots the pipeline is tested on by hand measurement.
- `docs/` - this file and `CONTEST.md`.
- `tools/` - scripts shared between the ML and classical sides (classical runner, chart.js corpus utilities).

## 7. Current measured performance

See `ml/RESULTS.md` for the full tables; the headlines on `main`:

| set | main (v5) | pre-contest v3 | classical |
| --- | --- | --- | --- |
| mpl-val 200 line_found (all) | 69% | 55% | 14% |
| mpl-val 200 line_rms_median | 0.28% | 0.44% | 0.38% |
| plotly-v1 150 line_found | 82% | 75% | 13% |
| Chart.js corpus worst case | 0.56% | 61.22% | 0.074% |
| t5-real-100 within-0.5% (110 charts) | 50% | n/a | n/a |
| t5-real-100 failed | 20 / 110 | n/a | n/a |

Numbers in RESULTS.md are reproducible from `main` using the commands in that document, under the shared GPU lock pattern `flock /tmp/gpu.lock python -m p2d.evaluate ...`.
