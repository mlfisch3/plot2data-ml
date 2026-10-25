# Results

Measured on Sun 25 Oct 2026 with the first trained model, `v1`: PlotNet (ResNet-34 U-Net) after 14,000 iterations at batch 8 on 40,000 matplotlib charts, about three hours on the RTX 3080 laptop GPU; and the tick reader after 8,000 iterations.

Errors are a percentage of the plot's full height (the unit of `../ACCURACY.md`): 0.1% is a tenth of a percent of full scale.
"Good coverage" is the fraction of a true curve's pixel columns where the extraction is within 1% of the truth, which counts a trace that wanders onto the wrong curve as wrong rather than as covered.

## Synthetic validation set (200 charts)

The validation charts come from the next generator version, so they include house styles v1 never trained on (Plotly-, Excel-, news-, FT-, dashboard-style, offset spines, area fills, direct labels): a test of generalisation as well as accuracy.
"Simple" is the subset with at most three series and fewer data points than pixel columns, which is what most screenshots look like; "all" adds up to six overlapping series of up to 2,500 points each.

Geometry in source pixels, with true tick values (`evaluate --refine`):

| | ML v1, simple | ML v1, all | Classical, simple | Classical, all |
| --- | --- | --- | --- | --- |
| line series found (coverage > 50%) | 88% | 78% | 14% | 12% |
| good coverage of true curves | 76% | 59% | 11% | 7% |
| median RMS of found lines | 0.20% | 0.32% | 0.38% | 0.50% |
| median error at turning points | 0.34% | 2.0% | 0.19% | 0.81% |
| markers found / precision | 82% / 79% | 52% / 70% | 5% / 4% | 5% / 5% |
| median marker error | 0.10% | 0.11% | 0.14% | 0.15% |
| tick recall / position error | 92% / 0.31 px | 91% / 0.32 px | - | - |

The classical engine's numbers are end to end (its own OCR and calibration); its RMS and peak figures describe only the few series it found.
Its main failure on these charts is not precision but finding the series at all: unusual frames, labels on the right, no axis lines, legends, overlapping series.

The "all" peak error is dominated by charts with more data points than pixel columns, where the top and bottom of a one-column spike cannot both be represented by one value per column.

## Chart.js corpus, end to end (`eval_corpus`)

`../corpus/` is the classical engine's own test set: 18 Chart.js charts, a renderer PlotNet never saw in training.
Same definition as `../ACCURACY.md` (RMS over 200 points as % of full scale), with ticks read by the learned tick reader:

| Case | ML v1 | Classical (tuned on this corpus) |
| --- | --- | --- |
| linear-single-solid | 0.028% | 0.031% |
| linear-single-nogrid | 0.201% | 0.193% |
| linear-thin-line | 0.032% | 0.044% |
| linear-thick-line | 0.031% | 0.035% |
| linear-dashed | 0.080% | 0.055% |
| linear-multi | 0.035%, 0.037%, 0.015% | 0.033%, 0.043%, 0.037% |
| dark-theme | 0.040%, 0.019% | 0.032%, 0.035% |
| log-y | 0.175% | 0.043% |
| log-y-multi | 0.174%, 0.021% | 0.047%, 0.048% |
| scatter-markers | 0.134% | 0.031% |
| scatter-halo-colours | 0.147%, 0.129%, 0.122%, 0.139% | 0.027%, 0.025%, 0.017%, 0.018% |
| jpeg-compressed | 0.035% | 0.036% |
| offset-annotation | fails (61%) | 0.032% |
| retina-2x | 0.055% | 0.196% |
| log-log | 0.563% (68% cover) | 0.074% |
| sawtooth-sharp | 0.288% | 0.258% |
| narrow-peaks | 0.246% | 0.362% |
| narrow-small | 0.104% | 0.077% |

All 25 series are found.
Before ticks were snapped to their drawn tick marks the whole column read 0.15-0.2%: the network had learned matplotlib's offset between a label and its tick, and Chart.js places labels differently. Where there is no tick mark or gridline to snap to (`nogrid`) that bias remains; training on more renderers is the fix.
`offset-annotation` prints a `x10^3` multiplier at the axis end, which the pipeline does not read yet.
Markers are not yet re-measured on the source pixels, which is the gap on the scatter cases.

## Real screenshots (`eval_real`)

The images in `../examples/real/`, with the classical project's hand-measured tick anchors:

| Image | Series found | Calibration error at the anchors |
| --- | --- | --- |
| 01 panel 1, 2, 3 (cropped dashboard panels, no axis lines) | 1, 1, 1 (correct) | x <= 0.97 px, y <= 2.2 px |
| 02 microprocessor trend (log y, 5 marker series, legend as coloured text) | 5 scatter (correct), y read as log | - |
| 03 women/men percent (Pew style, direct labels, no y axis line) | 2 lines + 2 fragments, and the printed end values taken as markers | x 3.6 px (the right-aligned "2021"), y 1.9 px |
| 04 hits per visit | 2 lines (correct) | - |
| 05 retail sales, monthly spikes | 1 (correct), spikes traced to the tips | x 0.9 px, y 1.7 px |

The printed values at line ends ("46", "36") are exactly what the v2 generator now draws as distractors.

## Tick reader

98.8% of validation tick labels read exactly (string match), from 9,880 labels.

## What limits accuracy now

1. One renderer in training. The tick bias above, and the network's habits generally, are matplotlib's. Plotly is now a second generator (`synth/plotly_render.py`); Chart.js would be a third.
2. Markers are taken from the network's peak at canvas resolution; a source-pixel re-measurement like the one for lines would help, with care for the marker-centre convention, which differs by library (matplotlib centres a triangle's bounding box, Chart.js its circumcircle).
3. Offset multipliers (`x10^3`, `1e6` at the axis end) are not read.
4. Dense data (more points than pixel columns) is represented one value per column, which cannot keep both ends of a one-column spike.
