# Team 4, "markers": every drawn marker, once, at its centre

Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t4-markers`, branch `team/t4-markers`, seed base 14,000,000, run and data prefix `t4-`.

## Why this area

A marker series must return exactly one point per drawn marker.
End to end on the matplotlib validation set, marker recall is 66% and precision 75% on simple charts, 51% / 68% on all (v2); geometry only it is 83% / 79%.
On the real women/men chart the printed end values (`46`, `36`) come back as markers.
On the Chart.js `scatter-halo-colours` case the error is 0.08 to 0.10% against the classical engine's 0.02%.
A third of markers missing, a quarter of returned markers spurious, is not an extraction of a scatter plot.

## Known failure modes

- Overlapping and touching markers (dense scatters, marker rows along a line); markers on a line+markers series; markers of several series in one cloud.
- Marker heat peaks that merge, split, or sit on text glyphs, legend symbols, digits and tick marks; numbers printed on the chart taken as markers.
- Asymmetric markers (triangles, stars): libraries disagree on where the data point is; the current rule keeps the network's estimate for anything not symmetric under a half turn.
- Hollow markers, markers with halos (Chart.js), small markers (2 to 3 px), markers over gridlines.
- Clustering markers into series: by colour (`merge_by_colour`) and by the embedding; shape is not used.

## Where to look first

`evaluate --refine --viz out/viz --json out/rows.json`, worst `marker_recall` / `marker_precision` rows; `out/base/real-v3/03-*`; `out/base/corpus-viz-v3/scatter-*`.
`extract.peaks`, `extract.extract` (the marker branch), `extract.refine_markers`, `extract.merge_by_colour`, `data.PlotDataset.targets` (`points_heat`, the marker sigma), `synth/mpl_render.py` (marker styles, direct labels at `prob 0.04`).

## Seeds of ideas (not a list to follow; beat it)

- Predict marker size and shape (a regression and a classification head, CenterNet style), then fit the exact shape template to the source pixels for the centre; count overlapping markers from the blob area.
- An instance head for markers: per-pixel offset to the marker centre, voted; splits touching markers that one heat peak merges.
- Train the network to tell marker from glyph: far more direct labels, annotations, data labels and legend symbols in the training data, and a hard-negative weighting.
- Marker series membership from colour, shape and embedding together; a legend-swatch match.
- For line+markers series, trace the line and then look for the markers along it at the sampled data positions.
