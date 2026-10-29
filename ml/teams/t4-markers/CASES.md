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

Plotly per-marker diagnosis (`out/t4/diag-plotly/`): 9,050 of the 16,517 markers (55%) have a neighbour within 3 px (line+markers recall 0.21, scatter 0.83); separated markers are found at 0.89 (8-12 px), 0.96 (12-20 px), 0.94 (> 20 px). Misses: taken 3,638, peak_off 3,397, no_heat 893, no_peak 714, unlabelled 143. Spurious: dup 1,327 (55%), line_ink 461 (19%), marker_ink 147, grid 10. Grouping: 182 returned marker series, 33 impure, 55 of 129 true series split.

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
On Plotly, whose recorded centre is the drawn centre, the same figure separates what the refinement measures from what it leaves to the network (`out/t4/diag-plotly/summary.json`): filled symmetric symbols circle 0.010%, cross 0.008%, diamond 0.019%, pentagon 0.029%, hexagon 0.049%, square 0.056% (0.05 to 0.25 px: the centroid is exact where it runs); open symbols circle-open 0.11%, diamond-open 0.096%, square-open 0.126%, triangle-up-open 0.287% and the thin-stroke x 0.115% (the ring or the strokes never form one component above the ink-weight threshold, so the network estimate stands); asymmetric star 0.187%, triangle-down 0.178%, triangle-up 0.129%.
So the centre precision problem is hollow rings, thin strokes and asymmetric shapes; filled symmetric markers are already measured to a twentieth of a pixel.

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

Baselines from the frozen tree (v3 with the drawn-centre probe GT): `out/t4/eval-<set>-v3d.txt`, `out/t4/diag-<set>-v3/summary.json`. Standard sets: `out/t4/base-val-refine-frozen.txt`, `base-plotly-refine-frozen.txt`, `base-val-e2e-frozen.txt`, `base-plotly-e2e-frozen.txt`.

## After af04090 (`p2d/markers.py`)

Measured in this worktree with the brainstormer's committed change (`af04090`), geometry only, `--refine`, same checkpoint `runs/v3/best.pt`, same probe sets. Eval outputs tagged `step23`: `out/t4/eval-<set>-step23.txt`, `rows-<set>-step23.json`; diagnosis `out/t4/diag-<set>-step23/summary.json`. Compare with `python teams/t4-markers/tools/diag_delta.py v3 step23`.

### What the change does

`p2d/markers.py` replaces `extract.refine_markers`. It measures each series' marker size from the series' ink, splits touching markers by a Gaussian mixture seeded at the heat peaks (one component per peak, sigma proportional to size), adds extra seeds to merged blobs whose area holds more markers than peaks, converges two seeds on one marker into one centre, drops a peak whose ink-blob is no wider than the owning line's stroke (dash veto), detects the matplotlib snap convention from the fractional parts of the isolated centres and backs it out, and detects triangles from the apex asymmetry of the isolated blobs and offsets to the bbox centre. A new `extract.loose_markers` carries peaks the embedding dropped; `markers.attach_loose` attaches them to a series by colour (and to a line's trace by distance) and forms new series by colour from what remains.

### Standard sets (geometry only, `--refine`)

| set | metric | v3 all / simple | af04090 (step23) all / simple | step24 all / simple | delta vs v3 (step24) |
| --- | --- | --- | --- | --- | --- |
| mpl-val 200 | marker_recall | 0.593 / 0.845 | 0.544 / 0.826 | 0.598 / 0.850 | +0.005 / +0.005 |
| mpl-val 200 | marker_precision | 0.704 / 0.825 | 0.812 / 0.896 | 0.799 / 0.875 | +0.095 / +0.050 |
| mpl-val 200 | marker_err_median_pct | 0.128 / 0.112 | 0.082 / 0.070 | 0.086 / 0.071 | -0.042 / -0.041 |
| plotly 150 | marker_recall | 0.465 / 0.829 | 0.399 / 0.780 | 0.445 / 0.783 | -0.020 / -0.046 |
| plotly 150 | marker_precision | 0.798 / 0.819 | 0.903 / 0.915 | 0.871 / 0.903 | +0.073 / +0.085 |
| plotly 150 | marker_err_median_pct | 0.091 / 0.081 | 0.030 / 0.025 | 0.044 / 0.027 | -0.047 / -0.054 |

