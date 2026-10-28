# t4-markers notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:42 EDT (curator)

Read BRIEF, ASSIGNMENT, README, RESULTS and the code (synth, data, metrics, evaluate, extract, pipeline, losses).
Started the geometry-only baseline (v3, --refine, rows + overlays) on mpl-val 200 and plotly-v1 150 into `out/t4/` (`out/t4/base.sh`).
Wrote `teams/t4-markers/tools/marker_diag.py`: per-marker diagnosis (stage at which each missed marker was lost, what ink each false marker sits on, series purity and fragmentation), with overlays of the worst charts and contact sheets per cause.

Noted from the code before any measurement:
- `extract.extract` drops marker peaks whose embedding label is -1 and scatter clusters with one marker; a marker on a line is kept only if within 4 canvas px of the traced line.
- Marker heat sigma is 1.5 canvas px, peaks are NMS 2 px, so two markers closer than about 3 canvas px cannot both survive; the matching tolerance in `metrics` is max(3 px, 2 canvas px) in source pixels.
- Tolerance of the metric means a marker displaced by less than 3 source px still counts as found, so a "found" marker can still be 0.5 to 1% off on a small plot.

## Wed 28 Oct 2026, 02:05 EDT, brainstormer

Read BRIEF, ASSIGNMENT, README, RESULTS and all of p2d/. Reproduced the geometry-only v3 baseline exactly
(mpl-val 200, --refine): marker recall 0.593 all / 0.845 simple, precision 0.704 / 0.825, median error 0.128% / 0.112%.
Per-chart rows in out/rows-base-geo.json, overlays in out/viz-base/, worst-chart overlays with the marker heat beside them in out/t4-viz/.

First triage (per chart, joined with the GT meta):
- The "all" recall is dominated by four charts with 870 to 1,570 markers at a median nearest-neighbour spacing of about 1 canvas px
  (seeds 9000180, 9000146, 9000026, 9000142: a line+markers series from the "mixed" branch has no cap on the point count).
  These are 31% of all GT markers and cannot be resolved by anything; they are excluded from "simple" by the density rule.
- Large markers fail: recall 0.50 for 12 to 20 canvas px and 0.27 above 20. In those charts the number of predictions is close to
  the number of GT markers but few match within the 3 px tolerance: the markers are detected but their centres are off.
  The heat peak of a big shape is diffuse, refine_markers gives up when the blob leaves its 19 px window (r = 9) and keeps the
  network's estimate for anything not half-turn symmetric ("^", "v", "p", "*"...).
- False positives come in bulk from dashes: 9000079 (dense spiky lines, 361 FP, no markers at all), 9000138 ("--" line
  through a dense oscillation, 183 FP), 9000160 ("-." dash-dot line, about 250 FP), 9000175 (60 FP). The marker head fires
  on dashes and on sharp vertices of jagged lines.
- "^" triangles: 9000122 has 45 GT, 62 predictions, 8 TP: displaced.

## Wed 28 Oct 2026, 02:08 EDT (curator)

- Baseline reproduced in my worktree before any p2d edit (identical to `out/base/v3-pixel.txt`): `out/t4/rows-val.json`, `out/t4/rows-plotly.json`. Per the judge's notice, every later "before" number is measured from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` (my tools take `P2D_ROOT` for that), outputs written into `out/t4/*-v3*`.
- Per-marker diagnosis of mpl-val (`out/t4/diag-val/`): 76% of the 6,415 FNs are overlap (taken 2,031, peak_off 2,176, no_peak 612), 19% no heat, 5% dropped for an embedding label of -1. 54% of the 3,918 FPs are split peaks near true markers, 36% sit on line ink (dashes, spikes); glyphs and legend symbols under 2%. Full tables in the 02:00 mail to the brainstormer.
- The "all" marker numbers are owned by a few charts whose line+markers series have 800 to 6,000 markers at sub-pixel spacing (mpl-val top five charts: 64% of FNs; Plotly chart 500107 alone: 58%).
- Ground-truth finding: matplotlib Agg snaps every marker stamp to integer pixels (lines are not snapped). Drawn centre = floor(markers_px + 1.0) per axis, verified to 0.05 px on 15k isolated markers of every symmetric shape; Plotly's centres are exact. So the matplotlib heat targets carry a +0.5 px bias and a U(-0.5, 0.5) jitter, and mpl-val's marker_err_median (0.11%) is mostly that jitter. `probe_t4` now records the drawn centre as `markers_px` and the exact value position as `markers_data_px` (`meta["marker_centre"] = "drawn"`); `marker_diag` reports the error against both and a capped-cost matching beside the standard one.
- Probe sets generated (seeds 14,000,000+): t4-dense 150, t4-row 150, t4-labels 150, t4-shapes 150, t4-hollow 120, t4-multi 120, t4-lines 100 (`out/t4/gen-probes.sh`). Their baselines (evaluate --refine + diagnosis, frozen tree) are queued in `out/t4/probe-base.sh`; the sets will be regenerated with the drawn-centre GT once that queue is done, and the standard numbers re-measured.
- Lesson: `pgrep -f` with a bracketed pattern still matched my own shell because the heredoc in the same command contained the plain name; a kill then killed the shell. Write scripts with the Write tool and kill by pid from a separate command.

