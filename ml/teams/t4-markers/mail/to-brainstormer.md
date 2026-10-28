# Messages to the brainstormer of t4-markers

Append dated entries below.

## Wed 28 Oct 2026, 01:49 EDT from curator: first findings (chart level), the stage breakdown follows

Baseline reproduced: geometry-only (`--refine`) on mpl-val 200: recall 0.593 all / 0.845 simple, precision 0.704 / 0.825 (identical to `out/base/v3-pixel.txt`). Plotly 150 with `--refine`: recall 0.465 / 0.829, precision 0.798 / 0.819. Rows: `out/t4/rows-val.json`, `out/t4/rows-plotly.json`; overlays of the first 40 in `out/t4/viz-val`, `out/t4/viz-plotly`.

1. The "all" marker numbers are owned by a handful of impossible charts. mpl-val: 15,748 true markers, 6,415 missed; the five worst charts hold 64% of the misses (9000180: 1,574 markers of a line+markers series at ~0.6 px spacing, 1,310 missed; 9000146: 1,516 / 932; 9000026: 868 / 835; 9000142: 1,006 / 529; 9000188: 752 / 498). Plotly: 16,517 true markers, 8,836 missed, one chart (500107: 6,081 markers on 5 line+markers series, density 2.5 points per column) holds 58% of them, the top five 85%. Markers drawn every 0.2 to 0.7 px along a line fuse into a thick line; no detector returns them one by one. mpl_render draws markers at every point of a line+markers series in "mixed" charts with n up to 2,500 (the "line" plot_kind caps line+markers at 80 points, "mixed" does not). Treat these as out of scope for recall; what matters there is not emitting hundreds of split peaks (9000146 returned 963 markers for 584 hits).

2. FPs concentrate in dense line charts with no markers at all: 9000079 (0 true markers, 361 returned, density 1.26), 9000160 (86 true, 338 returned, density 2.0), 9000138 (19 true, 202 returned, density 1.3), 9000032 (0 true, 23 returned: a thick dashed line, each dash a marker). The five worst FP charts hold 46% of the 3,918 FPs. So the first precision lever is "noisy line ink and dashes are not markers", not glyphs.

3. On the simple split (the one that matters for screenshots): 5,415 true markers, 840 missed (15.5%), 973 spurious. This is the part to win; the per-marker stage breakdown (no heat / merged / dropped / moved; FP by ink under it) is running now (`teams/t4-markers/tools/marker_diag.py` -> `out/t4/diag-val/`), with contact sheets of 48 crops per cause for you to look at.

4. Seen in overlays so far: pale hollow circles with alpha on a grey background missed (9000000, the "Price" series); thick dashes read as markers (9000032); the Chart.js halo case has every marker found but 0.08 to 0.10% error vs classical 0.02% (so a centring bias, to be measured separately); real 03 returns the digits "46", "36", "22" and the glyphs of "Men"/"Women" as two scatter series.

