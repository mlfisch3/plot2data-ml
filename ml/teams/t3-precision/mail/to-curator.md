# Messages to the curator of t3-precision

Append dated entries below.

## Wed 28 Oct 2026, 01:40 EDT from brainstormer

First findings after reading everything:

1. The standard e2e commands (#1, #2) run `p2d.evaluate` without `--refine`, and `evaluate.main` passes `refine=a.refine` into `pipeline.run`, so the scoreboard's end-to-end numbers on mpl-val and Plotly are measured with no `refine_lines`, no `refine_ticks` and no `refine_markers`. `eval_corpus` and `eval_real` call `run()` with its default `refine=True`. I am measuring the first 60 mpl-val charts both ways (`out/t3/base60-e2e.txt` vs `out/t3/base60-e2e-refine.txt`), plus `--oracle-ticks --refine` and geometry with and without refine. If refinement helps end to end, I intend to make the e2e path refine by default (the pipeline's real behaviour) and report the harness change separately from my own gains, so the judge can see both.
2. On the corpus overlays: sawtooth-sharp's trace stops visibly short of every apex (mitred joins overshoot the vertex, and our trace stops below even the vertex); narrow-peaks (round joins) looks right at the tips; log-log finds a stray second series (the legend text) and reads only 68% coverage, which smells like an x-calibration problem more than a precision one, I will check.

What I am doing in the next hour: `teams/t3-precision/scripts/colres.py`, a per-column residual analysis on mpl-val (refined centroid vs network fallback, by slope, line width, canvas scale, distance to a vertex) and a per-peak analysis (signed shortfall vs vertex heat, angle, line width). Then the ranked list of ideas in NOTES.md.

What I want from you, in order:
- Probe set A, sharp peaks: polylines with vertices of prominence 5 to 50% of plot height, angles 10 to 90 degrees, line widths 1 to 5 px, both round and mitred joins (matplotlib `solid_joinstyle`), source widths 400 to 1800 px, with the per-vertex truth. One series per chart, nothing else hard.
- Probe set B, scale: the same smooth curves rendered at 500, 900, 1400 and 1800 px wide, thin (1 px) and normal (2 px) lines, so the loss from the 768 x 512 canvas is isolated.
- Probe set C, ticks and frame without marks: label-only axes (no tick marks, no grid) in a few house styles, so the label-to-tick offset bias is measurable per renderer.
- From the mpl-val worst cases: which are precision failures (trace on the right curve but off by a fraction of a pixel to a few pixels) and which are tracing failures (wrong curve, gaps)? Only the first kind is ours.
Paths: my outputs go under `ml/out/t3/`; scripts under `ml/teams/t3-precision/scripts/`.

## Wed 28 Oct 2026, 01:51 EDT from brainstormer: the error budget

`out/t3/colres.txt` (per-column residuals on 60 mpl-val charts, geometry with refine). Simple subset: 47% of columns keep the network's estimate (fallback: window too small for steep runs, vertex-heat gate, |yr - yc| gate). Refined columns: median |r| 0.027 px, 1.4% of the squared error. Fallback columns: 98.6%. |slope| > 3: 26% of columns, 90% of the squared error. Within 4 px of a vertex: 72%. Unsnapped peaks (dense, flanks < 3 px): median shortfall 8.6 px; snapped: 0.77 px. The ranked list is in NOTES.md. I am rewriting `refine_lines` now (full-column runs, classical flat/steep/turn blend with top + t/2 at extrema, flank fit and intersection at vertices). Please make probe A include dense spikes with flanks under 3 px (the retail-sales shape, 300 to 2500 points) as well as sparse vertices, and both joins. Also, in your diag, if cheap: `refine_ticks` on/off per tick (I have `scripts/tickdiag.py` running for that too; compare when both land).
