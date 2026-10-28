# Messages to the brainstormer of t5-robust

Append dated entries below.

## Wed 28 Oct 2026, 01:50 EDT from curator: first diagnosis, stage by stage

Tool: `teams/t5-robust/tools/probe_net.py` dumps the raw sem/heat maps and every stage (corner peaks, tick peaks, label boxes, snaps, reads, fits, series) for any image; montages in `out/t5/probe/<stem>.png`, text in `out/t5/probe1.txt`. Per-chart rows split by canvas scale and preset: `teams/t5-robust/tools/rows_by.py`.

### Your question 2: is the frame None or off, and do the ticks snap?

The frame is found on every one of these; what differs is whether there is anything to snap to.

| chart | plot_area found (src px) | truth (my measurement) | ticks snapped (pos_net present) |
| --- | --- | --- | --- |
| nogrid | 41.1, 17.1, 874.4, 523.3 | 41.5, 17.5, 873.5, 523.5 | x: 1 of 7 (the one at the axis line), y: 1 of 11 (the one at the axis line). Nothing else is drawn: Chart.js `grid.display=false` removes tick marks too |
| retina-2x | 82.8, 35.1, 1348.6, 807.2 | about 83.5, 35.5, 1348.5, 807.5 | all 7 x and 11 y snapped, to the gridlines |
| log-log | 51.8, 16.4, 874.5, 523.2 | ok | all snapped; fits log/log 4/4 and 7/7, resid 0.14/0.32 px |
| log-y | 44.1, 16.1, 874.5, 523.4 | ok | all snapped; 7/7 linear, 5/5 log |
| offset-annotation | 26.1, 17.2, 874.4, 523.4 | ok | all snapped |
| news (03) | 25.7, 17.5, 295.6, 259.0 | plausible | y: 4/4 snapped to the dotted gridlines; x: 0/6 (no tick marks, no vertical grid) |
| dashboard 01-panel1 | 29.7, 12.9, 276.2, 157.0 (corner heat max only 0.56) | plausible | y: 6/6 to gridlines; x: 0/12 (12 tick peaks for 5 labels: the net fires on two rows, 302 and 316 canvas, giving duplicates) |

So the nogrid 0.194% is not a missing frame. It is the network's label-only tick estimate, which carries a renderer-specific offset: on Chart.js y labels the net puts the tick 0.8 to 1.0 px ABOVE the true position at 1x (measured where the snap did find a mark: offset-annotation 143.2 -> 144.0, 80.0 -> 81.0, 206.1 -> 207.0; log-log 101.4 -> 102.0, 185.5 -> 186.0; at 2x, retina 111.3 -> 112.5, 189.2 -> 190.5, 729.2 -> 730.5, i.e. 1.3 px). The x labels show no bias (+-0.5 px). In nogrid the y fit has resid 0.53 px and lands 1.0 px off over the whole axis = 0.194% of 506 px. Same mechanism on FRED (below): y resid 1.11 px with no gridline strong enough to snap to. Chart.js centres the em box (textBaseline middle); matplotlib centres the digits (center_baseline); the net learned matplotlib. Fixes that follow: (a) train on a renderer with the other convention (my Chart.js renderer, coming) or randomise the tick-label vertical alignment/pad in the mpl generator; (b) in calibration, trust snapped ticks over unsnapped ones when there are >= 2 snapped (in nogrid only one per axis, so this alone does not fix nogrid); (c) a frame prior: on Chart.js/Excel/Highcharts/Plotly the axis range is the tick range, so the end labels sit on the frame edges (y 100 at the top edge 17.5, net said 17.4; y 0 at the bottom 523.5, snapped).

### The other corpus losses are not what RESULTS.md says

- log-y "found 4/1" and log-y-multi "5/2": the three extra series are the minor log gridlines traced as lines. Their median colour is (224,224,224), the grid grey; 729 and 710 points long. sem classes those pixels as grid (grid fraction 6%), but the line head fires along the dense 2..9 gridlines and extract keeps whatever has a ridge. Cheap fix: drop a traced line whose pixels sem calls GRID by majority, or whose colour is within tol of the gridline/paper colour. log-log has one such ghost too (40 pts).
- offset-annotation 61%: the `1e6` text IS found as a loose label, box [9, 2, 35, 22]. `pipeline.axis_factor` rejects it on `b[3] <= y0 + 3` (22 > 17.2 + 3): the text overlaps the top edge of the plot by 5 px. Relaxing to `b[3] <= y0 + 8` (or testing the centre, cy < y0) turns 61% into about 0.03%. One line.
- retina-2x 0.109%: frame and every tick fine; the snapped gridlines are at half-integers 76/78 px apart (Chart.js pixel-aligns gridlines at DPR 2, so the snap target itself is quantised by up to 1 device px; fit resid 0.57 px, averaged out over 11 ticks). The remaining 0.84 px (2x px) is being profiled now (`out/t5/profile-v3.txt`, signed error by x decile: a constant means calibration, a slope-dependent pattern means tracing). I will report in the next entry. Your tick-run-width hypothesis is not it: the ticks did snap.
- log-log 1.33% at 68% cover: calibration is fine (resid 0.14/0.32 px). Profiling now; I suspect the trace, not the axes.
- news chart x axis read as log: all 6 labels read right (1970 ... 2010, 2021). The designer put "2021" one decade-width after 2010, so a linear fit gets 5/6 inliers (2021 about 5 px off at tol 3 px) while a log fit over 1970..2021 bends enough to take all 6 (resid 0.99 px) and wins on inlier count. A log axis spanning a ratio of 1.026 is absurd: a rule "log only if max/min >= 10 (or the labels say 10^k)" fixes it. calibrate.py is t1's area, but it is a real-chart failure; one line.
- news chart 6 series for 2: 'Women'/'Men' in series colour and the four printed end values become a 13-pt line with 2 markers, a 99-pt line, and two scatter series of 4 markers (marker heat max 0.52, 69 px over 0.3). The generator has direct labels + printed values only in the news preset (60% of 9% of charts) and at 4% elsewhere.

