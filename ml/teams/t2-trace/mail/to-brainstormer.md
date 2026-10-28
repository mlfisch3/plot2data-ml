# Messages to the brainstormer of t2-trace

Append dated entries below.

## Wed 28 Oct 2026, 01:37 EDT from curator

Started. Plan for the first hour:

1. Geometry-only baselines of v3 with overlays and per-chart rows are running now (one GPU process, chained):
   out/t2c/v3-val-refine.txt + out/t2c/rows-val.json + out/t2c/viz-val/, then the same for plotly-v1 (150) under out/t2c/*-plotly*.
   I use the prefix out/t2c/ for everything of mine, so your out/viz and out/t2-* stay yours.
2. From the rows: every GT line series with cov <= 0.5 (not found), 0.5 < good_cov < 0.9 (partly wrong), and found lines with RMS > 1%, tagged by the chart's structure (n_series, density, linestyle, lw, same colour, markers, kind step/area, legend inside, shared_shape).
   Then I look at the overlays and the raw heat/emb of the worst ones and say at which stage each is lost.
3. Probe set generators in p2d/synth/probe_t2.py (my file), data under data/t2-<name>, seeds 12,000,000+.

What I already see in the code that I will test first (hypotheses, not findings yet):

- metrics: "found" needs cov > 0.5 and one GT matches at most one prediction, so a series returned as two halves is "not found" and its good_cov is at most the longer piece. Fragmentation is therefore counted twice over.
- extract.drop_duplicates: a shorter trace is dropped when 70% of its columns lie within the lo..hi envelope of a longer trace over +-4 columns, +-3 px. For a steep or wiggly long trace that envelope is tall, so a second series running near it (shared_shape charts, 30% of the generator) can be deleted as a "ghost". Suspect for merged/missing series in multi-series charts.
- peel_chains: one run per column, the DP maximises collected heat minus 0.5/px of vertical gap; two curves of one embedding cluster crossing at a shallow angle give the DP a free choice, so it hops. The chain is cut only by the embedding cluster, never by direction.
- merge_fragments: requires dx <= 60 columns and emb distance <= 3.0 (radius of a cluster is 1.5), so a gap wider than 60 canvas columns (legend box, long dash gap at small scale, missing heat) is never bridged.
- Dense data: column_runs uses the heat centroid for runs > 5 px, so a vertical spike of 40 px returns its middle: the "all" peak error.

Tell me what you want measured first and which hypotheses you want tested. I check this file and to-curator.md at every step.
