## Identity

- Team: t1-axis
- Role: curator
- Agent id: ad4f4c6475d1a2a70 (Opus 4.7 replacement)
- Partner id: a6077483041273a9d (replacement brainstormer, Opus 4.7)
- Paused at: Wed 28 Oct 2026, 17:57 EDT
- Session start (replacement): 16:06 EDT

## Last-committed state

My branch HEAD is 37c7ebe (brainstormer's `REPORT.md v5 ablation` commit). My own curator commits since takeover, newest first:

- d14c686 CASES.md header level fix for classes 11 and 12
- 418d604 remeasure.sh - one-shot re-measurement script for any new commit
- 09bb103 CASES.md section 12 extended with probe and real-screenshot evidence
- fde46d3 NOTES.md measurements against 244ce7b and real-screenshot regression
- 2db8e2c CASES.md class 12 (colour-aware box regressions, 7 charts)
- 969dc43 axis_overlay.py (truebox + computed boxes for a few seeds)
- 8ef8cd3 CASES.md probe-set baseline table and class 11 (superscript taken as label)
- 253a1e6 parse_value OverflowError guard in diag.py and test_reader.py
- 72a9afd Opus 4.7 takeover - NOTES, salvage, offline.py, test_reader.py

The brainstormer's cumulative commits since takeover: 244ce7b (snapshot), 8bcd112, cd1956d, 3929f5c, ba4b822, 3c73e75, 5e91191, 37c7ebe. Current HEAD on team/t1-axis is 37c7ebe.

## In flight when paused

- Background `remeasure.sh v3c73e75` was wedged on `teams/t1-axis/diag.py` (12 min elapsed, 0 overlays written) due to system load averaging 20+ on 16 cores and GPU 90% full with 15+ competing processes. KILLED on pause (SIGTERM to all teams/t1-axis/ processes). No partial output needs preserving: the diag was still in model-load / early-batch phase and did not reach reclass/compare/test_boxes.
- Wait scripts: all killed (`DONE` loop scripts and watcher2).
- No Monitor tool subscriptions. The branch-commit watcher (`boqc5di4t`) already completed and reported `5e91191` before pause.

## Hypotheses still open

1. The brainstormer's three latest fixes (hyphens in multiplier scan, `_mask_tick_marks` max_w=6, dedup tick reads) should clear most of the mpl-val "class 12" regressions and improve probe `t1-crowded_y/x`, `t1-tiny/x` back toward 1.0. Not yet measured on my side (my remeasure wedged); the brainstormer confirmed by their own numbers that both-axes-within-0.5% is 83.0 on 3c73e75 (vs 81.5 on 3929f5c, +1.5).
2. The probe `t1-dates/x` 0.20 within is reader + date parser; the brainstormer deprioritised. Not expected to move post-3c73e75.
3. The probe `t1-rot90/x` 0.00 should move to near 1.00 post-3929f5c (90-deg rotation of tall crops). The brainstormer's reader-on-true-boxes went from 22.5 to 97.5% exact on rotated labels on mpl-val.
4. Multiplier/offset: 6 of 7 mpl-val charts fixed post-cd1956d; 9000079, 9000153, 9000169 may still miss.
5. Possible false-positive risk from the axis-end multiplier scan: a non-multiplier axis mislabelled with a factor. Not yet audited; the brainstormer asked for this check.

## Pending experiments

(All queued to run post-resume, in this order of priority:)

1. **Rerun `teams/t1-axis/remeasure.sh v37c7ebe`** against the current HEAD (37c7ebe). Produces: diag-mpl-v37c7ebe, diag-probe-v37c7ebe, compare-mpl-v37c7ebe.txt, compare-probe-v37c7ebe.txt, boxes-mpl-v37c7ebe.txt, boxes-probe-v37c7ebe.txt. Expected ~15 min on a quiet GPU, up to an hour under contention; run `nohup` with the sentinel-DONE wait pattern.
2. Fill the actual probe-set numbers into REPORT.md's "Probe set" section (currently has placeholders "near 1.0" for `t1-mult_sci/y`, `t1-offset/y`, `t1-rot90/x`). Replace with the compare file numbers once (1) finishes.
3. Audit for false-positive multipliers: scan diag-mpl-v37c7ebe/diag.json for any y axis where the fit chose a non-1 multiplier and the predecessor base did not. Report any findings to the brainstormer.
4. If the brainstormer committed anything newer during the pause window, run remeasure with that tag instead of v37c7ebe.

## Mail unread

None. Last message to the brainstormer sent at ~17:00 EDT ("Not retrying; waiting on remeasure"). The brainstormer's last message was received at ~17:15 EDT ("v5 ablation 83.0 landed, full scoreboard still running"). All sent via SendMessage; no mailbox entries added after takeover.

## Resume plan

1. `date "+%a %-d %b %Y, %H:%M %Z"` to confirm the pause ended; write a "## Wed 28 Oct 2026, HH:MM EDT curator: resumed" entry in NOTES.md.
2. Check `cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis && git log --oneline -5` for new brainstormer commits since 37c7ebe. If any, remeasure on the new HEAD instead.
3. `cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml && nohup teams/t1-axis/remeasure.sh v<hash> > /tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/remeasure4.log 2>&1 &` plus the standard `until grep -q "^DONE" ...; do sleep 30; done` waiter.
4. While remeasure runs, do the false-positive multiplier audit by reading the existing diag-mpl-v244 and (if available) diag-mpl-v3929f5c json: look for y axes with a scale factor applied vs the base's unchanged fit. Flag any that look suspicious to the brainstormer.
5. When remeasure finishes, update REPORT.md's "Probe set" section with the real numbers, and send compare file headlines to the brainstormer. Fill a final per-style delta table.
6. Final message to `main` (the judge) summarising: diagnosis (the nine classes from CASES.md with counts), the probe set (path `data/t1-probe/`, 640 charts seeds 11,000,000+, generator `p2d/synth/probe_t1.py`, baseline and post-fix numbers), and the paths to `ml/teams/t1-axis/CASES.md` and `ml/teams/t1-axis/REPORT.md`.
