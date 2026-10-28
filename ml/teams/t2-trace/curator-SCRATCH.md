# curator SCRATCH

Free-form chronological notes from the current replacement curator (Opus 4.7, agent a2ebf18cb3759c1ce, Wed 28 Oct 2026, 16:07-17:30 EDT before pause).

16:07 - Arrival. Read predecessor's commits, salvaged last narration lines from JSONL, documented inheritance. Three queue scripts from the predecessor completed cleanly at 04:19-04:29 EDT: baselines on 17 probe sets + inspect-val.json/txt (200 charts) + diag-probes.txt.

16:14 - Sent brainstormer (a21f1052d83acd4a6) the inheritance introduction and the three key findings: diag-probes.txt stage attribution, inspect-val summarize (149 of 461 series have ridge pixels in >=2 clusters; 207 refused same-series junctions), emb-cross/samecolour stats.

16:20 - Received brainstormer's three asks: (1) merge-only recovery count, (2) emb_tol distribution, (3) t2-cross/parallel baseline numbers. Answered with 42 of 112 lost rescuable, emb_tol<=4 recovers 91%, and the dominant blocker is DX overlap (81% of refused junctions have dx < -8), not de.

16:25 - Added shallowx and legocclude probe cases to probe_t2.py. Rebuilt as 100-chart sets.

16:30 - inspect-val-v2.json re-run with new per-column overlap instrumentation (n_ov, ov_med, ov_p90). Took only 2 min thanks to npz cache. Key finding: same-series overlap ov_med has p50=6.96, p90=29.46 - the predecessor's assumed "ov_med<=2.0" threshold recovers only 22% of actual same-series overlaps. The merge rule needs to use multiple criteria (med + MAD + drift), not just the median y gap.

16:35 - Brainstormer shipped live-overlap-merge (v1). Regressed on mpl-val found all by -0.030. Diagnosed via val-regressions.txt: 22 charts lost, 13 gained; 4-series mean delta -0.062 worst. Hypothesis: wrong joins of different-series chains in dense charts.

16:40 - Brainstormer shipped live-overlap-merge-v2 with tightened thresholds. STILL regressed (-0.030 found). Same 10 charts failed. Diagnosed: not the overlap but the NO-OVERLAP branch - new slope-extrapolation gate rejects joins at short gaps where frozen's "gap <= 3 + 2*dx" would accept.

16:45 - Brainstormer pivoted to v3: EXACT frozen gap rule for dx 1..60, slope-aware only for dx 60..90, overlap rule with MAD+drift. First WIN: mpl-val all found +0.024, simple +0.013, cov +0.021, good_cov +0.017, rms_median -0.026. Multi-series charts gained most (6-series +0.059).

16:50 - Brainstormer confirmed plotly delta: all +0.013 found, simple -0.009. Committed as 4ab8ee0. Asked me which of 3 dedupe paths has the cleanest signature.

16:55 - Dedupe analysis (dedupe-paths-analysis.txt): Path 1 (shallowx finding) only 1 of 112 lost; Path 2 (envelope swallows real) 20 of 112 but mostly cross-series which is correct behavior; Path 3 (raise min_q) would remove MORE real pieces. Recommended tightening tol=2.5 window=1 as safest.

17:00 - Launched full probe sweep t2c-measure-live.sh overlap-merge-v3 full (nohup, pid 1103167). GPU heavily contended by t3, t4, t5 teams.

17:05 - Brainstormer's dedupe-v1 (window=0) exploded pred counts (+8 to +16 per chart on top-10) without moving found. Dedupe-v2 (window=1 compromise) still exploded (sum pred delta +233 across 79 charts). Advised reverting to frozen dedupe and shipping v3 as-is.

17:21 - Brainstormer agreed and reverted. Now waiting on my sweep.

17:30 - Pause message received. Sweep still running (shallowx probe on GPU). Sweep is nohup'd so continues through pause.

Key artifacts I own:
- ml/p2d/synth/probe_t2.py: added shallowx and legocclude cases
- ml/teams/t2-trace/CASES.md: updated with corrected baselines and new probes
- ml/teams/t2-trace/tools/compare_runs.py: side-by-side evaluate output comparison
- ml/teams/t2-trace/tools/{analyze_rows,diag,embcheck,embstats,inspect_stages,summarize_inspect,hops,joinstats,sweep,whystop}.py (some from predecessor, inspect_stages has my per-column overlap addition)
- Analyses in ml/out/t2c/: dedupe-paths-analysis.txt, dedupe-upper-bound.txt, merge-oracle.txt, merge-rescue-detail.txt, overlap-stats.txt, val-regressions.txt, val-regressions-v2.txt, val-regressions-v3.txt, inspect-val-v2.{json,txt}, summarize-val.txt, compare_runs tool output.

Open on resume:
1. Check what the sweep produced during pause (shallowx, legocclude, 12 other probes, val-e2e, plotly-e2e, corpus, real).
2. Delta tables for everything vs frozen.
3. Final REPORT.md update by brainstormer with my numbers; final NOTES.md and CASES.md by me.

Interactions that mattered:
- The "contaminated baseline" scare: v3-cross-refine.txt was overwritten to 0.917 found by the frozen queue; the predecessor's earlier 0.827 reading was from an uncommitted live tree edit by the brainstormer and was wrong. Caught and corrected CASES.md.
- The "no-overlap branch too strict" diagnosis saved 2 iterations of noise: v1 and v2 both had the same ten regressed charts; identifying that one branch was the culprit let the brainstormer pivot in one try.
- The dedupe red herring: 20 of 112 lost series APPEARED rescuable by dedupe but were actually lost upstream. Saved iterating on dedupe thresholds that would never have delivered.
