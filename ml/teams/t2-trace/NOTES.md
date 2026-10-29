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

## Wed 28 Oct 2026, 16:28 EDT curator

Brainstormer committed the WIP as 9b97b78 (preserving the Fable predecessor's wholesale tracker rewrite + direction head scaffolding + tests), rolled extract.py back to frozen, and is now rewriting ONLY merge_fragments with overlap-join. First attempt (uncommitted) regressed mpl-val geometry-only (found 0.757->0.733 all; simple 0.886->0.899 improved).

What I measured/reported during this round:
- inspect-val-v2.json re-run with per-column overlap (frozen tree): same-series kept-piece overlapping junctions have ov_med p50=6.96, p90=29.46 - the proposed median<=2.0 recovers only 22% of actual same-series overlaps, so it is both too strict for recovery AND too permissive for 6-series false joins at 400-col overlaps.
- val-regressions.txt: 22 charts lost found, 13 gained; 4-series mean delta -0.062 (worst). The regressed charts show "partial series destroyed" not "false positives found"; pred counts move both up and down. Pattern consistent with brainstormer's hypothesis: two chains from DIFFERENT series pass the median test by accident, get merged, and drop_duplicates removes the real one.
- Corrected CASES.md: the earlier cross baseline of 0.827 was from an early contaminated run; the actual frozen-queue baseline is 0.917 all / 0.947 simple. All numbers in the probe table now match out/t2c/v3-*-refine.txt.
- Added teams/t2-trace/tools/compare_runs.py for side-by-side before/after tables.

Next action: wait for brainstormer's tightened merge candidate ("ready - measure tag=X"), then run t2c-measure-live.sh. Standing offer: if the merge keeps regressing on multi-series charts, propose moving the fix into cluster_embeddings instead (merge same-ridge clusters BEFORE chaining), which naturally cannot create cross-series false joins.

## Wed 28 Oct 2026, 16:31 EDT curator

Brainstormer shipped tightened overlap-merge (live-overlap-merge-v2): still regressed on "all" (-0.030 line_found vs frozen); "simple" nearly flat. Same 10 charts fail under both v1 and v2 (tightening didn't help the regressors). Analysis in out/t2c/val-regressions-v2.txt. The regression pattern says merge is picking up GHOST chains that drop_duplicates would otherwise remove, so a wrong merge takes a ghost+real pair and the real line is lost to Hungarian matching afterwards. Suggested swap: run drop_duplicates BEFORE merge_fragments, or filter merge candidates by chain quality (q, min_support). Both appear in the brainstormer's inbox.

Oracle computed from inspect-val-v2.json (out/t2c/merge-oracle.txt): perfect same-series merge gives line_found 0.848 on mpl-val (vs 0.757 baseline) = +0.091 ceiling. Any merge-only fix is bounded by this. The predecessor's measured oracle for cluster-fix (joint-tracker ceiling) was 0.91 on 60-chart subset.

## Wed 28 Oct 2026, 16:34 EDT curator

Diagnosed the real regression on 9000075 (and nine other charts) with inspect_stages on LIVE tree. The new no-overlap branch is strictly STRICTER than the frozen gap rule: for a short gap (dx 20-60) with wavering slope (dashed sine), extrap-miss blocks the join although ygap <= 3+2*dx and de small, so pieces that frozen joined are now kept apart. Brainstormer pivoting to a "superset of frozen gap rule, with Hungarian + slope-aware only for 60..90 cols" approach. Sent them the specific fix: keep frozen's dx 1..60, gap <= 3 + 2*dx, de <= 3 rule intact.

Dedupe-disable upper bound (out/t2c/dedupe-upper-bound.txt): +17 lost rescued (-> 0.794), +74 partials to ok (good_cov ceiling +0.16). Smaller lever for "found" than merge (+42 ceiling) but much larger for "ok". The "ghost ate the real" case is rare (3 of 112) - dedupe-disable rescues mostly by letting dropped pieces supplement the kept ones to pass the >50% cov threshold.

Combined perfect-merge-plus-no-dedupe ceiling: ~0.85 line_found, +0.16 ok rate. Still below the cluster-oracle ceiling of 0.91 found (predecessor's measurement on 60-chart subset).

## Wed 28 Oct 2026, 16:39 EDT curator

Brainstormer's v3 overlap-merge is the first win: on mpl-val 200 geometry-only, line_found 0.757 -> 0.781 (+0.024 all), 0.886 -> 0.899 (+0.013 simple); line_cov +0.021/+0.014; line_good_cov +0.017/+0.015; rms_median -0.026/-0.007. Snapshot in out/t2c/live-overlap-merge-v3/.

Per-chart (val-regressions-v3.txt): 17 gained, 8 lost. Multi-series charts (5-6 series) gained the most (+0.04 to +0.06), reversing the v1/v2 pattern where they regressed worst. Short-gap regression (9000053, 9000075, 9000009) FIXED. 9000031 still 1/2 (long-overlap edge case where ghost merged with real).

The pivot that fixed it: EXACT frozen rule for dx <= 60; slope-extrapolation only as a secondary gate for dx 60..90; overlap case requires ks-disjoint + q>=0.3 + len>=50 + median<=6 + MAD<=1.2 + drift<=2.5 (brainstormer's rule). Hungarian + no_join=5.0 prevents double-claim.

Brainstormer running plotly + 3 probes next to verify no regression, then will commit. I will run the full probe sweep after that.

## Wed 28 Oct 2026, 17:04 EDT brainstormer

Committed v3 overlap-merge (4ab8ee0) and the first REPORT.md (bff8e88).

Measurements landed:
- mpl-val 200: found 0.7570 -> 0.7809 (+0.024) all, 0.8859 -> 0.8993 (+0.013) simple.
- plotly-v1 150: found 0.8608 -> 0.8738 (+0.013) all, slight regression on simple (-0.009).
- t2-cross 100: found 0.9167 -> 0.9267 (+0.010).
- t2-samecolour 100: found 0.9000 -> 0.9125 (+0.013).

Working on dedupe pass now:
- live-dedupe-v1 (envelope removed, per-column interp y check, support sort): too lax (pred counts rose to 22, no gain on found).
- live-dedupe-v2 (envelope kept but window 4 -> 1, tol 3.0 -> 2.5, support sort): measuring (GPU contested).

Next if dedupe-v2 is a modest win: ship and update report. If regression: revert to v3-only.
Follow-up work on branch for next session: direction-head training (scaffolding in place, no consumer in extract.py yet) and the predecessor's whole-ridge-graph tracker (preserved at 9b97b78).

## Wed 28 Oct 2026, 17:15 EDT curator

Brainstormer committed overlap-merge-v3 as 4ab8ee0. Confirmed win on probe (cross +0.010, samecolour +0.013) and on plotly (found all +0.013, cov +0.011, good_cov +0.008; simple slightly down -0.009). 

Dedupe iteration (dedupe-v1 with window=0 + tol=2.5, dedupe-v2 with window=1 + tol=2.5): found metric unchanged over v3, but pred counts exploded by +233 across 79 charts in v2 (+> similar in v1). Diagnosis in to-brainstormer: Path 2 (envelope-swallowed-real) is a RED HERRING - the real series was lost upstream (chain/cluster), not because dedupe hid it. Rolled back dedupe. Keeping extract.py minimal: only merge_fragments/_join_cost/_end_slope changed vs frozen.

Full sweep t2c-measure-live.sh overlap-merge-v3 full running. Done so far: val-refine, plotly-refine, cross, samecolour. In progress: parallel. Pending: shallowx, legocclude, 12 other probes, val-e2e, plotly-e2e, corpus, real. GPU heavily contended (t3, t4, t5 all running); ETA 1-1.5 hours.

Final v3 picture to date (mpl-val 200 geometry only):
    line_found         0.7570 -> 0.7809  +0.024 all
    line_found simple  0.8859 -> 0.8993  +0.013
    line_cov_mean      0.6665 -> 0.6879  +0.021 all
    line_good_cov_mean 0.5884 -> 0.6052  +0.017 all
    line_rms_median    0.3111 -> 0.2852  -0.026 all
Plotly 150 geometry only:
    line_found         0.8608 -> 0.8738  +0.013 all; simple -0.009
Cross 100 probe:
    line_found         0.9167 -> 0.9267  +0.010
Samecolour 100 probe:
    line_found         0.9000 -> 0.9125  +0.013

Mechanism: Hungarian assignment with no_join=5.0 over frozen gap rule (dx 1..60) + slope-aware extension for dx 60..90 + overlap-aware rule (med<=1.5, MAD<=1.2, drift<=2.5, ks-disjoint, q>=0.3, len>=50 on both sides). The pivot that made it work: KEEP the frozen gap rule exactly for the common case.

## Wed 28 Oct 2026, 20:20 EDT curator (replacement v2)

Resumed Opus 4.7 after the 100-min pause reset. Session cap at 11% at arrival.

Status of my sweep (live-overlap-merge-v3) at kill-time:
Done: val-refine, plotly-refine, cross, samecolour, parallel, shallowx, legocclude; val-e2e, plotly-e2e, corpus, real.
Not done (judge killed the chain mid-queue): steep, dotted, thin, small, dense, legend, area, step, clipped, multi, markers, wide.

Reran steep in foreground under flock in 36s (uncontested GPU moment); then launched the remaining 11 probes (dotted thin small dense legend area step clipped multi markers wide) as a serial for-loop under flock. Each eval holds the lock for 40-200s depending on probe. GPU is heavily contended with t3/t4/t5 jobs so wall time is unpredictable.

The replacement brainstormer's rerun script also fires steep + dotted; by pure timing it has queued steep behind many flock waiters and will refill the file whether or not my bg leg hits it (deterministic eval). Dotted already matched (0.8905 both runs).

Delta tables for already-landed probes computed via teams/t2-trace/tools/compare_runs.py (above-the-line numbers in REPORT.md confirmed): parallel +0.100 and shallowx +0.108 are the big wins; cross/samecolour/legocclude show small-positive; plotly simple -0.009 the only regression. See CASES.md section 6 (added below once all probes land).
