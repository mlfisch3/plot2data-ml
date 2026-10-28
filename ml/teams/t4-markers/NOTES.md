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

## Wed 28 Oct 2026, 16:11 EDT, brainstormer (replacement, Opus 4.7)

Picked up the thread. Predecessor (Fable 5.1 on a21fb6c74947efb61) was killed at the account's 5-hour limit near the start of its last task. State on arrival:
- `ml/p2d/markers.py` committed as af04090 (555 lines): source-pixel ink weight, mixture-of-Gaussians centres with one component per peak, size measurement from isolated blobs plus `size_at` for touching, Agg-snap convention detected by circular statistics on the fractional centres, triangle-apex orientation that transfers the bbox-centre offset to all markers of the series, dashed-line veto on blob elongation and per-marker line-stroke veto on `size_at`, `attach_loose` that re-homes label-minus-one peaks by colour.
- 11 new tests all pass; full suite (47 tests) green.
- Baselines on the standard sets and all seven probe sets measured from the frozen tree (`out/t4/base-*-frozen.txt`, `out/t4/eval-*-v3d.txt`).
- No "after" numbers yet: nobody has run the standard scoreboard with the new code. That is the first thing to do.

Resumed-work plan:
1. Measure `--refine` + geometry on mpl-val 200 and plotly-v1 150 with af04090; compare to the frozen tree.
2. Measure the probe suite (dense, row, labels, shapes, hollow, multi, lines) with af04090.
3. End-to-end numbers (with OCR) on both standard sets.
4. If gain holds, keep going: label-aware veto (text-blob OCR of F6 digits/legend-glyph FPs), small-marker branch (<4 px, where mixture is weakest), split-peak merging on big filled markers, triangle Agg-stamp when `snap_phase` fails on `cen + off` but passes on raw `cen` (double-check the current rule).
5. If a regression shows up on simple, back off the offending veto and iterate.

Pausing for background on the standard sets now.

## Wed 28 Oct 2026, 16:12 EDT (curator, replacement, Opus 4.7)

Took over for the predecessor (Fable 5.1, cut off by the usage limit at ~02:30 EDT). Partner replacement is `a1d4346bed4bd4f04`. Judge is `main`. Usage minder at 50%.

Context recovered from BRIEF, ASSIGNMENT, README, RESULTS, CASES, both mailboxes and the branch log (through af04090). Honouring the probe-GT convention: `markers_px` is the exact value position; `markers_drawn_px` is the drawn centre beside it; `marker_diag` reports both.

State on arrival:
- Baselines complete (frozen tree, v3). Standard: `out/t4/base-val-refine-frozen.txt`, `base-plotly-refine-frozen.txt`, `base-val-e2e-frozen.txt`, `base-plotly-e2e-frozen.txt`. Probe set (regenerated with the drawn-centre GT): `out/t4/eval-<k>-v3d.txt`, `rows-<k>-v3d.json` for `k in {dense, row, labels, shapes, hollow, multi, lines}`. Per-marker diagnosis from the frozen tree: `out/t4/diag-<k>-v3/`. Bias check: `out/t4/bias-v3.{txt,json}`.
- Brainstormer's committed change at `af04090`: `p2d/markers.py` (555 LOC, measures size, ink mixture centres, snap convention, dash veto, loose attach) replaces `extract.refine_markers`. Not yet measured by anyone.
- Untracked: `ml/p2d/zoom.py` (brainstormer's step 1 WIP, higher-scale tile pass), `ml/tests/test_probe_t4.py` (predecessor's invariant test for the probe generator). The former is brainstormer's turf, left alone; the latter is mine, committing now.

Next: launch the probe suite plus the two standard sets from this worktree at branch head on the GPU, tag `step23`, into `out/t4/*-step23*`; while that runs, slice the diagnosis of af04090 by stage and cause to tell real/false markers from "false markers that happened to touch a line" (per the predecessor's `line_dist` field), and update CASES.md with the delta.

## Wed 28 Oct 2026, 16:41 EDT (curator)

- Step23 (`af04090`) per-marker diag done on 6/9 sets (dense, shapes, row, labels, hollow, multi, lines; val/plotly running). Mid-flight mtime realisation: brainstormer edited markers.py at 16:21:17 before committing step24 at `c78db3f`, so labels/hollow/multi/lines/val/plotly actually used step24 behaviour (import happened after the edit for each new process). Dense/shapes/row got clean af04090. Plan: rename the dirty step23 outputs to step24 after the run, then fill dense/shapes/row at step24.
- Standard scoreboard numbers from the brainstormer's `step24.sh`: mpl-val --refine: recall 0.598/0.850 (+0.005/+0.005 vs v3), precision 0.799/0.875 (+0.095/+0.050), err 0.086/0.071 (-33%/-37%). plotly-v1 --refine: recall 0.445/0.783 (-0.020/-0.046 vs v3), precision 0.871/0.903 (+0.073/+0.085), err 0.044/0.027 (-52%/-67%). mpl-val is a clean win on every axis; plotly keeps a simple-recall regression (-4.6 pp), driven by two catastrophic charts (500134, 500021: line+markers series lost ALL markers under step24).
- Guard verification: `size_at` returns 1-3 for `X`, `*`, `.` at every size (empty cardinal arms); confirmed and relayed to brainstormer. Their step24 fix (`len(iso) >= 3 AND size <= stroke + 2`) is correct, recovers ~300 TP on mpl-val.
- Veto verification: `text >= data` sem-TEXT veto rate on real markers is 0.02-0.10% across labels and mpl-val, well below the 3% safety ceiling the brainstormer set; recommended that variant over the broader `non_data >= data` (1.26% on mpl-val). Reserved for step25.
- Tools: `teams/t4-markers/tools/diag_delta.py`, `perchart_delta.py`, `verify_text_veto.py` on branch.

## Wed 28 Oct 2026, 17:25 EDT (curator)

- Step24 fully measured: brainstormer's `eval-*-step24.txt` for val, plotly, dense, row, shapes, labels, hollow (`out/t4/`); my per-marker diag `out/t4/diag-*-step24/` for the same seven sets plus multi, lines (val, plotly, dense/shapes/row diag used step24 behaviour because of mid-flight marker.py edit, so step23 outputs for those four sets are also effectively step24 diagnoses but tagged step23).
- Corpus+real step24: `out/t4/corpus-step24.txt` (series median err 0.067 → 0.079, modest regression; coverage up to 100% on scatter-markers / scatter-halo-colours), `real-step24.txt` (byte-identical to v3).
- Step25 (`e4edf2b`) committed: dash veto scatter-only, iso elongation filter, sem[TEXT] veto.
- step25.sh died silently 12+ min into val eval (GPU 100% + dxg driver errors in dmesg + load 33 earlier). Pinged brainstormer; eval-val-step25.txt stayed 0 bytes.
- Killed my dense step24 fill at 40/150 charts (GPU thrashing). The eval numbers from brainstormer cover dense/shapes/row at step24; the step23 (= af04090) per-marker diag is a reasonable baseline-of-record for those sets since the gap is a before/after of the step24 fixes.
