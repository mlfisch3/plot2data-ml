# Results

Measured on Sun 25 Oct 2026.
The current model is `v2`: PlotNet (ResNet-34 U-Net) trained 14,000 iterations at batch 8 on 40,000 matplotlib charts (`v1`, about three hours on the RTX 3080 laptop GPU), then fine-tuned 8,000 iterations on those plus 12,000 charts in house styles (`v2`).
The tick reader trained 8,000 iterations on the labels of the same charts.
`v3`, which adds Plotly charts to training, is in progress.

Errors are a percentage of the plot's full height (the unit of `../ACCURACY.md`): 0.1% is a tenth of a percent of full scale.
"Good coverage" is the fraction of a true curve's pixel columns where the extraction is within 1% of the truth; a trace that wanders onto the wrong curve counts as wrong, not as covered.

## End to end on synthetic charts

Everything automatic: frame, ticks, the tick reader, calibration, series.
"Simple" means at most three series and fewer data points than pixel columns, which is what most screenshots look like; "all" adds up to six overlapping series of up to 2,500 points.

### Matplotlib validation set (200 charts, including house styles v1 never trained on)

| | v2, simple | v2, all | v1, simple | Classical, simple |
| --- | --- | --- | --- | --- |
| line series found (coverage > 50%) | 62% | 54% | 52% | 14% |
| good coverage of true curves | 54% | 41% | 44% | 11% |
| median RMS of found lines | 0.28% | 0.42% | 0.36% | 0.38% |
| median error at turning points | 0.34% | 2.0% | 0.44% | 0.19% |
| markers found / precision | 66% / 75% | 51% / 68% | 52% / 61% | 5% / 4% |
| calibration within 0.5%, x / y (all charts) | 84% / 79% | | 74% / 70% | |

v1's column was measured before this session's decoding fixes (tick-label grouping, tick snapping, marker re-measurement); most of the end-to-end gain is from those, the rest from v2.
The classical engine's RMS and peak figures describe only the few series it found.

With the true tick values supplied instead of read (`--oracle-ticks`), v1 already found 81% of simple series at 0.20% RMS: calibration from the labels is where most of the remaining end-to-end loss is.

### Plotly charts (150 held out; no Plotly chart was in v1 or v2's training)

| | v2, simple | v2, all | v1, simple | Classical, simple |
| --- | --- | --- | --- | --- |
| line series found | 79% | 72% | 59% | 13% |
| good coverage | 70% | 58% | 53% | 11% |
| median RMS | 0.22% | 0.27% | 0.24% | 0.15% |
| markers found / precision | 72% / 73% | 39% / 72% | 59% / 69% | 32% / 16% |
| calibration within 0.5%, x / y | 95% / 87% | | 83% / 83% | |

### Geometry alone (true tick values, `evaluate --refine`), matplotlib validation set

| | v2, simple | v2, all | v1, simple |
| --- | --- | --- | --- |
| line series found | 86% | 75% | 88% |
| good coverage | 75% | 58% | 76% |
| median RMS | 0.19% | 0.29% | 0.20% |
| median error at turning points | 0.33% | 1.9% | 0.34% |
| markers found / precision | 83% / 79% | 59% / 70% | 82% / 79% |
| median marker error | 0.10% | 0.12% | 0.10% |
| tick recall / position error | 95% / 0.32 px | 93% / 0.31 px | 92% / 0.31 px |

The "all" peak error is dominated by charts with more data points than pixel columns, where one value per column cannot keep both the top and the bottom of a one-column spike.

## Chart.js corpus, end to end (`eval_corpus`)

`../corpus/` is the classical engine's own test set: 18 Chart.js charts it was tuned on, and a renderer PlotNet never saw.
Same definition as `../ACCURACY.md` (RMS over 200 points, % of full scale), with ticks read by the tick reader:

| Case | v1 | v2 | Classical |
| --- | --- | --- | --- |
| linear-single-solid | 0.033% | 0.033% | 0.031% |
| linear-single-nogrid | 0.200% | 0.202% | 0.193% |
| linear-thin-line | 0.033% | 0.032% | 0.044% |
| linear-thick-line | 0.035% | 0.056% | 0.035% |
| linear-dashed | 0.081% | 0.075% | 0.055% |
| linear-multi | 0.039%, 0.041%, 0.015% | 0.042%, 0.041%, 0.015% (one split, 45% cover) | 0.033%, 0.043%, 0.037% |
| dark-theme | 0.039%, 0.018% | 0.045%, 0.017% | 0.032%, 0.035% |
| log-y | 0.170% | 0.170% | 0.043% |
| log-y-multi | 0.170%, 0.021% | 0.177%, 0.021% | 0.047%, 0.048% |
| scatter-markers | 0.060% | 0.060% | 0.031% |
| scatter-halo-colours | 0.06-0.08% | 0.08-0.10% | 0.017-0.027% |
| jpeg-compressed | 0.034% | 0.034% | 0.036% |
| offset-annotation | fails | fails | 0.032% |
| retina-2x | 0.055% | 0.104% | 0.196% |
| log-log | 0.62% (68% cover) | 0.62% (67% cover) | 0.074% |
| sawtooth-sharp | 0.303% | 0.286% | 0.258% |
| narrow-peaks | 0.278% | 0.240% | 0.362% |
| narrow-small | 0.066% | 0.066% | 0.077% |
| median over series | 0.060% | 0.075% | 0.037% |

All 25 series are found.
Before ticks were snapped to their drawn tick marks the whole column read 0.15-0.2%: the network had learned matplotlib's offset between a label and its tick, and Chart.js places its labels differently. Where there is no tick mark or gridline to snap to (`nogrid`) that bias remains; training on more renderers is the fix, and `v3` adds Plotly.
`offset-annotation` prints a `1e6` multiplier touching the top tick label; the pipeline reads multipliers that stand apart (matplotlib's), not this one yet.

## Real screenshots (`eval_real`, v2)

The images in `../examples/real/`, against the classical project's hand-measured tick anchors:

| Image | Series found | Calibration error at the anchors |
| --- | --- | --- |
| 01 panels 1, 2, 3 (dashboard crops, no axis lines) | 1, 1, 1 (correct) | x <= 1.2 px, y <= 2.7 px |
| 02 microprocessor trend (log y, 5 marker series, colour-coded text legend) | 5 marker series (correct), y read as log | - |
| 03 women/men percent (news style, direct labels, no y axis line) | the 2 lines, plus 2 short fragments and the printed end values taken as markers | x 0.96 px, y 2.2 px |
| 04 hits per visit | 2 lines (correct) | - |
| 05 retail sales, monthly spikes | 1 (correct), spikes traced to their tips | x 0.96 px, y 2.1 px |

## Tick reader

98.8% of 9,880 validation tick labels read exactly (string match).

## What limits accuracy now

1. Training has seen matplotlib only (v1, v2). The held-out Plotly numbers above show how much a renderer the model has never seen costs; `v3` trains on Plotly too, and Chart.js would be a third.
2. Calibration from the labels: one axis in six still misses 0.5%, from misread or misgrouped labels, axes with only two labels, and multipliers that touch a label.
3. Dense data (more points than pixel columns) is represented one value per column.
4. Asymmetric markers (triangles) keep the network's estimate, since libraries disagree on where their data point is.
