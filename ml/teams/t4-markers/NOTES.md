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
