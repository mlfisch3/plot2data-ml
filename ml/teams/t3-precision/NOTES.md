# t3-precision notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:40 EDT (brainstormer)

Read BRIEF, ASSIGNMENT, README, RESULTS, all of p2d/, ACCURACY.md, the classical engine's trace.ts / ticks.ts / calibration.ts / frame.ts.

Harness finding: scoreboard commands #1 and #2 (`evaluate --ocr`) run `pipeline.run` with `refine=False` (the `--refine` flag is not in those commands), so no source-pixel refinement of lines, ticks or markers enters the end-to-end numbers on mpl-val and Plotly; corpus and real use `refine=True`. Measuring both ways on 60 charts (`out/t3/base-quick.sh`).

What the classical engine does for sub-pixel accuracy that we do not:
- Column value: alpha-weighted centroid where the column holds one flat stroke; where the ink span exceeds ~1.25 stroke widths it blends towards an explicit turning-point rule: at a local maximum the value is `topmost ink + t/2`, at a minimum `bottommost ink - t/2`, on a monotone steep run the middle of the span. `t` is measured as ink area / path length. Mitred corners (Chart.js) are detected by cross-section (a sliver half a stroke below the tip) and descended until the ink is a full stroke wide.
- Sub-pixel outer edges from the coverage of the edge rows (`top = lo + 0.5 - alpha_lo`).
- Ticks: ink-mass centroid of the tick mark including the antialiased columns either side; label-only axes use label blob centres kept on a regular grid (`keepRegular`).
- Frame: ink-weighted centre of the spine band across its rows.
- Calibration: least squares over all labelled ticks with pairwise RANSAC and leave-one-out; the same idea as ours.
Our pipeline: ridge centroid on the heat map (canvas resolution, sigma 1 px), then `refine_lines` re-measures a blend-weighted centroid per source column, but keeps the network estimate at any column whose 3x3 canvas neighbourhood has vertex heat > 0.3, whenever the ink run reaches the window edge, and whenever the centroid moves more than max(1.5, 1/s) px. Vertices come from the vertex heat peak (sigma 1.5 canvas px) via `snap_vertices`, never measured on the source pixels.

Next: per-column residual analysis (`scripts/colres.py`) to see which columns carry the RMS, then the ranked list.

## Wed 28 Oct 2026, 01:49 EDT (curator)

Read everything; the worktree reproduces the judge's v3 geometry baseline exactly (`out/t3/base-refine.txt`: simple RMS 0.1886%, peak 0.3065%, frame p90 13.2 px, ticks 0.29 / 0.32 px).
Built the diagnostic collector `teams/t3-precision/scripts/diag.py` (per column: raw and refined error, slope, line width, scale, gridline/axis/other-series distance, vertex distance, ink run height; per peak: signed inward error raw and refined, angle, widths, vertex heat; per tick: raw and snapped error with what is drawn at the tick; per frame: signed edge errors with spine visibility from the label map), the summariser `diag_report.py` and `probe_report.py`.
Probe generator `p2d/synth/probe_t3.py`, seven families with a seed base each (peaks 13.0M, scale 13.1M, ticks 13.2M, width 13.3M, log 13.4M, grid 13.5M, frame 13.6M); ground truth overlays checked at 8x on peak tips and tick anchors.
Building `data/t3-{peaks,scale,ticks,width,log,grid,frame}` (240 / 128 / 144 / 96 / 48 / 48 / 80 charts); diag runs on mpl-val, plotly-v1 and the probes queued on the GPU one at a time.
First finding from the brainstormer's 60-chart runs: on the same 60 charts the simple-chart line RMS is 0.1464% without `refine_lines` and 0.1595% with it, and marker error 0.077% vs 0.095% with `refine_markers`; the source-pixel refinement is a net loss on simple charts. The per-column records will say on which columns.

## Wed 28 Oct 2026, 01:51 EDT (brainstormer): the error budget and the ranked list

Baselines on the first 60 of mpl-val (`out/t3/base60-*.txt`), simple subset (35 charts, 34 line series):

