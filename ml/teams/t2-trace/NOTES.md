# t2-trace notes

Dated entries, newest last. Both agents write here.

## Thu 29 Oct 2026 01:17-01:40 EDT, brainstormer

Round 2 kickoff. Baseline is integration/round-1 at 121ed4d (`runs/t5-chartjs/best.pt` + `runs/ocr1/best.pt` + `--tta shift`).

Verified reproducibility: fresh plotly-v1 measurement on my worktree with unchanged code matches integration numbers byte-for-byte (line_found 0.8252/0.9252, line_rms_median 0.2057/0.1452, calib_y_within_0.5 0.8867).

Target A fix applied in `ml/p2d/extract.py` long-overlap branch (lines 644-654):
- `min_q` raised from 0.3 to 0.4 (REPORT_V1 primary guard against ghost+ghost: both offending plotly simple seeds 500106 and 500111 are 1-3 series charts where a weak ghost cluster of q~0.3-0.4 triggered the overlap merge).
- Added `nov >= 0.5 * min(A.n, B.n)` as a second guard against the "cross-series short overlap" variant.

Both guards are additive: 110 pytest still pass; the transitive-chain test clears 0.501 (just barely).

Partner curator (a9934b30dea16322a) spun up in parallel, agreed on both plan and guard choice. Partner building `t2-ghostpair` probe at seeds >= 12,100,000. Partner noted a pre-existing bug in `evaluate.py` with `--refine --tta shift` (no ocr): `elif a.tta:` branch doesn't set `ex` before `score(meta, ex, ...)`. Using `--oracle-ticks --tta shift` for geometry probes avoids that path.

Queued three measurements under flock (serialised with t3/t4/t5 concurrent runs): plotly-v1, mpl-val, corpus.

## Thu 29 Oct 2026 01:40-01:55 EDT, curator

Verified brainstormer's view: integrated 121ed4d plotly-v1 line_found 0.8252/0.9252 reproduces byte-identical. R1's plotly-simple -0.019 regression is already absorbed by t5 base's cleaner ridge heat; the ghost+ghost merge pattern that drove 500106/500111 is unlikely to recur.

Fixed pre-existing bug `elif a.tta:` branch in `evaluate.py` (commit 355bec7): missing `ex = extract(...)` and refine step, so geometry-only runs with `--refine --tta shift` had thrown `UnboundLocalError`. 110 pytest still pass.

Launched 17-probe measurement batch under flock; serial per probe to avoid thrashing. Each probe ~3-5 min; total ~1 hour contingent on t3/t4/t5 lock contention (15 flock waiters at start). Script at `teams/t2-trace/measure_probes.sh`.

Built `t2-ghostpair` probe set, case index 17 in `p2d/synth/probe_t2.py`. Seeds 12,170,000..12,170,099 (round-2 base). 100 charts: 1-3 series, 3-5 pt strokes at dpi 100-120 (= 4-8 canvas-pixel stroke), presentation-shaped (900-1400 x 400-800 px), smooth shapes, mix of solid/dash/dashdot, plotly-presentation palette shifted into pool. Design in `CASES_R2.md` section 4. Baseline measurement queued.

Deferral trigger agreed with brainstormer: if ghostpair baseline already shows line_found >= 0.90 under the integrated model, there is nothing left for the overlap-merge fix to recover and target A defers. Will send probe result to brainstormer as soon as it lands.
