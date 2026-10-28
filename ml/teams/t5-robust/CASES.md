# t5-robust: the failure catalogue

Curator's record of what breaks on charts outside the training distribution, with the evidence.
"Before" numbers come from the judge's frozen worktree `PLOT2DATA-teams/base` (commit 6b313e9, network `runs/v3/best.pt`, reader `runs/ocr1/best.pt`); "after" numbers name the commit of the live tree they were measured on.
Errors are a percentage of the plot's full height unless the section says otherwise.
Tools: `teams/t5-robust/tools/probe_net.py` (every stage of the pipeline on one image, with a montage of the raw heads), `rows_by.py` (per-chart rows by canvas scale and preset), `corpus_profile.py` (signed error along x on the corpus).
Baseline outputs are under `ml/out/t5/`: `v3-corpus.txt`, `v3-real.txt`, `v3-e2e-ocr.txt`, `v3-plotly-e2e.txt`, `v3-*-rows.json`, `probe1.txt`, `profile-v3.txt`, overlays in `corpus-viz-v3/`, `real-v3/`, `probe/`.

## 1. Tick labels with nothing to snap to: the renderer's label-to-tick offset

**Where.** `corpus/linear-single-nogrid` (0.194%), FRED charts (y residual 1.1 px), any chart with labels but no tick marks or gridlines on that axis (Chart.js with `grid.display=false`, which removes tick marks too; OWID's x axis; news graphics; dashboards).

**What happens.** The frame is found (nogrid: 41.1, 17.1, 874.4, 523.3 against a true 41.5, 17.5, 873.5, 523.5). `refine_ticks` moves a tick onto a drawn mark or gridline when one is within 2 px; on nogrid only the two ticks at the axis lines (x = 0, y = 0) snap, the other 16 keep the network's estimate. That estimate is biased: the network learned matplotlib's placement (the digits centred on the tick) and Chart.js centres the em box, so the digits sit about 1 px above the tick. Measured where a snap target existed, net estimate -> snapped: offset-annotation 143.2 -> 144.0, 80.0 -> 81.0, 206.1 -> 207.0; log-log 101.4 -> 102.0, 185.5 -> 186.0; retina-2x (device px) 111.3 -> 112.5, 189.2 -> 190.5, 729.2 -> 730.5. The x labels show no bias (+-0.5 px). On nogrid the y fit (11 labels, resid 0.53 px) lands 1.0 px off over the whole axis: the signed error is a constant -0.19% at every x decile (`profile-v3.txt`), i.e. 1 px of 506.

**Probe.** `data/t5-chartjs-val` (100 Chart.js charts, 20% without gridlines, 50% without tick marks) and the real benchmark's FRED charts (gridlines too faint for `_pick_line`'s 12-grey-level floor on tinted paper).

