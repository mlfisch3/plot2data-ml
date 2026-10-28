## Identity

team=t2-trace
role=curator
agent id=a2ebf18cb3759c1ce
partner=brainstormer a21f1052d83acd4a6
pause time=Wed 28 Oct 2026, 17:30 EDT
model=Opus 4.7 at xhigh

## Last-committed state

Branch team/t2-trace head: 51c4247 "t2-trace: overlap-merge-v3 committed; dedupe reverted; full sweep in progress".

Shipping extract.py: overlap-aware merge_fragments with Hungarian assignment (committed at 4ab8ee0).
- The ONLY meaningful change vs frozen 6b313e9 is in merge_fragments + _join_cost + _end_slope + a scipy import.
- Dedupe was tried (dedupe-v1/v2) but reverted; it exploded pred counts without moving the found metric.

Measured deltas vs frozen so far (what the brainstormer will reference in REPORT.md):

| set | metric | frozen | v3 | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 all | line_found | 0.7570 | 0.7809 | +0.024 |
| mpl-val 200 simple | line_found | 0.8859 | 0.8993 | +0.013 |
| mpl-val 200 all | line_cov_mean | 0.6665 | 0.6879 | +0.021 |
| mpl-val 200 all | line_good_cov_mean | 0.5884 | 0.6052 | +0.017 |
| mpl-val 200 all | line_rms_median | 0.311 | 0.285 | -0.026 (improved) |
| plotly-v1 150 all | line_found | 0.8608 | 0.8770 | +0.016 |
| plotly-v1 150 simple | line_found | 0.9720 | 0.9626 | -0.009 (slight regression) |
| plotly-v1 150 all | line_good_cov_mean | 0.7264 | 0.7346 | +0.008 |
| t2-cross | line_found all | 0.9167 | 0.9267 | +0.010 |
| t2-samecolour | line_found all | 0.9000 | 0.9125 | +0.013 |
| t2-parallel | line_found all | 0.7100 | 0.8100 | +0.100 (biggest probe win) |
| t2-parallel | line_good_cov_mean all | 0.602 | 0.6676 | +0.065 |

## In flight when paused

Background job: `bash ml/out/t2c/t2c-measure-live.sh overlap-merge-v3 full` (pid 1103167 at pause time).
State at pause: shallowx probe RUNNING on GPU (pid 1126673); legocclude + 12 more probes + val-e2e + plotly-e2e + corpus + real still pending.
Pid 1103167 is a nohup'd script that will CONTINUE through my pause (it does not depend on this agent). Its outputs land in `ml/out/t2c/live-overlap-merge-v3/`.

Completed outputs in `ml/out/t2c/live-overlap-merge-v3/`:
- val-refine.txt / rows-val.json
- plotly-refine.txt / rows-plotly.json
- cross-refine.txt / rows-cross.json
- samecolour-refine.txt / rows-samecolour.json
- parallel-refine.txt / rows-parallel.json
- extract.py.snapshot, commit.txt

Monitors active at pause: none (all previous monitors expired on their own at 30m timeout before the pause; the last `b15qz4idc` expired coincident with the pause message).

Pending remeasure jobs: on resume, I need to collect:
- shallowx-refine, legocclude-refine, steep/dotted/thin/small/dense/legend/area/step/clipped/multi/markers/wide refine outputs
- val-e2e.txt, plotly-e2e.txt (end-to-end with OCR)
- corpus.txt, real.txt (Chart.js corpus + real screenshots)

The brainstormer is also paused per the coordinator; both will resume together.

## Hypotheses still open

1. Why does plotly-v1 simple regress by -0.009 line_found while plotly-v1 all improves by +0.013? Two charts (seeds 500106 and 500111) each lose one series; pred count rises on both. The overlap-merge appears to add spurious lines in 1-3 series Plotly charts where there was nothing legitimate to merge. If this holds through e2e, it is a minor cost worth noting in REPORT.md but not worth re-fixing before submission.

