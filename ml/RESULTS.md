# Results

Measured on Sun 25 Oct 2026 (v1, v2, classical) and Wed 28 Oct 2026 (v3).
The current model is `v3`: PlotNet (ResNet-34 U-Net) trained 14,000 iterations at batch 8 on 40,000 matplotlib charts (`v1`, about three hours on the RTX 3080 laptop GPU), fine-tuned 8,000 iterations on those plus 12,000 charts in house styles (`v2`), then fine-tuned 16,000 iterations on all of that plus 12,000 Plotly charts (`v3`).
The tick reader trained 8,000 iterations on the labels of the matplotlib charts.

Errors are a percentage of the plot's full height (the unit of `../ACCURACY.md`): 0.1% is a tenth of a percent of full scale.
"Good coverage" is the fraction of a true curve's pixel columns where the extraction is within 1% of the truth; a trace that wanders onto the wrong curve counts as wrong, not as covered.

## End to end on synthetic charts

Everything automatic: frame, ticks, the tick reader, calibration, series.
"Simple" means at most three series and fewer data points than pixel columns, which is what most screenshots look like; "all" adds up to six overlapping series of up to 2,500 points.

### Matplotlib validation set (200 charts, including house styles v1 never trained on)

| | v3, simple | v3, all | v2, simple | v2, all | v1, simple | Classical, simple |
| --- | --- | --- | --- | --- | --- | --- |
| line series found (coverage > 50%) | 62% | 55% | 62% | 54% | 52% | 14% |
| good coverage of true curves | 51% | 41% | 54% | 41% | 44% | 11% |
| median RMS of found lines | 0.31% | 0.44% | 0.28% | 0.42% | 0.36% | 0.38% |
| median error at turning points | 0.39% | 2.3% | 0.34% | 2.0% | 0.44% | 0.19% |
| markers found / precision | 64% / 74% | 48% / 64% | 66% / 75% | 51% / 68% | 52% / 61% | 5% / 4% |
| calibration within 0.5%, x / y (all charts) | 85% / 78% | | 84% / 79% | | 74% / 70% | |

v3 and v2 are within noise of each other on matplotlib charts; the Plotly training of v3 bought nothing here.
v1's column was measured before the decoding fixes of 25 Oct (tick-label grouping, tick snapping, marker re-measurement); most of the end-to-end gain from v1 is from those.
The classical engine's RMS and peak figures describe only the few series it found.

With the true tick values supplied instead of read (`--oracle-ticks`), v1 already found 81% of simple series at 0.20% RMS: calibration from the labels is where most of the remaining end-to-end loss is.

### Plotly charts (150 held out; v3 trained on other Plotly charts, v1 and v2 on none)

| | v3, simple | v3, all | v2, simple | v2, all | v1, simple | Classical, simple |
| --- | --- | --- | --- | --- | --- | --- |
| line series found | 78% | 75% | 79% | 72% | 59% | 13% |
| good coverage | 70% | 61% | 70% | 58% | 53% | 11% |
| median RMS | 0.18% | 0.25% | 0.22% | 0.27% | 0.24% | 0.15% |
| markers found / precision | 76% / 78% | 42% / 77% | 72% / 73% | 39% / 72% | 59% / 69% | 32% / 16% |
| calibration within 0.5%, x / y | 95% / 86% | | 95% / 87% | | 83% / 83% | |
| tick recall, x / y | 92% / 92% | 93% / 93% | 84% / 88% | 88% / 90% | | |
| frame corner error, median / p90 | 0.7 / 3.7 px | 0.6 / 3.2 px | 1.1 / 9.1 px | 1.0 / 9.0 px | | |

Training on Plotly made the geometry of Plotly charts markedly better (ticks, frame, RMS); the end-to-end counts moved little because they are limited by label reading and series separation, not by the renderer.

### Geometry alone (true tick values, `evaluate --refine`), matplotlib validation set

| | v3, simple | v3, all | v2, simple | v2, all | v1, simple |
| --- | --- | --- | --- | --- | --- |
| line series found | 89% | 76% | 86% | 75% | 88% |
| good coverage | 76% | 59% | 75% | 58% | 76% |
| median RMS | 0.19% | 0.31% | 0.19% | 0.29% | 0.20% |
| median error at turning points | 0.31% | 1.8% | 0.33% | 1.9% | 0.34% |
| markers found / precision | 84% / 83% | 59% / 70% | 83% / 79% | 59% / 70% | 82% / 79% |
| median marker error | 0.11% | 0.13% | 0.10% | 0.12% | 0.10% |
| tick recall / position error | 95% / 0.30 px | 95% / 0.31 px | 95% / 0.32 px | 93% / 0.31 px | 92% / 0.31 px |

The "all" peak error is dominated by charts with more data points than pixel columns, where one value per column cannot keep both the top and the bottom of a one-column spike.

## Chart.js corpus, end to end (`eval_corpus`)