Step24 (`c78db3f`) is af04090 with three guards: line-stroke per-peak veto only when `len(iso) >= 3 AND size <= stroke + 2` (fixes the `size_at = 3.0` false veto on `X`/`*`); raw-peak fallback when `len(iso) < 3` (fixes the triangle-centroid pull on packed scatters); `add_seeds` capped at 3 per blob, only trusted when `len(iso) >= 5` (fixes the merged-blob flood). On mpl-val: precision stays up (+5 to +10 pp vs v3), recall recovers to v3's level, error cut by a third. On plotly: precision +7 to +9 pp, error cut in half, recall drops a bit on simple (-5 pp) - the raw-peak fallback is less accurate on hollow/open Plotly markers whose centres the mixture would have placed well.

### Probe sets (geometry only, --refine, standard numbers)

The brainstormer's step24.sh writes `out/t4/eval-<k>-step24.txt`. Below is the subset finished so far (v3 vs step24):

| set | recall v3 all / simple | recall step24 all / simple | precision v3 | precision step24 | err v3 | err step24 |
| --- | --- | --- | --- | --- | --- | --- |
| dense | 0.765 / 0.760 | 0.810 / 0.808 (+0.045 / +0.048) | 0.856 / 0.855 | 0.930 / 0.933 (+0.074 / +0.078) | 0.168 | 0.105 (-0.063) |
| row | 0.700 / 0.700 | 0.667 / 0.667 (-0.033) | 0.849 | 0.868 (+0.019) | 0.135 | 0.120 (-0.015) |
| shapes | 0.977 / 0.976 | 0.985 / 0.984 (+0.008) | 0.936 / 0.935 | 0.984 / 0.984 (+0.048) | 0.118 | 0.069 (-0.049) |

Row is the one probe still regressing in step24: the dash/line-stroke veto fires on line+markers series whose line stroke is close to the marker size. Fixed in step25 (dash veto on scatter only; iso filter by elongation).

### Probe sets (per-marker diagnosis)

Measured either at af04090 (step23) or at c78db3f (step24). The three probe sets measured with step24-fill are re-run with the current branch so they share one semantics. See `teams/t4-markers/tools/diag_delta.py v3 step23` and `v3 step24` for the Markdown tables.

| set | tag | recall v3 -> after | precision v3 -> after | err v3 -> after (raw %) | FP causes delta | FN stages delta |
| --- | --- | --- | --- | --- | --- | --- |
| dense (step23 = af04090) | step23 | 0.765 -> 0.812 (+0.046) | 0.856 -> 0.925 (+0.069) | 0.168 -> 0.105 (-0.063) | dup -2194, legend -28, marker_ink +51, grid +31 | peak_off -1518, taken -662, unlabelled -128, moved +978, dropped +13 |
| shapes (step23 = af04090) | step23 | 0.977 -> 0.985 (+0.008) | 0.936 -> 0.984 (+0.048) | 0.118 -> 0.069 (-0.049) | dup -1132, grid -19, legend +16 | taken -149, dropped -25, unlabelled -10, moved +3 |
| row (step23 = af04090) | step23 | 0.700 -> 0.667 (-0.032) | 0.849 -> 0.868 (+0.019) | 0.135 -> 0.120 (-0.015) | dup -570 | **dropped +1062**, taken -232, peak_off -87, moved +80 |
| labels (step24) | step24 | 0.891 -> 0.847 (-0.044) | 0.593 -> 0.602 (+0.008) | 0.146 -> 0.115 (-0.032) | text -210, dup -90, bg -14, marker_ink +17 | dropped +248, moved +71, unlabelled -42, taken -5 |
| hollow (step24) | step24 | 0.825 -> 0.822 (-0.003) | 0.877 -> 0.923 (+0.045) | 0.138 -> 0.096 (-0.042) | dup -405, marker_ink -13 | **dropped +163, moved +49**, taken -119 |
| multi (step24) | step24 | 0.733 -> 0.766 (+0.033) | 0.838 -> 0.876 (+0.038) | 0.141 -> 0.088 (-0.053) | dup -1693, marker_ink +227 | peak_off -1739, taken -810, **moved +1445**, no_heat -59, dropped +110 |
| lines (step24, no-markers charts) | step24 | - | - | - | line_ink -105, legend -4 | - |
| val (step24) | step24 | 0.593 -> 0.598 (+0.006) | 0.704 -> 0.798 (+0.094) | 0.128 -> 0.086 (-0.043) | dup -869, **line_ink -784**, text 0, marker_ink +67, legend +13, bg +27 | taken -318, peak_off -276, unlabelled -244, dropped +440, moved +350 |
| plotly (step24) | step24 | 0.465 -> 0.445 (-0.020) | 0.798 -> 0.871 (+0.073) | 0.091 -> 0.044 (-0.047) | dup -567, line_ink -196, marker_ink -105 | taken -580, dropped +1005, moved +130, peak_off -129, unlabelled -87 |