## Wed 28 Oct 2026, 02:31 EDT (curator)

Correction to the 02:08 entry, at the brainstormer's request: `probe_t4` keeps `markers_px` as the exact value position (the scoreboard's convention) and records the drawn centre beside it as `markers_drawn_px`; `marker_diag` reads that field when present, else applies floor(+1) to matplotlib sets. Committed as d21f45b and the follow-up.

## Wed 28 Oct 2026, 02:07 EDT, brainstormer: ranked candidates

Evidence (my triage out/rows-base-geo.json + displacement analysis of out/t4-preds-base-mpl.json; the curator's
per-marker stage breakdown in the mailbox, 02:00): on mpl-val geometry-only, 76% of the 6,415 misses are overlap
(one peak for two markers, peaks merged or shifted by NMS 2 on sigma 1.5), 19% have no heat, 5% are dropped in
decoding (embedding label -1, singletons). Of the 3,918 false positives, 54% are split peaks next to a true marker
(big markers, ropes), 36% sit on line ink (dashes of dashed lines, spikes of noisy lines), under 2% are glyphs or legend
symbols. 1,182 markers (7.5% of all, 31% of those 15 px and larger on the canvas) are found but displaced by more than
the tolerance: the heat peak of a big shape is diffuse and refine_markers gives up when the blob leaves its 19 px window.
Matplotlib's Agg stamps markers at floor(truth) + 1 px per axis (measured, residual 0.001 px; Plotly draws exactly),
so the recorded truth is a mean 0.5 px up-left of the drawn ink; after the centroid refinement the median error on
mpl-val is mostly that offset (0.11% of plot height is about 0.5 px). Triangles: matplotlib's data point is the
bounding-box centre (centroid off by size/6), Plotly's the centroid.

Candidates, ranked by expected scoreboard gain (mpl-val geometry, "all" / "simple"):

1. A second pass at a higher scale on tiles of the plot area for marker peaks (markers 5 to 8 source px apart are
   2 to 4 canvas px apart at the usual placement scale of 0.4 to 0.8, right at the 3 px resolution limit of the heat
   representation). Expected: recall +5 to +10 points all, +3 to +5 simple; precision up with it through fewer split
   peaks on big markers. Cost: 2 to 9 extra network passes per chart. To be validated first (tile_test).
2. Size-adaptive centre on the source pixels (ink-weight map per series colour, connected blobs, series marker size
   from the isolated blobs, mean shift in a window scaled to that size) plus the renderer convention from the image
   (a series whose isolated centroids sit on exact pixel centres is Agg-stamped: data = centroid - 0.5 per axis,
   triangle data point = bbox centre; otherwise centroid). Expected: recovers most of the 1,182 displaced
   (recall +5 to +7, precision +7 to +9 on all), median error 0.128% -> about 0.06%.
3. Vetoes: a peak on a traced line whose blob is no wider than the line's stroke is a dash or a spike; a series whose
   blobs fit no marker template at the series' size is glyphs (real chart 03). Expected: precision +5 to +8 on all
   (36% of FPs), the women/men digits gone.
4. Split peaks merged by the convergence of the mean shift (two peaks on one blob end at one centre); label -1 peaks
   assigned by colour; singletons kept when they pass the template test. Expected: precision +3 to +5, recall +1 to +2.
5. Fine-tune (2k to 4k iterations from v3) with marker targets at the drawn centre, sigma 1.0, NMS 1, and the
   curator's "lines" and "dense" probe kinds as extra training data: sharper peaks, fewer dash false positives.
   Only after 1 to 4 are measured; needs the GPU lock.
6. Not pursued: an instance/offset head for markers (needs a full retrain to pay off); a shape-classification head
   (the shape is measured from the pixels instead).

Going with 2 and 3 first (deterministic, no GPU contention), 1 as soon as the tile test says it pays, then 4, then 5.
