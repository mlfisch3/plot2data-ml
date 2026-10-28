# Messages to the brainstormer of t3-precision

Append dated entries below.

## Wed 28 Oct 2026, 01:39 EDT from curator

Starting point, from reading the code before any measurement:

- The geometry-only scoreboard (`evaluate --refine`) calls `refine_lines` and `refine_markers` only, never `refine_ticks` (evaluate.py line 155); the tick figures there (0.29 / 0.32 px) are the raw network. The end-to-end path (`pipeline.run`) does snap ticks, and its tick error on mpl-val is the same (0.287 / 0.326 px), so snapping is a wash on matplotlib charts and only matters on other renderers (corpus).
- `refine_lines` keeps the network's estimate wherever the vertex heat within a 3x3 canvas window exceeds 0.3 (`keep_vertex`), and wherever the centroid moves more than max(1.5, 1/s) px from it. At a sharp peak the vertex head's own sub-pixel estimate (parabola on a sigma=1.5 Gaussian, on the downscaled canvas) is what stands; nobody measures the tip on the source pixels. The classical engine does (`trace.ts` `columnValues`/`turnDepth`: outermost ink + half a stroke, with a miter test), and that is how it gets -0.26% on sawtooth where we get +0.27%.
- Line heat sigma is 1.0 canvas px, vertex/tick 1.5, corner 2.0. For a 1600 px chart the canvas scale is 0.48, so one canvas px is 2.1 source px: sigma 1.5 on ticks is 3 source px.
- `plot_frame` takes the top 12 corner peaks over 0.25 and splits x and y by the biggest gap; with a hidden spine (plotly / dash / news presets, half of all seaborn-white charts) there is nothing at the corner but the end of a gridline.

What I am measuring now (results within the hour, in the mailbox and CASES.md): per-column signed error on found lines (bias vs noise, versus slope, line width, scale, gridline proximity), peak error split into clipped versus blunt, tick error by renderer/side/tick style, the frame failures, and a same-chart-at-several-sizes scale test. Probe sets follow under data/t3-*.

## Wed 28 Oct 2026, 01:58 EDT from curator: the diagnosis on 200 mpl-val charts (geometry, v3, refine)

Full tables: `out/t3/report-base-simple.txt` and `out/t3/report-base-all.txt` (from `scripts/diag_report.py out/t3/diag-base.pkl`); crops of the median-ranked series' worst stretch in `out/t3/cases/` (green truth, blue raw net, magenta refined). Source pixels throughout.

**1. Lines: the error is not sub-pixel, it is a few pixels on a tenth of the columns.** Simple charts, 132 matched series, 105k columns:
- 89.3% of columns are within 3 px; they have zero bias (-0.003 px), median |err| 0.068 px, and hold 1.3% of the squared error. On flat columns (|slope| < 0.5, > 3 columns from a vertex) the refined centroid is at 0.023 px median; there is no bias by line width (0.5 to 6 px: +0.02 to -0.07), none by canvas scale (0.4 to 2: p50 0.016 to 0.061), none by ink colour. Where `refine_lines` runs, it is as good as it needs to be.
- The other 10.7% of columns hold 98.7% of the squared error. They are: |slope| > 4 (18% of columns, 63% of the error, p50 1.7 px, p90 14 px, 81% kept from the net); within 3 columns of a vertex (53% of the error; within 8 columns: 65%); and in general the columns where refine keeps the network's estimate (43.5% of all columns).
- Oracle ceilings (`scripts/oracle.py`): median simple RMS 0.189% -> 0.039% if the net-kept columns were exact; -> 0.066% if columns within 8 of a vertex were exact; -> 0.061% if |slope| > 2 were exact; -> 0.117% if within 3 of a vertex; -> 0.162% if within 1. For "all": 0.311% -> 0.072% (net-kept exact), 0.101% (within 8 of a vertex).
- Why refine keeps the net, from the crops of median-ranked series: (a) low-contrast ink (`dd < 400`, e.g. 9000148 teal on lavender, a 5 px line left entirely to the net, 1.5 px wander on flat columns); (b) the ink run reaches the window edge (R = max(3, 2.5/s) + 4 rows): every steep flank and every thick line at small scale, e.g. 9000041-2 at s = 0.39, slope 6.6, a 2 px offset along the whole flank; (c) dashes and gaps: no ink in the column, the net's centre line through the gap is off by 2 px (9000196-1, 9000192-0 are dashed); (d) vertex heat > 0.3 in the 3x3 canvas neighbourhood, i.e. within up to 4 source px of a vertex at s = 0.4.
- A falling-on-screen slope (slope > 0) has bias -0.05 px and a rising one +0.03 on the near-correct columns: a tiny lag, not worth chasing.
- The worst 23 simple series by RMS are all tracing failures (gross columns hold > 90% of their error); 49 of 132 series are tracing-dominated, 83 precision-dominated with median RMS 0.081%. So the scoreboard median sits on series whose RMS is made by a few gross columns at vertices, flanks and gaps.

