# t4-markers: the failure catalogue

Curator's file. Every number here is v3 (`runs/v3/best.pt`), geometry only with `--refine`, unless marked otherwise.
"Before" numbers come from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` (commit 6b313e9); the first baseline (`out/t4/rows-val.json`, `out/t4/rows-plotly.json`, `out/t4/diag-val/`, `out/t4/diag-plotly/`) was measured in this worktree before any edit to `p2d/` and is identical to `out/base/v3-pixel.txt`.
Paths are relative to `ml/` in this worktree.

## Tools

- `teams/t4-markers/tools/marker_diag.py`: per-marker diagnosis. For every true marker the stage at which it was lost (`no_heat`, `no_peak`, `peak_off`, `unlabelled`, `dropped`, `moved`, `taken`), for every returned marker the ink under it (`dup`, `line_ink`, `marker_ink`, `text`, `legend`, `grid`, `axis`, `bg`), the purity and fragmentation of the series grouping, the error against the recorded centre and against the drawn centre, and a matching whose cost is capped at the tolerance (`recall_capped`). Writes `summary.json`, `rows.json`, overlays of the worst charts (`<id>.png`: green circle = found, red circle = missed, blue cross = correct, magenta cross = spurious; `<id>-heat.png`: the raw marker heat on the source image) and contact sheets per cause (`sheet-FN-<stage>.png`, `sheet-FP-<cause>.png`; each tile: source crop left, marker heat right, the point at the magenta cross). `P2D_ROOT=<tree>/ml` selects which `p2d` is diagnosed.
- `teams/t4-markers/tools/probe_report.py`: slices a diagnosis `rows.json` by the probe parameters recorded in each chart (`meta["probe"]`).
- `teams/t4-markers/tools/bias_check.py`: on images without pixel truth (Chart.js, real screenshots), the returned centre against the ink centroid of the blob under it, raw and refined.
- `p2d/synth/probe_t4.py`: the probe generator (see "Probe sets").

## The standard sets: the numbers and who owns them

Geometry only, `--refine`, v3:

| set | markers (gt / returned / hit) | recall all / simple | precision all / simple | median error |
| --- | --- | --- | --- | --- |
| mpl-val 200 | 15,748 / 13,251 / 9,333 | 0.593 / 0.845 | 0.704 / 0.825 | 0.128% / 0.112% |
| plotly-v1 first 150 | 16,517 / 9,627 / 7,681 | 0.465 / 0.829 | 0.798 / 0.819 | 0.091% / 0.081% |

The "all" column is owned by a handful of charts whose line+markers series draw a marker at every one of 800 to 6,000 points, at 0.2 to 0.7 px spacing, so the markers fuse into a thick line.
mpl-val: the five worst charts hold 64% of the 6,415 misses (9000180: 1,574 markers, 1,310 missed; 9000146: 1,516 / 932; 9000026: 868 / 835; 9000142: 1,006 / 529; 9000188: 752 / 498).
Plotly: one chart (500107: 6,081 markers on five line+markers series, 2.5 points per pixel column) holds 58% of the 8,836 misses, the top five 85%.
These come from `mpl_render` / `plotly_render` drawing line+markers in "mixed" charts without the 80-point cap that "line" charts have.
No detector can return those one by one; what can be won there is not returning hundreds of split peaks (9000146 returned 963 markers for 584 hits).
The "simple" split is the one that describes screenshots: 5,415 true markers on mpl-val, 840 missed (15.5%), 973 spurious.

## Failure kinds

### F1. Overlapping and touching markers (76% of the misses, 54% of the spurious)

Diagnosis (`out/t4/diag-val/summary.json`): of 6,415 misses, 2,031 are `taken` (a returned marker within tolerance, but the one-to-one matching gave it to a neighbour: one peak for two markers), 2,176 `peak_off` (heat present, nearest raw peak 3 to 6 px away: merged by the 2 px NMS on a 1.5 px sigma target), 612 `no_peak` (a plateau along a rope of markers).
Recall by nearest-neighbour distance in source px: < 3 px 18%, 3-5 px 38%, 5-8 px 51%, 8-12 px 70%, 12-20 px 83%, > 20 px 89%.
By spacing in marker diameters: < 0.5 21%, 0.5-1 57%, 1-1.5 74%, 1.5-2 84%, > 2 88%.
4,931 of mpl-val's 15,748 markers sit closer than half a diameter to another one.
The spurious side of the same failure: 2,130 `dup` returns within 6 px of an already matched marker (split peaks on ropes and on big markers).
Examples: 9000180, 9000146, 9000026 (ropes: `out/t4/diag-val/9000180.png`, `9000180-heat.png`), 9000142 (six scatter series in overlapping clouds, 529 of 1,006 missed: `out/t4/diag-val/9000142.png`), 9000188 (752 markers, 498 missed, 532 spurious). Sheets: `out/t4/diag-val/sheet-FN-peak_off.png`, `sheet-FN-taken.png`, `sheet-FP-dup.png`.
Real: `out/base/real-v3/02-microprocessor-log-scatter.png`, the row of grey diamonds along 10^0 and the dense triangles above 10^4.
Probe sets: `data/t4-dense` (clouds at a set spacing), `data/t4-row` (rows along a curve at a set spacing), `data/t4-multi` (several series in one cloud).

### F2. Dashes and spikes of lines returned as markers (36% of the spurious)

1,406 spurious markers sit on the ink of a line series that has no markers: the dashes of a thick dashed line near an apex (each dash is a blob the size of a marker: `out/t4/diag-val/sheet-FP-line_ink.png`), the spikes of a noisy dense line.
Charts with no true marker at all that returned many: 9000079 (361 returned, density 1.26 points per column), 9000032 (23, a thick "--" line: `out/t4/viz-val/9000032.png`); with few true markers: 9000160 (86 true, 338 returned), 9000138 (19 true, 202 returned).
The five worst FP charts hold 46% of all spurious markers.
Probe set: `data/t4-lines` (noisy, spiky, dashed, thick dashed and step lines, no marker anywhere; every return is spurious).

### F3. Large markers: diffuse heat, split peaks, missed centres

Recall by marker size (px): < 4 px 81%, 4-6 54%, 6-8 42%, 8-12 80%, 12-20 56%, > 20 px 33%.
The dips at 4-8 px are the ropes (small markers packed along a line); the fall above 12 px is real: a big filled marker gets a diffuse blob of heat with several peaks (`sheet-FP-dup.png`, bottom rows) or none above threshold.
Probe set: `data/t4-shapes` (every shape at one size per chart, 2 to 20 px, filled or hollow, markers far apart).

### F4. Decoding drops: embedding label -1, singleton clusters

313 misses (5%) had a raw peak within tolerance whose embedding label was -1 (`extract.extract` keeps only peaks within radius 1.5 of a cluster centre); 43 more were in a cluster of one marker (`len(mk) >= 2` rule) or lost on the way.
Typical: a marker of a line+markers series sitting on its line at a vertex, whose embedding differs from the line's cluster centre (`sheet-FN-unlabelled.png`, rows 4-8); markers inside a dense mixed cloud.
These are free recall: no training needed.

### F5. No heat on separated markers

For well separated markers (nearest neighbour >= 12 px, 6,501 markers) recall is 86.6%; the lead loss there is `no_heat` (412): markers under or against a thick line or a filled area of another series, pale translucent markers (`alpha`), big markers (F3), hollow markers on a tinted background (9000000, the pale green "Price" circles: `out/t4/viz-val/9000000.png`).
Sheet: `out/t4/diag-val/sheet-FN-no_heat.png`.
Probe set: `data/t4-hollow` (modes hollow, halo, alpha, small, ongrid, online).

### F6. Glyphs, digits and legend symbols returned as markers

On mpl-val this is under 2% of the spurious markers (text 9, legend symbols 31, bg 48 of which several are digits next to the point: `sheet-FP-bg.png` top-left "0.841", "Fit"), because mpl-val prints values on 4% of charts.
On the real women/men chart (`out/base/real-v3/03-women-men-percent.png`) the printed end values "46", "36", "22" and the glyphs of "Women"/"Men" come back as two scatter series; a chart with data labels at every point will do this at every point.
Probe set: `data/t4-labels` (a value printed at every marker, numbers printed near the points, end labels with values, annotations with arrows, an in-plot legend with marker symbols).

### F7. Series grouping: splits more than mixes

233 returned marker series on mpl-val; 37 impure (mean purity 0.98); 79 of 153 matched true marker series were split over more than one returned series.
`merge_by_colour` joins clusters of one colour; it cannot join a series the embedding split when the colour was also blended (translucent markers, markers over other ink), and it joins different series of close colours.
Probe set: `data/t4-multi` (modes close_colours, same_colour_shapes, sizes, mixed).

### F8. Centre precision, and what the ground truth actually marks

Matplotlib's Agg backend stamps every marker at an integer pixel position whatever `set_snap(False)` says (lines are not snapped: their `path_px` is exact).
Measured on 15,000 isolated markers of every symmetric shape (ink centroid of the instance mask against `markers_px`): the drawn centre is `floor(markers_px + 1.0)` in each axis, to 0.01-0.07 px.
Plotly (kaleido) places markers sub-pixel; its recorded centres match the ink to 0.05 px with no bias.
So on every matplotlib chart in `mpl-v1`, `mpl-v2` and `mpl-val` the recorded marker centre is off the drawn ink by u ~ U(0, 1) px per axis: a +0.5 px bias and a +/- 0.5 px jitter.
Consequences:
- the marker heat target is smeared and biased on 52k of the 64k training charts;
- `marker_err_median_pct` on mpl-val (0.11-0.13%, about 0.5 px) is mostly the truth's own jitter; `refine_markers`, which moves a symmetric marker to its ink centroid (right on every renderer), cannot show its gain on this set, since against the recorded centre the ink centroid is 0.5 px off by construction;
- on a renderer that does not snap (Chart.js, Plotly), a learned half-pixel bias is 0.09% of a 560 px plot; the Chart.js scatter cases read 0.06-0.10% against the classical engine's 0.02-0.03% (`out/base/v3-corpus.txt`). Measured on the source pixels (CPU, no network): the ink-blob centroids of `scatter-halo-colours` reproduce the published values to 0.07-0.09 px RMS in y (0.015-0.020% of the 475 px plot) after a least-squares axis fit, and `scatter-markers` to 0.07 px (0.013%); the centroids' fractional parts are uniform (Chart.js does not snap). So on these charts 0.02% is the floor of an exact centroid, and the 0.06-0.10% the pipeline reports is its own centre error and calibration, not the image. `bias_check.py` apportions it between the raw peak and the refined centre (queued).
`probe_t4` keeps `markers_px` as the exact value position (the convention of every other set and of the scoreboard) and records the drawn centre beside it as `markers_drawn_px`; `marker_diag` reports the error against both, and the per-axis bias of the returned centre against the drawn one.
Error by shape on mpl-val (median, matched markers, against the recorded centre): s 0.086%, d 0.089%, + 0.099%, X 0.081%, o 0.197%, D 0.157%, * 0.223%, ^ 0.356%, < 0.182%: the asymmetric shapes, where the network's estimate stands, are twice to three times worse than the symmetric ones that `refine_markers` re-measures.

### F9. Notes on the metric (not changed; reported beside it)

- `metrics.score` matches by the Hungarian method on raw distances: two returns near one true marker plus an unserved neighbour trade one hit for two misses (217 `taken` misses on mpl-val at nn >= 12 px). A cost capped at the tolerance maximises the number of hits instead; `marker_diag` reports `recall_capped` / `precision_capped`.
- The "all" marker numbers are dominated by charts no extractor can resolve (above); "simple" is the number to watch, and the per-chart distribution matters more than either.

## Probe sets

All generated by `p2d/synth/probe_t4.py` at seeds 14,000,000+, in the standard dataset format, with the provoking parameter and the measured spacing recorded in `meta["probe"]`.
Regenerated after the first baseline with `markers_drawn_px` recorded beside `markers_px` (same images, same seeds); the standard numbers do not change.

| set | charts | what is controlled | seeds |
| --- | --- | --- | --- |
| t4-dense | 150 | scatter clouds, median nearest-neighbour spacing 0.6 to 4 marker diameters, 1-4 series, shapes, sizes 3-9 pt | 14,000,000 |
| t4-row | 146 | markers along a curve at 0.7 to 5 diameters, with (60%) or without the line, 1-3 series | 14,001,000 |
| t4-shapes | 150 | every shape, one size per chart (2 to 20 px), filled or hollow, markers >= 4 diameters apart | 14,002,000 |
| t4-hollow | 120 | hollow, halo (paper-coloured edge), translucent, small (1.5-3 pt), on gridlines, on thick lines | 14,003,000 |
| t4-labels | 150 | value printed at every marker / numbers near points / end labels with values / annotations / in-plot legend | 14,004,000 |
| t4-multi | 120 | 2-5 series in one cloud: close colours, one colour with different shapes, sizes, mixed | 14,005,000 |
| t4-lines | 100 | noisy, spiky, dashed, thick dashed, step lines; no marker anywhere | 14,006,000 |

Baseline numbers: pending (queued from the frozen tree: `out/t4/eval-<set>-v3.txt`, `out/t4/diag-<set>-v3/`).