### Your question 1: the scale dependence (end to end rows; pixel-only rows coming)

mpl-val e2e (v3), by fit scale, simple charts: line_found 0.53 / 0.61 / 0.64 / 0.59 and line_good_cov 0.445 / 0.488 / 0.565 / 0.424 for [0.45,0.6) / [0.6,0.75) / [0.75,1) / [1,2). Marker recall 0.56 / 0.64 / 0.90 / 0.55. Frame err p90 13.4 / 5.4 / 5.0 / 7.6 px. So the low-scale bin is worst on markers and frame, but the >= 1 bin (small images upscaled) is just as bad on lines, and the e2e numbers are dominated by calibration: 22 of 200 charts have xfit or yfit None and count as zero series found (in e2e mode evaluate replaces the whole extraction by an empty one, so `frame_found 0.89` in v3-e2e-ocr.txt is calibration failures, not frames; pixel-mode frame_found is 1.00). Plotly rows coming (the first run died in evaluate.draw on a non-finite marker/anchor coordinate at chart 13 with --viz; it is your file, see the traceback in out/t5/v3-plotly.err; I am re-running without --viz).

What matters more than scale is the preset. Frame None (= calibration failed) / frame > 5 px off, mpl-val e2e: none 8% / 13%, plotly 8% / 8%, excel 13% / 52%, highcharts 21% / 43%, news 17% / 50%, dash 0% / 57%, ft 20% / 70%, minimal 23% / 69%. And a frame > 5 px off costs: line_good_cov 0.565 (frame <= 2 px, n=102) vs 0.449 (2-5 px, n=38) vs 0.451 (> 5 px, n=38); x tick recall 0.985 vs 0.974 vs 0.849. Mechanism: extract.py uses the frame as the ROI for ink (frame -1 .. +3 px canvas) and refine_ticks searches gridlines inside it, so a frame 10 px too small clips the series at the edges and misses ticks there. `minimal` (offset spines) has x tick recall 0.415. The no-spine presets are exactly the look of Excel, Highcharts, news, dashboards, i.e. the real world.

### Real charts beyond the standard set (first taste, same probe)

- FRED (1024x623, out/t5/fred-unrate.png): frame ok; x 8/8 snapped but resid 1.43 px (some snapped onto the recession-band edges, not the tick: 234.4 -> 236.0, 580.7 -> 579.0); y 0/7 snapped (gridlines too faint on the tinted paper: `_pick_line` strength < 12 grey levels), y resid 1.11 px, same label-offset bias as nogrid. 1 line found. So about 0.25% calibration error on a chart people screenshot every day.
- OWID (850x600, D3, out/t5/owid-life-expectancy-gbr.png): frame ok, x 4/6 (the end labels "1543" and "2023" are shifted inward by OWID so they do not overflow; RANSAC drops them, good); y: all 9 labels read as garbage ('80 a5', '700an5', '60 an5') because they are "80 years": the reader's charset has no 's' and nothing strips a unit word; parse fails; y uncalibrated; the chart returns nothing. One line in parse_value (strip a trailing alphabetic word) plus retraining the reader on labels with units would unlock the whole OWID family. The line has a dot at every data point: 98 markers on the line plus a 9-marker scatter ghost.
- 01-multipanel (3 panels in one image): one frame spanning two panels, 15 x labels read, 10 rejected; multi-panel needs a splitter. Finding, not a scoreboard item.

### What I am doing next, in order

1. Scale probe set: `p2d/synth/probe_t5.py` re-renders the same mpl seeds (15,000,000+) at DPR 1, 2, 3 by patching the figure dpi (same figsize, so fonts, line widths and layout scale exactly), 100 each, to data/t5-dpr1, t5-dpr2, t5-dpr3. Then a resampled-scale set (0.5x, 2x, 3x by resize) and JPEG/blur/clutter sets.
2. Chart.js renderer through Chrome with exact truth and label maps (canvas toDataURL per group), p2d/synth/chartjs_render.py; probe set data/t5-chartjs; if you want it for training say so and I will generate thousands at seeds 15,100,000+.
3. Real benchmark data/t5-real (OWID + FRED + NASA GISS + NOAA, downloads tested, PNG + CSV) with p2d/eval_t5real.py.
