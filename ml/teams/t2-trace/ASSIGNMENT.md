# Team 2, "trace": finding every series and following it to the end

Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace`, branch `team/t2-trace`, seed base 12,000,000, run and data prefix `t2-`.

## Why this area

Even with true tick values (geometry only, v2), 14% of simple line series and 25% of all series are not found at all (`line_found` 0.86 / 0.75), and of the true curves only 75% / 58% of columns are covered within 1% (`line_good_cov_mean`).
A series that is split, that hops to another curve at a crossing, that stops at a dashed gap or an occluding legend, or that is never separated from a same-coloured neighbour is a column of wrong numbers.
The p90 RMS of found lines is 1.2% (simple) and 2.3% (all): the tail is traces that wander.

## Known failure modes

- Crossings and near-parallel runs of different series; two series of the same colour (dashed versus solid); series that touch for long stretches.
- Fragmentation: one true series returned as two or three pieces (`merge_fragments` catches some); the Chart.js `linear-multi` case returns one series split with 45% coverage.
- Hopping: the per-column tracker (`peel_chains`) switching curves; the embedding clustering (`cluster_embeddings`) merging two series or splitting one.
- Dashed and dotted lines; thin lines (1 px); lines under markers; step series; area series (the top edge is the data); series hidden behind the legend box or a text annotation.
- Dense data: more points than pixel columns (the "all" split), where one value per column cannot represent the curve; vertical runs.
- Short series and series that leave the plot area.

## Where to look first

`out/base/v3-pixel.txt` (geometry only) against the truth with `evaluate --refine --viz out/viz --json out/rows.json`, worst `line_cov` rows first.
`extract.extract`, `extract.cluster_embeddings`, `extract.column_runs`, `extract.peel_chains`, `extract.merge_fragments`, `extract.drop_duplicates`, `losses.discriminative`, `data.PlotDataset.targets`.

## Seeds of ideas (not a list to follow; beat it)

- Joint tracking of all K series at once as K vertex-disjoint paths through the column graph (min-cost flow or a joint DP), instead of peeling one chain at a time; crossings then cost nothing.
- A learned direction field: at every data pixel, predict the tangent (or the next-column displacement) of its curve, so the tracker knows where to go through a crossing and across a gap.
- A second pass conditioned on a series: mask the input to one series' colour (or one embedding cluster) and run again, so each series is traced alone; or a small "tracker" network that takes a crop and a seed point and extends the trace.
- Make the training data crueller where it matters: more crossings, same-colour dashed pairs, legend occlusion, thin lines, and weight the loss there.
- Use the legend: the number of series and their colours/dash styles are printed on the chart.
- Represent dense data by an envelope (min and max per column) or a parametric path, not one value per column.
