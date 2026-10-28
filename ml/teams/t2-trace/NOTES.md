# t2-trace notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:37 EDT curator

Read BRIEF, ASSIGNMENT, README, RESULTS and p2d/ (extract, metrics, evaluate, data, synth, losses, model, train, pipeline).
Launched the v3 geometry-only baselines with overlays and rows: out/t2c/baseline.sh (mpl-val 200, then plotly-v1 150).
Opening note to the brainstormer in mail/to-brainstormer.md with the first code-level hypotheses (fragmentation counted twice by the metric, drop_duplicates envelope, DP hopping, merge gap limit of 60 columns, dense spikes).

## Wed 28 Oct 2026, 01:44 EDT brainstormer

Read everything. Ran the geometry-only baseline on 60 charts (out/t2-base60-pixel.txt, out/rows.json, out/viz) and wrote two diagnostics:
teams/t2-trace/tools/diag.py (stage attribution per GT line series: heat ridge present, cluster assigned, chain, merged, final) and
teams/t2-trace/tools/embstats.py (embedding statistics along true paths; oracle-cluster upper bound).

Stage attribution over the 133 line series of the first 60 mpl-val charts (fraction of true columns kept at each stage, 2 px tolerance):
heat 0.994 -> cluster 0.922 -> chains 0.764 -> merged 0.763 -> final 0.684.
The network's ridge is almost never missing. The loss is in decoding: global mean-shift clusters (radius 1.5, cap 16) fragment a series
into 5-15 clusters (purity of the dominant cluster 0.2-0.8 on multi-series charts), the per-cluster chains are short, merge_fragments does not
rejoin them, drop_duplicates/min_cols kills the pieces.

Embedding statistics (same 60 charts): within-series distance to the series mean median 0.77, p90 2.45, 22% of ridge pixels beyond the 1.5
cluster radius; adjacent-column distance median 0.24, p90 1.15 (locally consistent); nearest other series mean distance median 5.4, p10 2.6.
Oracle clusters (GT instance map) with the unchanged peel_chains: coverage 0.86, found 0.91 (vs 0.70 / 0.79 now on the same 60 charts).

Decision: replace "cluster globally, then chain within each cluster" by one tracker over the whole ridge graph, with the embedding used as a
local link cost (hard cutoff plus soft penalty between consecutive runs), runs split where the embedding jumps inside a column (crossings of
different colours), vectorised DP per column, then fragment joining as before. Expected: geometry-only line_cov_mean +0.1 to +0.15 (all),
line_found +0.08 to +0.12, and the same gain carried through to the end-to-end numbers for the charts whose calibration succeeds.

## Wed 28 Oct 2026, 01:51 EDT curator

Baselines done: out/t2c/v3-val-refine.txt (matches out/base/v3-pixel.txt exactly) and out/t2c/v3-plotly-refine.txt (found 0.861 all / 0.972 simple).
Per-series tag tables: out/t2c/analyze-val.txt, analyze-plotly.txt (tools/analyze_rows.py). Lost rate 7% with no crossing vs 37% with 10+ crossings; 53% under 1.2 px; 41% under 250 px plot height; 54% of area series; 39% dotted.
Staged inspection over all 200 mpl-val charts (tools/inspect_stages.py, composites in out/t2c/inspect-val/): the heat is present on the curve in 458/461 series; the losses are decoding. The most common lost pattern is a series cut into 2-3 long pieces at a cluster change, both kept, never joined by merge_fragments (9000080, 9000108, 9000041, 9000156, 9000175, 9000162). A first run mislabelled kept pieces as marker-row (a matching bug under --refine); fixed, re-run queued with the reasons each junction was refused (dx, overlap, y gap, embedding distance).
Probe generator p2d/synth/probe_t2.py with 13 cases; t2-cross, t2-samecolour, t2-parallel built (100 each), the other ten building. CASES.md drafted.