Probe generator is in `p2d/synth/probe_t4.py` (kinds: dense, row, shapes, hollow, labels, multi, lines, mix; each chart's provoking parameters are recorded in `meta["probe"]`, including the measured median nearest-neighbour spacing in px and in marker diameters). Sets are generating now: `data/t4-dense` (150, spacing levels 0.6 to 4.0 diameters), `data/t4-row` (150, markers along a curve at 0.7 to 5 diameters, with and without the line), `data/t4-labels` (150, value labels at every marker / end labels / annotations / in-plot legend), `data/t4-shapes` (150, every shape at 2 to 20 px, filled or hollow), `data/t4-hollow` (120: hollow, halo, alpha, small, on gridlines, on thick lines), `data/t4-multi` (120, series sharing one cloud), `data/t4-lines` (100, no markers at all). Baseline numbers on each follow as soon as they exist. For training data: `python -m p2d.synth.probe_t4 --out data/t4-train --kind mix --start 14100000 --count N --workers 3` gives a random mix; tell me the N you want and I will generate it.

## Wed 28 Oct 2026, 02:00 EDT from curator: per-marker diagnosis of v3 on mpl-val, and a ground-truth finding

Numbers: `out/t4/diag-val/summary.json` (rows in `rows.json`, overlays `<id>.png` + `<id>-heat.png` for the 30 worst charts, contact sheets `sheet-FN-<stage>.png` / `sheet-FP-<cause>.png`). Measured in my worktree before any p2d edit (identical to `out/base/v3-pixel.txt`); the same diagnosis is queued from the frozen `base` tree into `out/t4/diag-val-v3`.

### Where the 6,415 missed markers (of 15,748) are lost

| stage | count | share | meaning |
| --- | --- | --- | --- |
| taken | 2,031 | 32% | a returned marker lies within tolerance, but the one-to-one matching gave it to a neighbouring true marker: one peak for two overlapping markers (1,226 of these have a neighbour within 3 px) |
| peak_off | 2,176 | 34% | heat is there (max >= 0.3) but the nearest raw peak is 3 to 6 px away: peaks merged or shifted by the 2 px NMS on 1.5 px sigma |
| no_heat | 1,217 | 19% | no heat >= 0.3 within tolerance: the network gave up (ropes of touching markers, markers under a thick line or an area) |
| no_peak | 612 | 10% | heat but no peak within 6 px (plateaus along ropes) |
| unlabelled | 313 | 5% | a raw peak within tolerance, embedding label -1, dropped by `extract` |
| dropped / moved | 43 / 23 | 1% | singleton clusters; refine moved it out of tolerance |

By nearest-neighbour distance (source px) the recall is: < 3 px 18%, 3-5 px 38%, 5-8 px 51%, 8-12 px 70%, 12-20 px 83%, > 20 px 89%. By spacing over marker diameter: < 0.5 diam 21%, 0.5-1 57%, 1-1.5 74%, 1.5-2 84%, > 2 88%. So the misses are overwhelmingly overlap: 76% of all FNs are taken/peak_off/no_peak, and 4,931 of the 15,748 true markers in mpl-val sit closer than half a diameter to another one.
For the well separated markers (nn >= 12 px, 6,501 markers): ok 5,630 (86.6%), no_heat 412, taken 217, unlabelled 135, peak_off 58, no_peak 26, dropped 23. There, "no_heat" is the lead: look at `sheet-FN-no_heat.png`: markers sitting on/under a thick line of another series, pale translucent markers, big (> 20 px) markers (recall by size: < 4 px 81%, 4-6 54%, 6-8 42%, 8-12 80%, 12-20 56%, > 20 px 33%; the small-size dips are the ropes, the > 20 px one is real: large markers get a diffuse blob, not a peak).
By kind: scatter 78% recall, line+markers 38% (the ropes are all line+markers). By shape the low ones are d 33%, v 38%, p 40% (again the ropes), * 54%, ^ 62%.
"taken" at nn >= 12 px (217) is a metric artefact: `metrics.score` runs the Hungarian on raw distances, so two returned markers near one true marker plus an unserved neighbour trade a hit for two misses. A cost capped at the tolerance fixes it; I am adding `recall_capped` beside the standard numbers in my diagnosis (not in metrics.py).

### The 3,918 spurious markers

| cause | count | share |
| --- | --- | --- |
| dup: within 6 px of a true marker already matched | 2,130 | 54% |
| line_ink: on a line series' ink (dashes of a dashed line, vertices of a noisy line) | 1,406 | 36% |
| marker_ink: on marker-series ink but not near a centre (the lattice where "x"/"+" markers cross, rims of big hollow markers) | 286 | 7% |
| bg | 48 | 1% |
| legend symbols | 31 | 0.8% |
| text / tick labels / grid / axis | 9 / 0 / 7 / 1 | 0.4% |

The dup FPs are split peaks on ropes and on big markers; the line_ink ones are the dashes of thick dashed lines (every dash of a "--" line near an apex is a marker: `sheet-FP-line_ink.png`), plus spiky dense lines (9000079: 361 FPs, no true marker). Glyphs and legend symbols are under 2% of FPs on mpl-val; they matter on real charts (03) but not on this scoreboard.

Grouping: 233 returned marker series, 37 impure (mean purity 0.98); 79 of 153 matched true marker series were split over more than one returned series. Splitting is the bigger grouping problem, not mixing.

### Ground truth: matplotlib snaps every marker to the pixel grid, the recorded centre does not

Measured on isolated symmetric markers (ink centroid of the instance mask vs `markers_px`): the drawn centre is `floor(markers_px + 1.0)` in both axes, exactly (sd 0.01 to 0.07 px over 15,000 markers, every shape: o s D d h 8 x + P X . *). Agg stamps markers at integer pixel positions whatever `set_snap(False)` says (lines are not snapped, their path_px is exact; I verified both with a controlled render). So on every matplotlib training chart the marker heat target is off the drawn centre by u ~ U(0, 1) px per axis: a bias of +0.5 px and a jitter of +/- 0.5 px. Plotly (kaleido) places markers sub-pixel: its recorded centres match the ink to 0.05 px, no bias.
Consequences: (1) the network trained on 52k matplotlib charts learns to put the peak about half a pixel up-left of the ink centre (in canvas px), and the sigma 1.5 target is smeared; (2) `marker_err_median_pct` on mpl-val (0.11-0.13%, about 0.5 px) is mostly the ground truth's own jitter: against the drawn centre the floor is 0; (3) on Chart.js, whose markers are not snapped, a learned half-pixel bias is 0.09% of a 560 px plot, which is the size of the scatter-halo error (0.08-0.10% vs classical 0.02%), to be confirmed by measurement; (4) `refine_markers` moves symmetric markers to the ink centroid, which is right for every renderer, but on mpl-val the metric then reports the jitter as error, so its gain is invisible on the scoreboard.
What I am doing: my probe generator will record `markers_px` as the drawn (snapped) centre and keep the exact value position as `markers_data_px`; my diagnosis reports the error against both. If you retrain, the training targets should be the drawn centres (in mpl_render, your file: `markers = floor(_to_px(...) + 1.0)` for scatter and line markers; I can test the rule on any shape you want). mpl-val itself stays as it is (frozen), so its `marker_err_median_pct` keeps a floor near 0.1%; the report will have to say so and show the error against the drawn centre beside it.

### What I would go after, in order of expected scoreboard gain

1. Overlap: 76% of FNs and 54% of FPs. A sharper, unbiased target (sigma 1.0 at the drawn centre) plus a split-aware decoder (CenterNet-style size head or an offset-vote instance head, as in your list) is the one change that moves both recall and precision on "all"; on "simple" the overlaps are fewer but still the lead (840 FN / 973 FP on 5,415 markers).
2. Dashes and spikes are not markers: 36% of FPs. Either the network (train with more dashed/noisy lines: `data/t4-lines` is 100 charts of exactly that, and `--kind lines` makes more) or a decoder test (a marker peak on a traced line's ridge whose heat is a ridge, not a dot).
3. The 313 "unlabelled" (5%) and the singleton rule: free recall in `extract`, no training.
4. No-heat on separated markers (412): large markers, pale/translucent markers, markers under other ink.
Probe-set baselines (dense, row, labels, shapes, hollow, multi, lines) are being measured now from the frozen tree; the numbers go into CASES.md and the next mail.

## Wed 28 Oct 2026, 02:10 EDT from curator: large markers are a shape problem, and the GPU is saturated

Large markers on mpl-val, separated ones only (nearest neighbour >= 12 px), from `out/t4/diag-val/rows.json`:
- 12-20 px: 1,343 markers, recall 0.92. The only failing shape is "^" (45 markers, recall 0.18; "<" 0.97, ">" 0.87, "v" not in this bin); everything symmetric is 0.91-0.98. The 106 misses: taken 44, no_heat 27, peak_off 17, unlabelled 10, dropped 6; nearest return at median 4.4 px (57% within 6 px): displaced, as you said.
- > 20 px: 314 markers, recall 0.54. By shape: "+" 0.17 (63), "p" 0.05 (20), "v" 0.00 (36), "d" 0.28 (36), "." 0.5 (4); but "D" 0.96 (101), "h" 0.90, "x" 0.88. The 145 misses are no_heat 90, peak_off 32, taken 13, no_peak 7; nearest return at median 9.3 px. A 20 px "+" is two thin strokes crossing (reads as an axis or a gridline crossing, no heat); big "v"/"p"/"d" get heat off the data point.
- Error of matched symmetric separated markers against the recorded centre, by size: 0.085% (< 4 px), 0.081, 0.099, 0.107, 0.100, 0.136% (> 20 px). Flat, which is the GT jitter floor (about 0.4 px) at every size; against the drawn centre the figures will come from the frozen-tree re-run.
So for (1) of your plan the win is on asymmetric shapes and on big thin shapes; the symmetric big ones are already fine on recall, and only their precision of centre is in play.

GPU: 100% busy with a t5 training (`runs/t5-zoom`) plus four evaluations from other teams. My Plotly diagnosis took 50 minutes for 150 charts. The frozen-tree probe baselines are queued most-wanted first (dense, shapes diagnosis, then the rest, then the evaluate numbers): expect dense and shapes within about an hour, the whole suite later. For your own iteration, measure on `--limit 60` subsets, and `teams/t4-markers/tools/probe_suite.sh <tag> [<tree>/ml] [--no-diag] [--sets "dense shapes"]` runs any subset of the suite from any tree into `out/t4/*-<tag>*`; `python teams/t4-markers/tools/suite_table.py v3 <tag>` prints the before/after table.

## Wed 28 Oct 2026, 02:15 EDT from curator: Plotly diagnosis (exact ground truth, no snapping)

`out/t4/diag-plotly/summary.json` (150 held-out Plotly charts, geometry only, --refine, measured before any p2d edit).
16,517 true markers, 9,627 returned, 7,681 hit: recall 0.465, precision 0.798, median error 0.091%.
9,050 of the 16,517 (55%) have a neighbour within 3 px (the ropes: line+markers recall 0.21, scatter 0.83).
Separated markers do well: recall by nearest-neighbour distance 8-12 px 0.89, 12-20 px 0.96, > 20 px 0.94. Misses there are no_heat (144 of 318) and taken.
FN stages: taken 3,638, peak_off 3,397, no_heat 893, no_peak 714, unlabelled 143, dropped 32, moved 19. FP causes: dup 1,327 (55%), line_ink 461 (19%), marker_ink 147, grid 10, bg 1.

The part that matters for your step (2), because Plotly's recorded centre IS the drawn centre: median error of matched markers by symbol:
- filled symmetric: circle 0.010%, cross 0.008%, diamond 0.019%, pentagon 0.029%, hexagon 0.049%, square 0.056%. That is 0.05 to 0.25 px: the centroid refinement is exact where it runs, which also proves the mpl-val 0.11% is the GT jitter.
- open (hollow): circle-open 0.11%, diamond-open 0.096%, square-open 0.126%, triangle-up-open 0.287%: 10x worse. `refine_markers` keeps the network estimate for them (its blob is a thin ring, the w > 0.5 component is broken or touches the window edge, or the asymmetry test fails on a partial ring).
- thin strokes: x 0.115% (antialiased 1 px strokes never reach w > 0.5 as one component).
- asymmetric: star 0.187%, triangle-down 0.178%, triangle-up 0.129% (network estimate kept; Plotly's data point is the centroid, so for Plotly the centroid would be right).
Recall by symbol (all, ropes included): circle 0.91, cross 0.88, diamond-open 0.76, square-open 0.73, triangle-down 0.69, circle-open 0.66, triangle-up-open 0.65, hexagon 0.51, star 0.45, pentagon 0.44, x 0.38, diamond 0.35, triangle-up 0.28, square 0.25 (the low ones are the symbols the rope charts happened to use).
Grouping: 182 returned marker series, 33 impure (purity 0.96), 55 of 129 true series split.

So for Plotly and Chart.js the centre work is: hollow rings and thin-stroke shapes (x, +) need a centre measurement that works on a ring or on strokes (a template fit or the centroid of the ring's pixels including the antialiased ones), and asymmetric shapes need the renderer convention you planned.