2. The chain-oracle ceiling the predecessor measured (0.86 cov / 0.91 found on 60-chart subset of mpl-val) is a +0.05 found over v3's 0.78. That remaining gap would require a true cluster-fix (not just merge). Would be the next lever for a v4.

3. Shallowx baseline (frozen) had chain stage perfect (1.000) but final 0.902; the loss was drop_duplicates behavior. v3 may ALSO improve shallowx because merge consolidates ghost+real pairs. Awaiting shallowx measurement to confirm.

4. The dedupe lever appears closed. Path 2 (envelope-swallowed-real) is a RED HERRING: of 20 of 112 lost series with the symptom, only 2-3 actually recoverable by dedupe fixes - the real series were lost upstream (chain/cluster), not just hidden by dedupe. See out/t2c/dedupe-paths-analysis.txt and dedupe-upper-bound.txt.

## Pending experiments

None of mine. The brainstormer may try "one more small improvement that rides alongside v3" per their last message: a safer _join_cost tie-breaking refinement for dense charts. If they ship it, I will measure.

Possible future levers (not for this round):
- Direction-head training (predecessor's scaffolding in model/data/losses is intact).
- Cluster-fix: merge same-ridge clusters BEFORE chaining (would need peel_chains rework or a new upstream pass).
- drop_duplicates with chain-level q scoring + per-column agreement (ran out of time to tune the thresholds correctly).

## Mail unread

Latest in `ml/teams/t2-trace/mail/to-curator.md`: curator inbox was last touched by predecessor at 01:44 EDT; nothing new there. Live comms with the brainstormer are via SendMessage; latest I received was "Reverted drop_duplicates to frozen... Thank you - this has been a productive pair." I replied with sweep status. No unread mail.

## Resume plan

1. Check `ml/out/t2c/live-overlap-merge-v3/` to see what the sweep produced during the pause (all files or still running).
2. If sweep still running, let it continue; otherwise analyse the newly-landed probes/e2e/corpus/real.
3. Compute delta table across all 15 probes vs frozen (teams/t2-trace/tools/compare_runs.py) and the end-to-end/corpus/real numbers.
4. Send the complete delta to brainstormer for REPORT.md's "Generality and regressions" section.
5. Update CASES.md with shallowx/legocclude v3 numbers.
6. Final NOTES.md entry: brief, summary of session.
7. Confirm `git status` is clean (no uncommitted work other than brainstormer's pause-state files which they will handle).
8. Reply to main with the final summary paragraph.

Specific numbers to collect from sweep outputs:
- live-overlap-merge-v3/{shallowx,legocclude,steep,dotted,thin,small,dense,legend,area,step,clipped,multi,markers,wide}-refine.txt line_found / line_cov_mean / line_good_cov_mean / line_rms_median_pct / line_rms_p90_pct, deltas vs out/t2c/v3-{same}-refine.txt frozen.
- live-overlap-merge-v3/val-e2e.txt and plotly-e2e.txt: ALL metrics (line_found, cov, good_cov, rms, peak_err, marker_recall, marker_precision, calib_x_within_0.5pct, calib_y_within_0.5pct), deltas vs out/base/v3-e2e-ocr.txt and out/base/v3-plotly-e2e.txt if those exist (or vs frozen separately-run e2e).
- live-overlap-merge-v3/corpus.txt: per-series RMS vs published; delta vs out/base/v3-corpus.txt.
- live-overlap-merge-v3/real.txt: calibration error at hand-measured anchors.

Analysis helpers available:
- teams/t2-trace/tools/compare_runs.py --a <frozen.txt> --b <live.txt>
- teams/t2-trace/tools/compare_runs.py --dir-a out/t2c --dir-b out/t2c/live-overlap-merge-v3 --probes cross samecolour parallel ...
- Python ad-hoc for e2e/corpus/real.

Threshold for the pause/resume protocol: 50% (coordinator said 64% at pause time). Expect usage to reset at approximately 19:10 EDT (~100 min from pause message).
