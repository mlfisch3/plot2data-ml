# Team 3, "precision": the last fraction of a pixel

Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t3-precision`, branch `team/t3-precision`, seed base 13,000,000, run and data prefix `t3-`.

## Why this area

Where everything else works, the numbers are still off by more than the pixels allow.
On the Chart.js corpus the learned pipeline's median error is 0.06 to 0.075% of full scale against 0.037% for the classical engine, and on individual cases it is far worse: `log-log` 0.62% at 67% coverage, `sawtooth-sharp` 0.29%, `narrow-peaks` 0.24%, `linear-single-nogrid` 0.20%, `retina-2x` 0.10% (v2; v1 had 0.055%), `thick-line` 0.056%.
On synthetic charts the median RMS of found lines is 0.19% and the error at turning points 0.33% (simple) and 1.9% (all).
Tick positions are good to about 0.32 px, which alone is 0.08% of a 400 px plot: the tick and frame precision caps everything downstream.

## Known failure modes

- Turning points: a column centroid averages both flanks of a sharp peak; the network's vertex heat is blunt; peaks of one or two columns are clipped.
- Line width: thick lines and anti-aliasing shift the centroid; the paper-to-ink blend model in `refine_lines` assumes a single series colour.
- Ticks: the 0.3 px floor; where there is no tick mark or gridline to snap to, a renderer-specific label offset remains (the `nogrid` case).
- Scale: large screenshots are downscaled to the 768 x 512 canvas before the network sees them; a 1600 px wide chart loses half its resolution; `retina-2x` got worse from v1 to v2.
- Log axes: the error in value space grows with the slope; `log-log` is the worst corpus case.
- The frame: median corner error 1.3 px, p90 14 px; not found on 11% of charts.

## Where to look first

`out/base/v3-corpus.txt` and `out/base/corpus-viz-v3/`, `../ACCURACY.md` for the classical engine's figures and how it got them, `../src/engine/` for its sub-pixel tricks (it beat us on the corpus; what does it do that we do not?).
`extract.refine_peak`, `extract.refine_lines`, `extract.refine_ticks`, `extract.snap_vertices`, `extract.plot_frame`, `data.fit_transform`, `data.PlotDataset.targets` (the heat-map sigmas), `metrics.peak_vertices`.

## Seeds of ideas (not a list to follow; beat it)

- Run the network at native resolution (tiles) or at 2x on the plot area, and fuse; or a second, local network that takes a strip around a traced line and outputs the sub-pixel offset per column.
- At a vertex, fit straight lines to the two flanks and intersect them: the peak can lie between pixel rows and the intersection recovers it (the classical engine does something like this).
- Deconvolve the line: knowing the line width and the anti-aliasing model, fit the ideal line profile per column instead of a centroid.
- Ticks and gridlines are equally spaced: fit one affine map to all of them jointly (and to the frame), so the position error averages down with the number of ticks.
- Measure the label-to-tick offset per chart from the ticks that do have marks, and apply it to those that do not.
- Error in value space on log axes: sample and fit in log space, and report where the slope amplifies error.