`../corpus/` is the classical engine's own test set: 18 Chart.js charts it was tuned on, and a renderer PlotNet never saw.
Same definition as `../ACCURACY.md` (RMS over 200 points, % of full scale), with ticks read by the tick reader:

| Case | v3 | v2 | v1 | Classical |
| --- | --- | --- | --- | --- |
| linear-single-solid | 0.033% | 0.033% | 0.033% | 0.031% |
| linear-single-nogrid | 0.194% | 0.202% | 0.200% | 0.193% |
| linear-thin-line | 0.031% | 0.032% | 0.033% | 0.044% |
| linear-thick-line | 0.042% | 0.056% | 0.035% | 0.035% |
| linear-dashed | 0.067% | 0.075% | 0.081% | 0.055% |
| linear-multi | 0.037%, 0.046%, 0.017% | 0.042%, 0.041%, 0.015% (one split, 45% cover) | 0.039%, 0.041%, 0.015% | 0.033%, 0.043%, 0.037% |
| dark-theme | 0.047%, 0.017% | 0.045%, 0.017% | 0.039%, 0.018% | 0.032%, 0.035% |
| log-y | 0.170% (plus 3 spurious series) | 0.170% | 0.170% | 0.043% |
| log-y-multi | 0.177%, 0.021% (plus 3 spurious) | 0.177%, 0.021% | 0.170%, 0.021% | 0.047%, 0.048% |
| scatter-markers | 0.060% | 0.060% | 0.060% | 0.031% |
| scatter-halo-colours | 0.07-0.10% | 0.08-0.10% | 0.06-0.08% | 0.017-0.027% |
| jpeg-compressed | 0.034% | 0.034% | 0.034% | 0.036% |
| offset-annotation | 61% (multiplier not read) | fails | fails | 0.032% |
| retina-2x | 0.109% | 0.104% | 0.055% | 0.196% |
| log-log | 1.33% (68% cover) | 0.62% (67% cover) | 0.62% (68% cover) | 0.074% |
| sawtooth-sharp | 0.268% | 0.286% | 0.303% | 0.258% |
| narrow-peaks | 0.211% | 0.240% | 0.278% | 0.362% |
| narrow-small | 0.066% | 0.066% | 0.066% | 0.077% |
| median over series | 0.067% | 0.075% | 0.060% | 0.037% |

All 25 series are found by every version.
Before ticks were snapped to their drawn tick marks the whole column read 0.15-0.2%: the network had learned matplotlib's offset between a label and its tick, and Chart.js places its labels differently. Where there is no tick mark or gridline to snap to (`nogrid`) that bias remains.
`offset-annotation` prints a `1e6` multiplier touching the top tick label; the pipeline reads multipliers that stand apart (matplotlib's), not this one, so v3 finds the series and scales it wrongly.
v3 returns spurious extra series on the two `log-y` cases (text scraps taken as lines) and loses more of `log-log` than v2: the two regressions of v3.

## Real screenshots (`eval_real`)

The images in `../examples/real/`, against the classical project's hand-measured tick anchors:

| Image | Series found, v3 (v2) | Calibration error at the anchors, v3 |
| --- | --- | --- |
| 01 panels 1, 2, 3 (dashboard crops, no axis lines) | 1, 1, 1 (correct) | x <= 1.1 px, y <= 4.0 px (v2: y <= 2.7 px) |
| 02 microprocessor trend (log y, 5 marker series, colour-coded text legend) | 5 marker series (correct), y read as log | - |
| 03 women/men percent (news style, direct labels, no y axis line) | the 2 lines, plus 2 short fragments and the printed end values taken as markers; v3 reads the x axis as log (wrong), v2 as linear | x 2.0 px, y 2.2 px |
| 04 hits per visit | 2 lines (correct) | - |
| 05 retail sales, monthly spikes | 1 (correct), spikes traced to their tips | x 0.96 px, y 2.1 px |

## Tick reader

98.8% of 9,880 validation tick labels read exactly (string match).

## What limits accuracy now

1. Calibration from the labels: one axis in five or six misses 0.5%, from misread or misgrouped labels (`10^3` read as `0^3`), axes with only two labels, multipliers that touch a label, and the linear/log decision.
2. Series separation and tracing: even with true ticks, 11% of simple and 24% of all line series are not found, and a quarter of the columns of the found ones are off by more than 1%.
3. Precision: tick positions are good to 0.3 px, which caps the corpus at about 0.03-0.07%; the classical engine's hand-tuned sub-pixel measurement is still better on its own corpus.
4. Markers: a third missing and a quarter spurious on simple charts end to end; printed numbers taken as markers.
5. Renderers never seen (Chart.js, and everything else): the `nogrid` bias, `retina-2x`, `log-log`.
6. Dense data (more points than pixel columns) is represented one value per column.

An improvement contest on exactly these five fronts is running on branches `team/t1-axis` to `team/t5-robust`; see `teams/BRIEF.md`.
