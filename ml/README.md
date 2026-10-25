# plot2data-ml: a learned extractor

This directory replaces the hand-tuned detection stages of the classical engine (`../src/engine/`) with a network trained on synthetic charts.
Charts are cheap to make and every number that drew them is known, so the training data is unlimited and its labels are exact.

## The idea in one paragraph

A plotting library is a function from numbers to pixels.
We run it forwards thousands of times with random data and random styling, record exactly where every series, marker, tick and frame corner landed, and train a network to recover that geometry from the pixels alone.
The network does the perceptual work that was brittle by hand: which ink is data and which is grid, legend, text or axis; which pixels belong to which series where they cross or share a colour; where a dashed line runs through its gaps; where the labelled ticks sit.
Precise measurement and arithmetic stay explicit: sub-pixel peak fitting, a re-measurement of each line on the source pixels, a robust fit of tick values to tick positions, and linear/log selection.

## Pipeline

1. **Placement.** The image is scaled to fit a 768 x 512 canvas (`data.fit_transform`), one affine transform that every output is mapped back through.
2. **PlotNet** (`model.py`): a U-Net over an ImageNet-pretrained ResNet-34 with a full-resolution stem, and three heads:
   - `sem`: per-pixel class - background, data ink, legend symbol, axis, grid/reference line, tick label, other text;
   - `heat`: six heat maps - series centre lines (drawn *through* dashes and occlusions), marker centres, polyline vertices, labelled x ticks, labelled y ticks, plot-frame corners;
   - `emb`: an 8-dimensional per-pixel embedding trained with a discriminative loss, so pixels of one series cluster together.
3. **Decoding** (`extract.py`): peaks and ridges refined to sub-pixel precision by a parabola through the log heat (exact for a Gaussian); series found by clustering embeddings; one centre-line sample per canvas column; marker centres from the marker heat map.
4. **Refinement on the source pixels** (`extract.refine_lines`): each line is re-measured per source column as the ink-weighted centroid of the pixels whose colour lies on the paper-to-series-colour blend segment. At vertices, where a column centroid averages both flanks of a peak, the network's own centre-line estimate stands.
5. **Tick labels** (`ocr.py`): each labelled tick is paired with the tick-label component nearest it along the axis; the crop is read by a small convolutional CTC recogniser trained on the synthetic labels, and parsed (`1,000`, `45%`, `$1.2M`, `10^3`, `2.5e+08`, `-3`).
6. **Calibration** (`calibrate.py`): RANSAC over pairs of ticks in pixel space, least squares over the agreeing ticks, linear and log both tried and the one that explains more ticks kept.
7. **Sampling** (`sampling.py`): a marker series returns one point per marker. A curve is resampled uniformly in x, and by default the step is the coarsest whose linear reconstruction stays within the trace's uncertainty everywhere, so the finest feature on the curve sets the step for the whole curve.

## Synthetic data

`synth/mpl_render.py` draws a random matplotlib chart and records its ground truth.
Label maps are made by re-rendering the same frozen figure once per artist group with everything else hidden, so a pixel's class is whose ink it actually is, antialiasing included.
`synth/series.py` makes the data: random walks, seasonal sales with spikes, spectra with narrow peaks, sparse polylines, steps, growth curves for log axes, point clouds.
`synth/presets.py` adds the house styles of charts people screenshot: Plotly, Excel, news graphics with direct labels, Highcharts, FT, dashboards, offset-spine minimal.
`data.py` places each chart on the canvas with random scale and position, applies JPEG, blur, resampling, noise and clutter backgrounds, and rasterises the targets *after* the geometric transform, from vectors, so they stay sub-pixel exact.

```sh
python -m p2d.synth.build --out data/mpl-v1 --start 0 --count 40000
python -m p2d.train --data data/mpl-v1 --val data/mpl-val --run runs/v1 --iters 24000
python -m p2d.ocr train --data data/mpl-v1 --val data/mpl-val --run runs/ocr1
```

## Measuring

All errors are a percentage of the plot's full height, the unit of `../ACCURACY.md`.
As there, the RMS over every column and the error at turning points are reported separately, because a plot has few peaks and many columns and an average hides clipped peaks.

```sh
python -m p2d.evaluate --ckpt runs/v1/best.pt --data data/mpl-val                  # pixel geometry only
python -m p2d.evaluate --ckpt runs/v1/best.pt --data data/mpl-val --refine         # with source-pixel refinement
python -m p2d.evaluate --ckpt runs/v1/best.pt --data data/mpl-val --oracle-ticks   # end to end, true tick values
python -m p2d.evaluate --ckpt runs/v1/best.pt --data data/mpl-val --ocr runs/ocr1/best.pt   # fully end to end
python -m p2d.eval_corpus --ckpt runs/v1/best.pt --ocr runs/ocr1/best.pt           # the Chart.js corpus, out of distribution
node --experimental-strip-types ../tools/run-classical.ts data/mpl-val out/classical-val.json 300
python -m p2d.score_classical --data data/mpl-val --pred out/classical-val.json    # the classical engine, same metric
```

## Results

See [RESULTS.md](RESULTS.md).