**What would fix it.** Train on a renderer with the other convention (`data/t5-chartjs`, 4,000 charts) or randomise the label alignment in the matplotlib generator (the brainstormer's `data/t5-mpl-va`); weight snapped ticks above unsnapped ones in the fit; use the frame edge for the end labels on charts whose range is the tick range.

## 2. Minor log gridlines traced as series

**Where.** `corpus/log-y` (found 4/1), `log-y-multi` (5/2), `log-log` (2/1); Chart.js draws gridlines at 2..9 of every decade, the training charts rarely have minor gridlines.

**What happens.** sem classes the gridline pixels as grid (6-8% of the canvas), but the line head fires along the dense horizontal lines and `extract` keeps any ridge with enough support: three ghosts of 729, 710 and 98 points with median colour (224, 224, 224), the gridline grey. The true series is found and scored normally; the ghosts cost precision and would land in a user's CSV.

**Fixed by** 259b09d (drop a traced line whose pixels sem calls GRID by majority); measured after: see section 9.

## 3. The axis multiplier that touches the plot

**Where.** `corpus/offset-annotation` (61.2%: the values come back in millions-less units).

**What happens.** The `1e6` text is found as a loose tick-label box [9, 2, 35, 22]; `pipeline.axis_factor` requires the box to end above the plot top plus 3 px (y0 = 17.2, so 20.2) and the box ends at 22: rejected by 1.8 px. Everything else about the chart is right (frame, 7/7 and 8/8 ticks, 0.03% trace).

**Fixed by** 259b09d (tolerance widened); measured after: see section 9.

## 4. Resolution: retina screenshots and small canvases

**Where.** `corpus/retina-2x` (0.109% against 0.033% for the same function at 1x); `data/t5-dpr2` and `t5-dpr3` (the same 100 matplotlib charts at 1x, 2x and 3x device pixel ratio, widths 1056 / 2113 / 3170 px median, fit-canvas scale 0.73 / 0.36 / 0.24).

**What happens.** On retina-2x the frame and all 18 ticks are right (every tick snapped; the gridlines are pixel-aligned by Chart.js at half-integers 76 and 78 px apart, so the snap target itself carries up to 1 device px of quantisation, resid 0.57 px, averaged out by the fit). The error is in the first x decile only (+0.14% at x < 1.2 where the curve climbs steeply; elsewhere within +-0.07%, the same as the 1x chart). There `refine_lines` cannot re-measure: a 4 px line at slope 2 runs past the +-9 px column window and the column keeps the network's estimate, which was made at canvas scale 0.55 (1.8 source px per canvas px). The low-scale end of mpl-val shows the same: marker recall 0.56 at fit scale [0.45, 0.6) against 0.90 at [0.75, 1.0) (simple charts, e2e rows).

**Probe numbers.** See section 9 (base tree on t5-dpr1/2/3, pixel mode and e2e).

## 5. Frames on charts without spines, and what a wrong frame costs

**Where.** mpl-val presets excel, highcharts, news, dash, ft, minimal (the look of Excel, Highcharts, news graphics, dashboards): the frame is more than 5 px off on 43-70% of them (e2e rows, `rows_by.py`), against 13% for plain matplotlib styles and 8% for Plotly; `minimal` (offset spines) has x tick recall 0.415.

**What it costs.** `extract` takes the frame as the ROI for data ink (frame -1 .. +3 canvas px) and `refine_ticks` searches gridlines inside it, so a frame 10 px too small clips the series at the edges and misses the ticks there. mpl-val e2e: line_good_cov 0.565 when the frame is within 2 px (n=102), 0.449 at 2-5 px (n=38), 0.451 beyond 5 px (n=38); x tick recall 0.985 / 0.974 / 0.849.

**Addressed by** 259b09d (tolerant ROI, furniture excluded by class).

## 6. Real charts: what the standard sets do not contain

From `out/t5/probe1.txt` and `probe-dash.txt`:

- **News chart (examples/real/03)**: the six x labels read right (1970 ... 2010, 2021) but the designer placed "2021" one decade-width after 2010, so a linear fit gets 5/6 inliers (2021 is 5 px off at the 3 px tolerance) while a log fit over 1970..2021 takes all 6 (resid 0.99 px) and wins on inlier count. The series: 'Women'/'Men' in series colour and the four printed end values become a 13-point line with 2 markers, a 99-point line and two scatter series of 4 markers (6 series for 2). The log rule is fixed by 259b09d ("log needs a decade").
- **Dashboard crops (01-panel1/2/3)**: corner heat max 0.56 (no axis lines), y ticks snap to the gridlines, the x labels get two rows of tick peaks (12 peaks for 5 labels), '8k' is read as an x tick; calibration within 1-4 px anyway.
- **Three panels in one image (01-multipanel)**: one frame spanning two panels, 15 x labels read, 10 rejected as disagreeing; multi-panel needs a splitter, which no set measures.
- **OWID (data/t5-real/owid-*)**: the y labels carry a unit word ("80 years", "1 billion", "20%"); the reader's charset has no 's' and nothing strips a word, so every y label parses to None and the chart returns nothing. The x end labels are shifted inward by OWID so they do not overflow (RANSAC drops them, fine). A dot at every data point: 98 markers on the line plus a 9-marker scatter ghost.
- **FRED (data/t5-real/fred-*)**: x ticks snap onto recession-band edges within 2 px of a tick (234.4 -> 236.0, 580.7 -> 579.0; resid 1.43 px); y ticks never snap (gridlines of 10 grey levels on tinted paper); y resid 1.11 px from the label bias of section 1.

## 7. Clutter, noise, skew (probe sets, generated from the same seeds)

`probe_t5.py` makes, from the same 100 matplotlib charts (seeds 15,000,000+): `resize` 0.5x and 2x (resampled, as a pasted screenshot), `jpeg` at 50 and 30, `blur` (down-up resample at 0.7 plus sigma 1.0), `dark` (lightness inverted, hue kept), `clutter` (the chart inside a page with text, a toolbar, a sidebar, a second chart, a scrollbar, a cursor), `skew` 1 degree.
Numbers: section 9 when generated and measured.

## 8. The real benchmark, `data/t5-real`

30 charts whose publishers serve the image and the data from the same query (`teams/t5-robust/tools/fetch_real.py`, `p2d/eval_t5real.py`): 12 Our World in Data (D3; 850 x 600; line charts with end labels, unit words in the labels, log options), 16 FRED (its own renderer; 480 x 300 to 1200 x 700; recession bands, legend on top, a dark theme, thin and thick lines, daily and monthly series, two-series charts, log axes), NASA GISS (1130 x 600, two series plus an uncertainty band) and NOAA Mauna Loa (800 x 600, monthly plus trend).
The score is the RMS of the best-matching extracted series against the published numbers as a percentage of the chart's y data span (the axis span is not published; it is 10-30% larger on autoscaled charts), the coverage of the truth's x range, and the count of series found; dates are decimal years, which is what year labels read as.
Numbers: section 9.

## 9. Numbers

Filled in as the runs finish (`out/t5/*.txt`).
