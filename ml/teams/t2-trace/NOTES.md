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

## Wed 28 Oct 2026, 01:58 EDT curator

Measurement protocol, after a scare: the brainstormer edits p2d/extract.py live in the shared worktree, and a baseline run that starts after an edit imports the new code (my t2-samecolour baseline did, and was discarded).
Baselines now run from a frozen copy of p2d at the baseline commit 6b313e9, out/t2c/base-src (cwd there, or P2D_SRC=... for the tools in teams/t2-trace/tools); "after" numbers run from the live tree with out/t2c/t2c-measure-live.sh <tag>, which records the commit and a snapshot of extract.py next to the numbers.
Queue scripts carry the team name (out/t2c/t2c-*.sh); kills are by pid after pgrep, never by a generic pattern.
Cross probe baseline (valid, imported before the edit): found 0.827, good cov 0.714, rms median 0.11%, rms p90 17.2%: 66 of 248 found series have rms > 5%, the hop signature; 1.59 lines returned per true series.

## Wed 28 Oct 2026, 16:09 EDT curator

Replacement. Identity: Opus 4.7 at xhigh, fresh quota, Wed 28 Oct 2026 16:xx EDT. The predecessor a3fb40d310830ed59 (Fable 5.1 xhigh, 02:00-02:30 EDT) is terminated along with its brainstormer partner; a new brainstormer is being spawned by the main session.

Salvage: ml/teams/t2-trace/salvage/a3fb40d310830ed59-excerpt.md (last narration + tool prefixes from the predecessor's JSONL).

State I inherited:
- Last team commit b980834 at 02:11 EDT (markers + wide probes, samecolour baseline).
- All three queued scripts (t2c-queue-frozen, -frozen2, -diag) completed on their own at 04:19-04:29 EDT. Frozen baselines on 17 probe sets (val, plotly, cross, samecolour, parallel, steep, dotted, thin, small, dense, legend, area, step, clipped, multi, markers, wide) with viz/, rows-*.json, series-*.csv for the two standard sets; diag-probes.txt gives the heat/cluster/chain/merged/final attribution per probe set.
- inspect-val.txt + inspect-val.json for 200 mpl-val charts; verdict counts in inspect-val.txt tail (ok 125 / wander 95 / emb-split 84 / hop 65 / fragment 52 / chain-gap 18 / emb-merge 8 / dropped:dup 5 / dropped:marker-row 4 / heat 3 / other 1 / dropped:faint 1).
- Diag probes (chain stage big losses): dense 0.187, parallel 0.849, clipped 0.711, multi 0.664; final stage big drops: parallel 0.849->0.672, multi 0.663->0.580, area 0.743->0.640, cross 0.957->0.913.
- The brainstormer's uncommitted live-tree p2d/ changes (extract.py +467 lines rewrite from cluster-then-chain to chain-through-whole-plot with embedding as link cost; data.py +47, model.py +27 adding a 'dir' head, losses.py +13, train.py +4, evaluate.py +3). None measured on the probe set or scoreboard yet.
- My tools (teams/t2-trace/tools/, 10 scripts): analyze_rows.py, diag.py, embcheck.py, embstats.py, inspect_stages.py, summarize_inspect.py, hops.py, joinstats.py, sweep.py, whystop.py. summarize_inspect, hops, joinstats, sweep, whystop are not yet committed; whystop/joinstats/sweep expect the new TRACE API in extract.py.

What was in flight at termination: nothing active (all queues done); the predecessor had stated "the monitor will notify me as each lands, and nothing else is actionable until then".

Plan:
1. Run summarize_inspect.py on inspect-val.json + rows-val.json so the predecessor's verdict counts also split simple vs all.
2. Commit the stable new tools (analyze_rows.py, inspect_stages.py, embcheck.py, summarize_inspect.py, diag.py, embstats.py) and the salvage. Keep whystop/joinstats/sweep/hops uncommitted until I confirm they fit the live decoder or revert them.
3. Wait for the new brainstormer's id from main, then read mail/to-curator for the next request. Private backlog meanwhile: a shallow-crossing probe (angle under 15 degrees) to isolate hop separately from near-parallel, and a staged inspection of the live-tree decoder on mpl-val once the brainstormer declares a candidate frozen.
4. When the brainstormer publishes a "measure this" tag, run t2c-measure-live.sh with it; before/after goes in the report.

## Wed 28 Oct 2026, 16:11 EDT brainstormer (replacement)

Identity: Opus 4.7 at xhigh effort; the predecessor was Fable 5.1, agent id a1cf484d2a4590c35, cut off by usage limits before testing its code.

Salvaged state: the committed branch holds the probe generator (p2d/synth/probe_t2.py, 15 cases built), the frozen-baseline protocol and the diagnostic tools; CASES.md and NOTES.md are current. All of ml/p2d/extract.py (467-line diff), ml/p2d/data.py (direction targets), ml/p2d/model.py (dir head), ml/p2d/losses.py, ml/p2d/evaluate.py and ml/p2d/train.py are modified but UNCOMMITTED, as is ml/tests/test_trace.py. Three of its seven tests fail: the two column_runs tests use heat parameters that do not actually fuse the ridges and the chain-crossing test has a small discontinuity at the crossing that the slope tolerance (0.3) does not allow.

Live measurement vs frozen on first 20 charts of data/t2-cross (geometry only):
frozen (6b313e9): found 1.000, good_cov 0.925, rms_median 0.06%, rms_p90 0.37%
live (uncommitted): found 0.896, good_cov 0.805, rms_median 0.09%, rms_p90 12.3%
The joint tracker regresses on crossings. Suspect split_thr=1.2 (just above the p90 adjacent-column embedding distance of 1.15) fragmenting runs falsely and the shared-run mechanism producing bad chains.

Plan: 1) commit current state as a WIP checkpoint so nothing is lost, 2) measure live on 100-chart probes to confirm scope of regression, 3) decide whether to debug the tracker or roll back to the frozen chain + just a smarter merge_fragments. Partner id not yet known; mail inbox is empty.