| run | line_found | good_cov | line_rms_median | peak_err_median | calib x/y within 0.5% |
| --- | --- | --- | --- | --- | --- |
| geometry, no refine | 0.91 | 0.83 | 0.146% | 0.299% | - |
| geometry, `--refine` (scoreboard #5) | 0.91 | 0.82 | 0.160% | 0.298% | - |
| oracle ticks, `--refine` | 0.74 | 0.62 | 0.160% | 0.310% | 0.97 / 0.92 |
| e2e `--ocr`, no refine (scoreboard #1 as run) | 0.62 | 0.53 | 0.273% | 0.197% | 0.90 / 0.88 |
| e2e `--ocr --refine` | 0.59 | 0.51 | 0.340% | 0.235% | 0.90 / 0.90 |

Two surprises: `refine_lines` does not lower the median RMS (0.146 -> 0.160), and turning refinement on end to end makes the line RMS worse (0.27 -> 0.34; `refine_ticks` moves ticks both ways, see `out/t3/tickdiag.txt` when it lands).

Per-column residuals (`scripts/colres.py`, `out/t3/colres.txt`, 60 charts, geometry with refine), simple subset, 26,519 columns:

- 47% of columns keep the network estimate (fallback). Refined columns: median |r| 0.027 px, p90 0.15 px, 1.4% of the squared error. Fallback columns: median |r| 0.52 px, p90 5.8 px, 98.6% of the squared error.
- |slope| > 3 px/px: 26.5% of columns, 74% fallback, 90% of the squared error. The window of `refine_lines` (+-7 to +-10 rows) cannot hold a steep run, so steep columns go back to the canvas-resolution ridge.
- Within 1.5 px of a drawn vertex: 9% of columns, 53% of the squared error; 1.5 to 4 px: 19%; 4 to 10 px: 22%. The vertex-heat gate (3x3 canvas window > 0.3) fires on 15.5% of columns and those hold 44% of the squared error.
- Line width and canvas scale barely matter once the fallback is accounted for (refined columns are unbiased: mean r -0.001 px).
- Peaks (229 with prominence >= 5%): snapped by the vertex head 66%, median |err| 0.15%, median shortfall +0.77 px; not snapped 34%, median |err| 1.16%, shortfall +8.6 px, almost all with flanks shorter than 3 px (dense data).

So the error is not sub-pixel noise at all: it is the columns the refinement declines to measure. The refined centroid is good to a fortieth of a pixel.

Ranked candidates (expected gain on the scoreboard):

1. **Measure every column on the source pixels, vertices included** (rewrite `refine_lines`): blend-weight map over the whole band, full-column runs (no window), run selected by distance to the network estimate with a span check for merged runs; stroke width `t` from ink area over path length; the classical flat/steep/turn blend per column (centroid where the span is about `t`, `top + t/2` at a maximum, `bottom - t/2` at a minimum, mitre descent by cross-section); at vertices with straight flanks, fit the two flanks and intersect, and give the join columns the polyline's own values. Expected: simple line_rms_median 0.16% -> about 0.06%; peak_err_median simple 0.30% -> about 0.1%, all 1.8% -> about 0.8%; corpus sawtooth 0.27% -> under 0.1%, narrow-peaks and thick-line down; the same code runs on Plotly and Chart.js, so it is general.
2. **Ticks: snap only where it helps, and learn the label offset per chart** (`refine_ticks`): accept a snap only when the line found is the same for most ticks of the axis (a consistent offset from the network's positions), fall back to the network otherwise; then fit the ticks jointly (equal spacing) and transfer the measured offset to label-only ticks. Expected: tick error median 0.3 -> 0.15 px, calib within 0.5% +2 to 4 points, e2e line_rms down by the calibration share (0.27 -> about 0.22%). Needs the tick diagnostics first.
3. **Frame on the source pixels**: snap each edge to the spine or outermost gridline, with the tick anchors as a consistency check; p90 of 14 to 21 px is wrong frames, not imprecise ones. Expected: frame median 1.4 -> 0.4 px; indirect gains in coverage (the ROI clips series) and tick snapping.
4. **Harness**: once 1 and 2 are in, make the e2e path of `evaluate` refine by default so #1 and #2 measure the pipeline as shipped; report the harness change separately.
5. Native-resolution tiles for large images: deferred; the per-column data says the canvas scale is not where the error is once columns are measured at source resolution.
6. Dash gaps: interpolate across short gaps instead of the network estimate; small.

Going after 1 first, then 2, then 3.

## Wed 28 Oct 2026, 02:00 EDT (curator)

Diagnosis on 200 mpl-val charts written to the mailbox and CASES.md sections 1 to 4 (lines, peaks, ticks, frame).
Provenance: `out/t3/diag-base.pkl` was written 01:54:14, the first live edit to `p2d/extract.py` was 01:55:44, and the plotly-v1 collection started 01:54:18 (module imported before the edit); both are clean baselines.
From now on every baseline run imports p2d from the frozen tree (`P2D_ROOT=/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml`), supported by `scripts/diag.py` and `scripts/corpus_diag.py`; the queued probe-set and corpus runs were stopped (own pids only, matched on this team's file names) and re-queued that way.
