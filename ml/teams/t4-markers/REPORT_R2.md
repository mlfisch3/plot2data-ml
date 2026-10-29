# t4-markers round 2

Submission branch: `team/t4-markers-r2`. Base: `integration/round-1` at `121ed4d`. Baseline pytest: 110.

Round 2 principle: diminishing returns.
The round-1 integration is already a strict win over the frozen baseline on every scoreboard (`INTEGRATION-REPORT.md`): mpl-val `marker_recall` 0.613 all / 0.809 simple, `marker_precision` 0.736 / 0.845; plotly 0.403 / 0.824 and 0.795 / 0.912; corpus worst case 61.222% -> 0.214%.
The round-2 angle is the biggest surviving gap after that, measured against those numbers.

## Claim

Add a y-snap-to-line step to `measure_series` for line+markers series: every centre whose y disagrees with the traced line's y at its x by less than half the marker is replaced by the line's y.
On line+markers series the trace is a sub-pixel ridge averaged along the line, which is a stronger anchor than one marker's heat peak.
Scatter and series without a traced line are untouched (gate on `line_px is not None and len(line_px) >= 3`, the same gate the dash veto already uses).
Expected to close the residual y-error on line+markers series without touching the x-axis estimates, with a bounded cost of nothing on scatter.

## Diagnosis

See `CASES_R2.md` for the full round-2 case catalogue.
Short summary of where the integrated pipeline stands after round 1:

### What round-1 integration unlocked (vs step25 standalone)

The integrated model (`runs/t5-chartjs/best.pt` + `--tta shift` + `--refine` + markers.py step25) matches or beats the step25 isolated numbers from a different direction:

- **mpl-val**: integrated has slightly higher recall `all` (+0.8pp vs step25 isolated), slightly lower precision; simple recall drops because t5's native-res resolves peaks step25 could not and reshuffles which markers end up labelled.
- **plotly**: integrated has lower all-recall and all-precision but comparable simple numbers; the integration's gain is concentrated in end-to-end line/peak metrics, not geometry.
- **End-to-end scoreboards** (what the brief weights): integrated beats step25 standalone on every line / peak metric (`line_rms_median_pct` -11% / -9% on plotly simple, -5% / -10% on mpl-val simple), beats on `frame_found` and `calib_x/y`.
  The whole-integration win is driven by t5's native-res + Chart.js training and t1's structured axis read, not by markers alone.

### What is left after the integration

Baselines against the INTEGRATED model (`runs/t5-chartjs/best.pt` + `--tta shift` + `--refine`), one probe set per column.
All numbers from the current branch at HEAD:

<!-- SEE: eval-<set>-int.txt for the per-set numbers.
     Will be filled in once the suite completes. -->

- **Line+markers y drift (NEW round-2 angle)**: markers drawn on a line, whose network heat peak lands away from the line's path.
  The line tracer already measures the line's y to ~0.2% RMS, which is a tighter y anchor than any one marker's heat peak.
  This is the F1/F3 interaction: not a rope (where the markers merge in x) nor a big marker (where the heat is diffuse), but the ordinary line+markers case.
  Not addressed in round-1.