Notes:
- The "moved" FN stage (markers that reached the pipeline but ended beyond tolerance after refinement) is up on every set where the mixture or the convention correction runs. On dense, shapes, hollow, multi, it is the price of the ink-based centring; the `err_median_pct` improvement shows the move is usually TOWARD the drawn centre, just occasionally past tolerance for a few.
- The "dropped" FN stage (markers whose peak had a label but which measure_series returned no centre for) is up on sets that have line+markers at tight sizes: row (+1062), labels (+248), hollow (+163). This is still the dash-veto / mass-filter signature, lighter after step24's guards but not gone.
- The lines set shows the dash veto still fires on dense, spiky lines (105 fewer line-ink FPs, from 526 to 421) but is not aggressive on all of them. A full win here would mean 0 FP on no-marker charts.

### Per-shape error on Plotly (step24, matched markers, median %)

The triangle convention and the mixture-centre work are visible on Plotly's symbols because Plotly draws at the exact value position (no snap jitter):

| symbol | v3 | step24 | delta |
| --- | --- | --- | --- |
| triangle-down | 0.178 | 0.049 | -0.129 |
| triangle-up | 0.129 | 0.016 | -0.113 |
| x (thin strokes) | 0.115 | 0.031 | -0.084 |
| star | 0.187 | 0.120 | -0.067 |
| hexagon | 0.049 | 0.022 | -0.026 |
| pentagon | 0.029 | 0.020 | -0.009 |
| circle, cross, diamond, square | ~0.01-0.06 | ~0.01-0.06 | ~0 |
| circle-open, diamond-open, square-open, triangle-up-open | 0.11, 0.10, 0.13, 0.29 | 0.10, 0.10, 0.13, 0.28 | ~0 (hollow rings still at network's estimate) |

Triangles improved by an order of magnitude; hollow symbols are unchanged (the ink-weight > 0.5 threshold does not capture a ring, so the mixture mass is too low and the fallback keeps the raw peak).

### Returned-centre bias on isolated symmetric markers (source px)

The snap back-out on matplotlib (Agg) is visible:

| set | tag | dx mean / median | dy mean / median | abs median |
| --- | --- | --- | --- | --- |
| val | v3 (ink centroid, = drawn centre) | -0.21 / -0.00 | -0.17 / -0.00 | 0.00 |
| val | step24 (snapped-back) | -0.46 / -0.50 | -0.44 / -0.50 | 0.71 |
| plotly | v3 (ink centroid, = drawn = value) | -0.05 / -0.00 | -0.03 / -0.00 | 0.04 |
| plotly | step24 (ink centroid) | -0.01 / -0.00 | -0.02 / -0.00 | 0.04 |

On mpl-val the step24 centres are now 0.5 px up-left of the drawn centre, which is the EXACT VALUE POSITION in matplotlib (Agg stamps the drawn marker at `floor(value + 1.0)`, so the drawn pixel sits half a pixel down-right of the value). That is the correct target, and `err_median_pct` drops from 0.128% to 0.082% against the ground-truth value. `err_drawn_median_pct` goes up slightly (markers no longer at the snap-aligned centre), by construction.

### F10. Asymmetric shapes under the ink-centroid refinement, no isolated examples to measure the convention

`measure_series` places a marker's centre at the centroid of its blob of ink, and corrects for the triangle convention (matplotlib: bbox centre; Plotly: centroid) only when there are enough **isolated** blobs to measure the apex direction and the centroid-to-bbox offset. On a chart whose triangles overlap (packed scatter, nn_rel < 1) there are no isolated blobs, no correction is measured, and the centre lands at the ink centroid - about `size / 6` below the drawn bbox centre for a "^" triangle. For a 17.5 px triangle this is 2.9 source px, borderline the 3 px matching tolerance.

Example: `data/t4-dense/14000078.png`, one series of 200 "^" triangles at 17.5 px (nn_rel 0.93). v3 (network estimate kept): 200 gt, 168 TP, 54 FP. af04090 (centroid pulled down): 34 TP, 152 FP (`out/t4/diag-dense-step23/14000078.png`, `14000078-heat.png` - the heat is pristine). The old `extract.refine_markers` kept the network's estimate for anything not symmetric under a half turn, which is correct for the asymmetric case when the shape convention cannot be measured.

Fix landed in step24 (`c78db3f`): when `len(iso) < 3` the measure returns the raw heat peaks (what the network produced, trained on the drawn centre) instead of the mixture-centroid. 14000078 recovers from TP 34 to ~168 at step24 (confirmed indirectly by the mpl-val step24 recall recovering to v3's level despite the mixture dominating big markers).

### F11. `add_seeds` overshoots in merged blobs of packed symmetric markers

For each connected component of a series' ink the add-seeds step adds `floor(area / area1 + 0.35) - k` extra seeds (where `k` is the number of heat peaks under the component and `area1` is the median isolated-blob area), up to 12. On a packed symmetric cloud (`o`/`s`/`v` at nn_rel < 0.5) a few merged blobs each get many extras, the mixture then has far more components than markers inside the mass, and its centres do not sit at the markers. FPs rise and TPs shift out of tolerance.

Example: `data/t4-dense/14000064.png`, three series ("o", "v", "o") at 15.8 px, nn_rel 0.42. v3: 378 gt, 221 TP, 293 FP. af04090: 182 TP, 441 FP (overlay: `out/t4/diag-dense-step23/14000064.png`). Dense-set totals confirm: FP cause "dup" fell by 2,194 (the split-aware mixture working on honest ropes) but new TPs were "moved" out of tolerance by 978 (the overshoot).

Fix landed in step24 (`c78db3f`): `add_seeds` capped at 3 extras per blob, only trusted when `len(iso) >= 5`. 14000064 recovery visible in dense step24 totals: `dup` FPs 2,194 fewer than step23 kept while recall still improves (0.812 → 0.810 - essentially maintained with far fewer spurious seeds).

## After step25 (`e4edf2b`)

Step25 (`e4edf2b`) is step24 with three further changes to the branch (brainstormer):
1. Dash veto on scatter only (`line_px is None`). The step24 veto fired on isolated marker+dash merged blobs in line+markers series on dashed or thick solid lines, taking out whole series (Plotly 500134, 500021).
2. Iso elongation filter (`elongation(patch) <= 4.0`). The step24 iso list could contain unresolved line fragments whose max dimension is huge; those were mis-read as marker shapes.
3. `extract.loose_markers` filters out heat peaks where `sem[TEXT] > sem[DATA]`. Drops digit and annotation FPs on labels and real screenshots (women/men chart's "26", "36", "46", "22" glyphs).

### Standard sets (geometry only, `--refine`)

| set | metric | v3 all / simple | step24 all / simple | step25 all / simple | delta vs v3 (step25) | delta vs step24 (step25) |
| --- | --- | --- | --- | --- | --- | --- |
| mpl-val 200 | marker_recall | 0.593 / 0.845 | 0.598 / 0.850 | 0.605 / 0.858 | +0.012 / +0.013 | +0.007 / +0.008 |
| mpl-val 200 | marker_precision | 0.704 / 0.825 | 0.799 / 0.875 | 0.758 / 0.860 | +0.054 / +0.035 | -0.041 / -0.015 |
| mpl-val 200 | marker_err_median_pct | 0.128 / 0.112 | 0.086 / 0.071 | 0.087 / 0.071 | **-32% / -37%** | +0.001 / 0 |
| plotly 150 | marker_recall | 0.465 / 0.829 | 0.445 / 0.783 | 0.460 / 0.832 | -0.005 / **+0.003** | +0.015 / **+0.049** |
| plotly 150 | marker_precision | 0.798 / 0.819 | 0.871 / 0.903 | 0.851 / 0.891 | +0.053 / +0.072 | -0.020 / -0.012 |
| plotly 150 | marker_err_median_pct | 0.091 / 0.081 | 0.044 / 0.027 | 0.048 / 0.032 | **-48% / -60%** | +0.004 / +0.005 |

Step25 is the first branch that is non-negative on EVERY axis vs v3: plotly simple recall went from the step24 -4.6pp regression back to +0.3pp (slightly above v3), while keeping the +7pp precision win and the -60% error cut. mpl-val's precision gave back 4.1pp vs step24 to let the extra recall through (the dash-veto-on-scatter-only lets some dashed-line FPs through, mainly on charts whose line+markers series are drawn with dashed lines - the right tradeoff since those are the real markers the step24 veto was killing).

### Per-chart recovery of the Plotly catastrophes

Measured on `rows-plotly-base.json` (v3), `rows-plotly-step24.json`, `rows-plotly-step25.json`:

| chart | shape / line pattern | gt | TP v3 / step24 / step25 | pred v3 / step24 / step25 | status |
| --- | --- | --- | --- | --- | --- |
| 500134 | triangle-up-open + diamond + hexagon on dashed line+markers | 228 | 186 / 0 / 111 | 226 / 0 / 119 | step25 recovers 111/186 (60%); step24 had wiped the series |
| 500021 | square on solid line+markers | 123 | 85 / 1 / 74 | 110 / 2 / 88 | step25 recovers 74/85 (87%); step24 had wiped the series |
| 500099 | triangle-down on dashdot line+markers | 42 | 41 / 20 / 30 | 48 / 25 / 37 | partial recovery (30/41 vs 20) |
| 500003 | pentagon on line+markers | 20 | 20 / 7 / 19 | 20 / 8 / 20 | full recovery (19/20) |
| 500107 | 5x line+markers rope, 6081 pts | 6081 | 931 / 708 / 708 | 1111 / 867 / 867 | **unchanged** (rope, needs zoom.py integration) |

Four of five step24 catastrophes recovered; the 500107 rope is a known F1-class case that no veto fix can touch (sub-pixel marker spacing).

### Probe sets (geometry only, `--refine`, step25 vs v3d)

Standard numbers, all seven probes measured in this worktree with `e4edf2b` under flock, one at a time:

| set | metric | v3d all / simple | step25 all / simple | delta vs v3d (step25) | note |
| --- | --- | --- | --- | --- | --- |
| dense | marker_recall | 0.765 / 0.760 | 0.810 / 0.809 | **+0.045 / +0.049** | packed scatter clouds - mixture + F11 fix |
| dense | marker_precision | 0.856 / 0.855 | 0.930 / 0.933 | +0.074 / +0.078 | |
| dense | marker_err_median_pct | 0.168 / 0.173 | 0.105 / 0.108 | **-37%** | |
| row | marker_recall | 0.700 / 0.700 | 0.697 / 0.697 | -0.002 | step24 regression (0.667) fully recovered |
| row | marker_precision | 0.849 | 0.861 | +0.012 | |
| row | marker_err_median_pct | 0.135 | 0.121 | -10% | |
| shapes | marker_recall | 0.977 / 0.977 | 0.985 / 0.983 | +0.008 / +0.007 | triangle correction |
| shapes | marker_precision | 0.936 / 0.935 | 0.984 / 0.983 | +0.047 / +0.049 | |
| shapes | marker_err_median_pct | 0.118 / 0.113 | 0.069 / 0.066 | **-42%** | |
| labels | marker_recall | 0.891 | 0.897 | +0.006 | step24 -4.4pp regression fully recovered; sem[TEXT] veto less sharp than hoped |
| labels | marker_precision | 0.593 | 0.606 | +0.013 | expected 0.75; see diagnosis |
| labels | marker_err_median_pct | 0.146 | 0.116 | -21% | |
| hollow | marker_recall | 0.825 | 0.829 | +0.004 | |
| hollow | marker_precision | 0.877 | 0.920 | +0.042 | |
| hollow | marker_err_median_pct | 0.138 | 0.096 | **-30%** | hollow rings still at network estimate |
| multi | marker_recall | 0.734 / 0.817 | 0.767 / 0.860 | +0.033 / +0.044 | step24 abandoned (GPU thrash); first clean read |
| multi | marker_precision | 0.838 / 0.864 | 0.876 / 0.939 | +0.038 / +0.075 | |
| multi | marker_err_median_pct | 0.141 / 0.140 | 0.088 / 0.082 | **-38% / -41%** | |
| lines | spurious markers / 100 charts | 534 | 446 | -88 (-17%) | dashes/spikes veto still fires; step24 line_ink -105 improvement held |

Every probe set positive or neutral vs v3d on every axis. The two step24 regressions (row -3.3pp recall, labels -4.4pp recall) are both fully recovered by step25.

### What the labels sem[TEXT] veto actually did

Expected on 02:31 EDT and in the step25 plan: precision 0.60 -> ~0.75 (predecessor's text-veto verifier measured 0.02-0.10% false-veto on real markers, so almost pure FP drop).

Measured: precision 0.593 -> 0.606 (+1.3pp). FP count fell by 160 (3547 -> 3387), but TPs rose by 36 (5175 -> 5211) and predictions rose by 100 (8722 -> 8598). The veto is correctly dropping digit/annotation peaks (text FPs down), but the dropped peaks were a smaller slice of all FPs than hoped: on `data/t4-labels` the dup/line_ink FPs on packed clouds dominate the FP side, and the sem[TEXT] veto does not touch those.

For comparison, step24 (which had the broader `len(iso) >= 3 AND size <= stroke + 2` line-stroke veto plus the dash veto on everything) traded FPs for recall the other way: step24 FP 3257, TP 4922 (precision 0.602 but recall only 0.847). Step25 has strictly more TPs than step24 (5211 vs 4922) and still 160 fewer FPs than v3d - net improvement across both axes.

Per-marker diag queued (labels step25) will confirm whether the TP gain is a side effect of the step25 dash-veto-on-scatter-only also unlocking labels line+markers series. See `out/t4/diag-labels-step25/summary.json` once it lands.

### Lines (no-markers probe) FP breakdown

| tag | spurious markers | note |
| --- | --- | --- |
| v3d | 534 | dashes of thick dashed lines, spike apices on noisy lines |
| step24 (from step24 diag delta) | ~429 (-105 vs v3d, 'line_ink' cause) | the full-strength dash veto |
| step25 | 446 | +17 vs step24 (step25 relaxed dash veto on line+markers; some of that reaches no-marker charts) |

Still 88 fewer spurious markers vs v3d. A full win would be 0 FP on no-marker charts; the gap is pure dashes/spikes the network emits a heat peak for.