**2. Peaks: clipped, and by the network's own estimate (refine does not touch them).** Simple charts, 916 scored turning points:
- Median inward error +1.26 px (0.307% ph), 53% clipped by > 1 px, 36% by > 3 px, 7% overshoot by > 1 px; raw net and refined are identical at peaks.
- By turning angle (0 = straight): < 60 deg: p50 0.05 to 0.2 px (fine); 90-120: +2.1 px; 120-150: +0.8; > 150 (needles): +2.3 px, 66% clipped > 1 px. By width 2 px below the tip: < 2 columns: +1.66 px; > 16 columns: +0.45.
- By canvas scale: s = 1: p50 -0.09 px (14.8% clipped > 1 px) ; s > 1: +0.19; 0.7-1: +0.65; 0.5-0.7: +2.5; < 0.5: +2.5 px (68% clipped). The clipping is resolution loss on the 768 x 512 canvas.
- By line width: > 4 px: +3.6 px (0.59% ph), 63% clipped; < 1.2 px: +0.5.
- Even when the vertex head fires within 1 px of the tip (471 of 916 peaks) the median shortfall is +0.74 px (45% > 1 px); at 1-2 px: +2.3; no vertex within 4 px: +4.0 px.
- "All" split: median +3.7 px (1.77% ph): one-sample spikes of dense series (> 150 deg turning: 3,886 of 5,605 peaks, p50 +8.4 px). t3-spikes probes this.

**3. Ticks: the network is unbiased at 0.27 px; snapping to drawn marks is biased by +0.25 px; half the variance is a per-axis shift.**
- Raw: x p50 0.27 px, bias -0.02; y p50 0.30, bias +0.10. Snapped (`refine_ticks`, 73-76% of ticks): x 0.34 (bias +0.21), y 0.37 (bias +0.28); on the very ticks it snapped it goes from 0.25 to 0.35 px. On matplotlib, snapping is a loss.
- The drawn marks and gridlines are pixel-snapped by matplotlib, the truth is not: snap error by the sub-pixel phase of the true position: frac in [0, 0.25): +0.63 px (p50 0.80); [0.25, 0.5): +0.46; [-0.25, 0): -0.02; [-0.5, -0.25): +0.22. The raw network error carries a weaker version of the same phase dependence (+0.21 / -0.23 in the two central bins), since it learned from the drawn marks. Any "snap to the mark" or "fit all gridlines jointly" idea inherits this quantisation unless it models it.
- Per axis: the mean error over an axis's ticks has std 0.34 px (x) / 0.46 px (y) across axes, the within-axis residual std is 0.29 / 0.28. Half the variance is a common shift per axis, which a least-squares calibration cannot average away.
- Label-only axes (no mark, no grid): x bias +0.22 to +0.30 px, y +0.52 to +0.72 px (n = 57 / 47): the nogrid case. Marks drawn inward only: y bias -0.1 to -0.3.
- No dependence on scale worth noting (p50 0.21 at 0.7-1, 0.38-0.40 at < 0.5).

**4. Frame: the visible edges are fine; the hidden top edge is the whole p90.**
- Found 200/200 in geometry mode. The e2e "frame_found 0.89" is an artefact: evaluate.py replaces the extraction by an empty one when calibration fails.
- Visible spine edges: p50 0.37-0.45 px, p90 0.9-1.1 px. All four visible (43 charts): max-corner p50 0.75 px, p90 1.75.
- Hidden top edge (151 of 200 charts): bias +5.2 px, p90 13.2 px (the worst: 9000023 highcharts +211 px, 9000049 +97, 9000133 excel +74). Hidden bottom: bias +1.6, p90 6.9. Hidden left/right are fine (p50 0.6). The frame p90 of 13 px is entirely the top edge of spineless house styles, where the corner heat has nothing to sit on and lands on the first gridline below. It also truncates the series ROI.

**5. Refinement as a whole on the same 60 charts (your numbers, confirmed): simple RMS 0.146% without vs 0.160% with; marker error 0.077 vs 0.095.** From the column records, refine_lines moves the flat columns from 0.153 to 0.045 px p50, so the loss must come from the columns it moves wrongly (the |yr - yc| gate lets through centroids pulled by neighbouring ink / gridlines: columns 1.5-3 px from a gridline have p50 0.18 px against 0.05 elsewhere, 83% net-kept) and from the vertex columns dropped and re-inserted by `snap_vertices`. I will split that next.

Probe sets built: data/t3-peaks (240), t3-spikes (160), t3-scale (128), t3-ticks (144), t3-width (96), t3-log (48), t3-grid (48), t3-frame (80); baseline per-factor tables land in CASES.md as the GPU queue drains (plotly-v1 first).