- **Hollow / small markers at low DPR**: `marker_err_median_pct` on the hollow probe is still 0.096% at step25 (down from v3's 0.138%), bulk of the remaining error on open rings and thin strokes where ink-weight > 0.5 does not form one component.
  Angle A for a future round; sub-1pt gain today.
- **Overlap in x (ropes)**: 76% of mpl-val FNs.
  The zoom pass (`ml/p2d/zoom.py`) is written but not integrated.
  Round-3 lever if time allows.
- **Triangles in no-iso overlap**: round-1's triangle convention correction only runs when there are enough isolated blobs.
  In packed-triangle scatter the fallback is the raw heat peak. Marginal.
- **Dashes/spikes as markers (lines probe)**: step25 drops ~88 of the v3 spurious markers on the lines probe (-17%).
  Reaching 0 is still open; the gain is bounded by what the dash veto can safely do without killing dashed line+markers.

### Why angle D (y-snap to line)

- **Hits an unaddressed failure directly**: no round-1 change touched line+markers y.
  The round-1 pipeline measures the marker's y from its ink centroid (symmetric) or raw heat peak (asymmetric / no-iso); neither uses the line as a prior.
- **Clean gate**: `line_px is not None and len(line_px) >= 3` on the pure measure_series call site, same gate the step25 dash veto already uses to tell line+markers from scatter.
  Pure scatter and lines without a traced path pass through untouched.
- **Bounded cost**: the y value only moves if it is within `max(1.5, 0.6 * size)` of the line's y at that x; an outlier marker plotted beside the line is not pulled onto it.
- **Grounded in a measured anchor**: `line_rms_median_pct` on mpl-val is 0.21% (plotly 0.14%).
  The marker centre's y, after step25, is at a worse anchor than that on most line+markers charts.
- **Deferred alternatives were worse**: filled vs hollow (A) is 0.03pp sub-1pt; shape class fit (B) is substantial code for a modest residual gain on no-iso overlap; hollow halos (C) is Chart.js-narrow sub-1pt; shape-aware clustering (E) is a bigger surgery than D.

## Probe set

`data/t4r2-linemk/` - 216 charts at seeds 14,100,000 to 14,100,215, generated by the new `linemk` kind in `p2d/synth/probe_t4.py`.

### What it provokes

Every chart is a line+markers series.
The markers sit exactly on the drawn line.
Varied dimensions, recorded in `meta["probe"]`:

| dimension | levels | range |
| --- | --- | --- |
| `spacing_rel` | 6 levels | 0.3, 0.5, 0.7, 1.0, 1.5, 2.5 marker diameters along x |
| `ms_pt` -> `ms_px` | 4 levels | 2 pt (2.5-4 px), 3 pt (3-5 px), 5 pt (5-10 px), 8 pt (8-16 px) at dpi 72-144 |
| `line_lw_pt` | 4 levels | 0.8, 1.5, 2.5, 4.0 pt (1 px to 8 px at dpi 72-144) |
| `dashed` | 2 levels | solid 60%, dashed 40% (random choice between "--", "-.", ":") |
| `n_series` | 2 levels | 1 (p = 2/3) or 2 (p = 1/3) |
| `shape` | 9 shapes | o, s, D, ^, v, *, x, P, + |
| curve | varied | random S.shape producing flat spans and steep spans in the same chart |

For every chart `meta["probe"]` records:
`kind="linemk", spacing_rel, ms_px, n_series, line_lw_pt, dashed, shape, n, nn_px_median, nn_rel_median, n_markers`.

Ground truth is `markers_px` (exact value position) with `markers_drawn_px` beside it (drawn centre, matplotlib's integer stamp).
The scoreboard matches against `markers_px`, same as all other t4-* probes.

Expected failure modes the set should surface:

- **Dense spacing + flat span**: markers merge in x, heat peaks sit along the ridge, y is well-centred (the fix should barely help here, since y is already close to the line).
- **Sparse spacing + sharp curve**: y heat may lag behind the drawn centre at a sharp bend; the line tracer follows the curve well because the line is thick, so y-snap buys the gain.
- **Thick dashed line + markers**: the dash veto has to let the markers through (step25 gate: skip veto on line+markers), while the y-snap replaces the drifted y.
  The hard case for the fix.
- **Hollow markers on thick line**: the open ring plus line ink gives a diffuse heat that step25 falls back to raw peak for.
  The snap should pull y onto the line cleanly where present.

### Baseline numbers (integrated, no snap)

Measured with `runs/t5-chartjs/best.pt` + `--tta shift` + `--refine`, markers.py at `7421076` (step25 integrated).
Command:

```
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock nice -n 19 \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t4r2-linemk \
  --limit 216 --refine --tta shift --json out/t4r2/rows-linemk-int.json \
  > out/t4r2/eval-linemk-int.txt 2>&1
```

<!-- Numbers filled in when eval-linemk-int.txt lands under out/t4r2/. -->

### Expected numbers after the patch

With the brainstormer's y-snap-to-line patch (currently stashed as `t4r2-brainstormer: line-snap patch, hold for baseline`), applied only inside `measure_series` for line+markers series:

<!-- Numbers filled in when eval-linemk-snap.txt lands under out/t4r2/. -->

The gain should concentrate on `marker_err_median_pct` and `peak_err` at marker y; recall and precision should be unchanged (the fix moves centres, it does not add or drop markers).

## Verification commands

- Baseline suite: `teams/t4-markers/tools/probe_suite_r2.sh int --no-diag`
- linemk eval: `python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/t4r2-linemk --limit 216 --refine --tta shift --json out/t4r2/rows-linemk-int.json`
- Pytest: `python -m pytest -q` (expect 112 after the brainstormer's two new line-snap tests land; 110 at the stashed baseline).
