# t3-precision: the failure catalogue

Curator's record of where the sub-pixel error comes from, measured on the v3 checkpoint (`runs/v3/best.pt`).
All pixel errors are in source pixels unless marked; "% ph" is a percentage of the plot height, the scoreboard's unit.
Every number here is reproducible from the scripts in `scripts/` and the probe sets under `data/t3-*` (generator `p2d/synth/probe_t3.py`).

How the records were made:

```sh
python teams/t3-precision/scripts/diag.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --out out/t3/diag-base.pkl
python teams/t3-precision/scripts/diag_report.py out/t3/diag-base.pkl [--simple]       # per-column, per-peak, per-tick, per-frame tables
python teams/t3-precision/scripts/probe_report.py out/t3/diag-peaks.pkl                # per-factor tables for a probe set
python teams/t3-precision/scripts/corpus_diag.py --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt   # corpus: calibration versus trace
```

(Sections are filled in as the measurements land; see the dated entries in NOTES.md.)

Provenance: every "baseline" number below was measured with the contest-start code (commit 6b313e9).
The mpl-val and plotly-v1 collections ran from this worktree before any file under `p2d/` had been edited (pickles written 01:54 and 02:0x, the first live edit to `p2d/extract.py` was at 01:55:44 and the Plotly process had imported the module at 01:54:18); every later baseline run imports `p2d` from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` (`P2D_ROOT=... scripts/diag.py`).

## 0. The scoreboard baseline, reproduced here

`python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine` (this worktree, before any edit; `out/t3/base-refine.txt`): simple / all: line_rms_median 0.189 / 0.311 %, peak_err_median 0.307 / 1.77 %, xticks 0.30 / 0.29 px, yticks 0.35 / 0.32 px, frame median 1.39 / 1.47 px, p90 13.8 / 13.2 px.
Identical to the judge's `out/base/v3-pixel.txt`.

## 1. Lines: a few pixels on a tenth of the columns, not a fraction of a pixel everywhere

Source: `out/t3/report-base-simple.txt`, `out/t3/report-base-all.txt` (200 mpl-val charts; simple = 115 charts, 132 matched line series, 105,366 scored columns).

| columns (simple) | share of columns | share of squared error | bias (px) | median abs error (px) | kept from the network |
| --- | --- | --- | --- | --- | --- |
| all | 100% | 100% | +0.001 | 0.090 | 43.5% |
| within 3 px of the truth | 89.3% | 1.3% | -0.003 | 0.068 | |
| flat (abs slope < 0.5, > 3 columns from a vertex), within 3 px | 32% | 0.0% | +0.00 | 0.045 (0.023 where refined, 0.229 where kept from the net) | 28% |
| abs slope > 4 | 18% | 62.8% | -0.28 | 1.69 (p90 14.2) | 81% |
| abs slope 2 to 4 | 14% | 6.9% | +0.03 | 0.15 (p90 2.8) | 44% |
| within 1 column of a polyline vertex | 9% | 32.8% | -0.06 | 1.61 (p90 12.6) | 82% |
| 1 to 3 columns from a vertex | 12% | 20.4% | -0.05 | 0.86 (p90 9.3) | 82% |
| 3 to 8 columns from a vertex | 15% | 12.1% | -0.09 | 0.21 | 58% |
| more than 8 columns from a vertex | 48% | 7.4% | -0.06 | 0.05 | 28% |

Flat columns carry no bias by line width (0.5 to 6 px: +0.02 to -0.07 px), none by canvas scale (0.4 to 2.0: median 0.016 to 0.061 px), none by ink colour. Columns 1.5 to 3 px from a gridline are the one flat exception: median 0.18 px, 83% kept from the net.
A falling slope reads -0.05 px, a rising one +0.03 px (near-correct columns with abs slope > 0.5): a negligible lag.

Where `refine_lines` keeps the network's estimate (43.5% of columns on simple charts, 47% on all), and why (from the crops in `out/t3/cases/`, green truth, blue raw network, magenta refined):

- Low-contrast ink, `dd < 400`: the whole series is left to the network. `9000148` series 0, a 5 px teal line on lavender paper: flat columns wander by 1.5 px (RMS 0.157%, 100% kept).
- The ink run reaches the window edge (R = max(3, 2.5/s) + 4 rows): every steep flank, every thick line at small scale. `9000041` series 2 (highcharts, s = 0.39, slope 6.6): a 2 px offset along the whole flank, 67% kept.
- Dashes and gaps: no ink under the column, the network's centre line through the gap is 2 px off. `9000196` series 1 (plotly, dashed, s = 0.42): median 2.3 px over the worst 60 columns; `9000192` series 0 (5.8 px dashed line, spike): 1.0 px median, 98% kept.
- Vertex heat above 0.3 in the 3x3 canvas neighbourhood: up to 4 source px around every vertex at s = 0.4.

Oracle ceilings (`scripts/oracle.py out/t3/diag-base.pkl`), median per-series RMS in % ph, simple / all:

| if these columns were exact | simple | all |
| --- | --- | --- |
| nothing (as measured) | 0.189 | 0.311 |
| within 1 column of a vertex | 0.162 | 0.258 |
| within 3 columns of a vertex | 0.117 | 0.201 |
| within 8 columns of a vertex | 0.066 | 0.101 |
| abs slope > 4 | 0.096 | 0.181 |
| abs slope > 2 | 0.061 | 0.130 |
| the columns kept from the network | 0.039 | 0.072 |
| the gross columns (error > max(3, 2 lw) px) | 0.109 | 0.148 |
| every column with error > 1 px | 0.036 | 0.039 |

Worst series: the 23 worst simple series by RMS are all tracing failures (gross columns hold over 90% of their squared error); over all 132 matched simple series 49 are tracing-dominated and 83 precision-dominated, the latter with median RMS 0.081%.
The scoreboard median therefore sits on series whose RMS is made by a handful of gross columns at vertices, on flanks and in gaps, not by a sub-pixel bias.

## 2. Peaks: clipped by the network's own vertex estimate, which refinement never touches

916 scored turning points on simple charts (prominence at least 5% ph); "+" is inward (clipped).

| | median inward (px) | median abs (% ph) | clipped by > 1 px |
| --- | --- | --- | --- |
| all peaks, refined | +1.26 | 0.307 | 53% |
| all peaks, raw network | +1.25 | 0.307 | 53% |
| turning angle < 60 deg (blunt) | +0.05 to +0.12 | 0.07 to 0.16 | 9 to 18% |
| 90 to 120 deg | +2.14 | 0.47 | 58% |
| > 150 deg (needles) | +2.30 | 0.36 | 66% |
| canvas scale 1.0 (native) | -0.09 | 0.23 | 15% |
| scale 0.7 to 1 | +0.65 | 0.25 | 42% |
| scale 0.5 to 0.7 | +2.49 | 0.40 | 63% |
| scale < 0.5 | +2.54 | 0.42 | 68% |
| line width > 4 px | +3.58 | 0.59 | 63% |
| line width < 1.2 px | +0.53 | 0.09 | 35% |
| a vertex-head peak within 1 px of the tip (471 peaks) | +0.74 | 0.18 | 45% |
| nearest vertex peak 1 to 2 px | +2.34 | 0.43 | 60% |
| no vertex peak within 4 px (133) | +4.03 | 1.09 | 64% |

So: at native resolution the tips are right; the clipping is resolution loss on the 768 x 512 canvas (sigma 1.5 canvas px on the vertex heat is 3 to 4 source px at s = 0.4 to 0.5), and the vertex head's parabola estimate is short by 0.74 px even when it fires on the tip.
Overshoot by more than 1 px: 7% of peaks.
"All" split: median +3.7 px (1.77% ph), 64% clipped by > 1 px; 3,886 of 5,605 peaks are one-sample spikes of dense series (turning angle > 150 deg, median +8.4 px): the trace runs through the base of the spike. Probed by `data/t3-spikes`.

## 3. Ticks: the network is unbiased at 0.27 px; snapping to drawn marks adds +0.25 px; half the variance is a per-axis shift

1,970 labelled ticks on 200 charts.

| | x raw | x snapped (`refine_ticks`) | y raw | y snapped |
| --- | --- | --- | --- | --- |
| bias (px) | -0.02 | +0.21 | +0.10 | +0.28 |
| median abs (px) | 0.27 | 0.34 | 0.30 | 0.37 |
| p90 (px) | 0.76 | 0.86 | 0.78 | 0.89 |
| on the ticks that were snapped (73 to 76%) | 0.25 | 0.35 | 0.29 | 0.37 |

Why snapping is biased: matplotlib pixel-snaps tick marks and gridlines, the truth (and the data line) are not snapped. Snap error by the sub-pixel phase of the true position, x and y alike: fraction in [0, 0.25): +0.63 px (median abs 0.80); [0.25, 0.5): +0.46; [-0.25, 0): -0.02; [-0.5, -0.25): +0.22.
The raw network error carries a weaker version (+0.21 / -0.23 in the two central bins): it learned from the drawn marks.
Per axis: the mean error of one axis's ticks has a standard deviation of 0.34 px (x) / 0.46 px (y) across axes against a within-axis residual of 0.29 / 0.28 px, so half of the variance is a common shift per axis that least squares over the ticks cannot average away.
By what is drawn at the tick (raw): mark and grid 0.25 to 0.26 px; mark without grid 0.27 to 0.32; grid only 0.31 to 0.42; label only (no mark, no grid; n = 57 x, 47 y): bias +0.22 / +0.52 px, median 0.38 / 0.39, p90 0.85 / 1.25: the `nogrid` corpus case in miniature.
Scale: 0.21 px at s = 0.7 to 1, 0.36 to 0.38 at s < 0.5.

## 4. Frame: visible edges are fine; the hidden top edge is the whole p90

200/200 found in geometry mode (the end-to-end "frame_found 0.89" is `evaluate.py` replacing the extraction with an empty one when calibration fails, not the detector).

| edge | visible spine: n, bias, median abs, p90 (px) | hidden: n, bias, median abs, p90 |
| --- | --- | --- | --- |
| left | 78, +0.22, 0.37, 1.05 | 122, -0.46, 0.61, 3.26 |
| top | 49, +0.02, 0.37, 1.09 | 151, +5.23, 1.22, 13.21 |
| right | 49, -0.00, 0.37, 0.89 | 151, +0.01, 0.56, 2.39 |
| bottom | 141, -0.24, 0.42, 1.13 | 59, +1.63, 0.60, 6.87 |

All four spines visible (43 charts): max-corner error median 0.75 px, p90 1.75. Some hidden (157): median 2.11, p90 15.0.
The worst are spineless house styles where the corner heat lands on the first gridline below the true top: 9000023 highcharts +211 px, 9000049 +97, 9000133 excel +74, 9000036 news +67 (all with the top edge invisible).
A low top edge also truncates the series ROI (`extract` keeps ink within the frame plus 3 px).

Confirmed without the network (label maps and grey levels of mpl-val, 200 charts; tick-mark ink is the AXIS class in the band just outside the axis, gridline ink the GRID class across the plot):

| drawn ink, centroid minus true position | n | bias (px) | median abs | frac [-0.5,-0.25) | [-0.25,0) | [0,0.25) | [0.25,0.5) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| x tick marks (label map) | 722 | +0.23 | 0.32 | +0.13 | -0.12 | +0.59 | +0.37 |
| x tick marks (grey levels) | 662 | +0.29 | 0.35 | +0.19 | -0.05 | +0.63 | +0.44 |
| x gridlines | 380 | +0.28 | 0.32 | +0.21 | -0.02 | +0.63 | +0.37 |
| y tick marks (label map) | 620 | +0.30 | 0.33 | +0.19 | -0.06 | +0.69 | +0.39 |
| y gridlines | 569 | +0.31 | 0.37 | +0.24 | -0.06 | +0.64 | +0.43 |

So the ink of a matplotlib tick mark or gridline is pixel-snapped to a position +0.3 px (mean) from the true tick, by an amount that depends on the sub-pixel phase of the truth and reaches +0.7 px; `refine_ticks` measures that ink correctly (its +0.21 / +0.28 bias is the ink's) and the network's raw estimate, unbiased at 0.27 px median, is already at the floor set by this quantisation (a uniform error of width 1 px has median 0.25).
Consequence: on matplotlib the tick floor cannot be lowered by measuring marks or gridlines more carefully; it can only be lowered by a renderer-specific offset (here -0.3 px) or by fitting the data line's own registration.
What this does to a 400 px plot: 0.3 px is 0.075% of full scale, the size of the best corpus numbers; the corpus decomposition (section 6) says how much of each corpus error is this calibration offset.
