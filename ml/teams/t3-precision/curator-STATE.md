# curator-STATE.md (t3-precision curator pause snapshot)

## Identity

- Team: t3-precision
- Role: curator
- My agent id: Opus 4.7 replacement curator (predecessor was aef15f58d799613ec, cut off 02:30 EDT)
- Partner id: ad1e8579d50b8d7ce (replacement brainstormer, Opus 4.7)
- Partner status: last known standing at team/t3-precision 9b82fba with REPORT.md updated; may have continued to iterate on dense-chart run selection.
- Pause time: Wed 28 Oct 2026, 17:28 EDT (5-hour session quota >57% per the coordinator; this signal is NOT the per-turn context tokens, which still have plenty of room).

## Last-committed state

- Branch: `team/t3-precision`.
- Branch HEAD at pause (verify with `git -C /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t3-precision log --oneline -5`):
  - `9b82fba` t3: REPORT update with the apex-end gate and the harness revert
  - `4c56536` t3: revert the e2e harness change, keep refine opt-in via --refine
  - `4b3b172` t3: an apex needs ink falling away on BOTH sides, not just one
  - `f64cbc4` t3: NOTES brainstormer entry since 16:14
  - `e2c2fec` t3: REPORT.md with the scoreboard #5 numbers and the corpus delta
  - `60f0ae1` t3: loosen peak-family test to accept generator seeds with few scored tips
  - `8053952` t3: use the trace's slope in the merged-run and occlusion tests
  - `5b90499` t3: initial REPORT.md draft, awaiting the full-scoreboard numbers
  - `0e9e16b` t3: fall back to the trace at clean=False columns, drop the aggressive occlusion gate
  - `d04def9` t3: CASES.md section 6 narrow-peaks diagnosis before/after fix (my commit)
  - `6db13c8` t3: fix narrow-peaks regression, butt-cap test, flank-fit direction
  - `b2a6276` t3: probe tips isolated for the peak metric (predecessor's)
- Files owned by curator (do not expect to see unknown edits to these):
  - `ml/p2d/synth/probe_t3.py` (probe generator, seven families).
  - `ml/teams/t3-precision/CASES.md` (sections 1-6 all present; section 6 is my work).
  - `ml/teams/t3-precision/scripts/*.py` (diag.py, diag_report.py, probe_report.py, corpus_diag.py, colres.py, oracle.py, cases.py, cache_ex.py, iter_refine.py, mpl_stroke.py, tickdiag.py).
- Persistent notes:
  - `ml/teams/t3-precision/NOTES.md` (dated log, both agents write).
  - `ml/teams/t3-precision/CASES.md` (failure catalogue).
  - `ml/teams/t3-precision/REPORT.md` (brainstormer's submission draft).
  - `ml/teams/t3-precision/mail/to-curator.md` and `mail/to-brainstormer.md` (append-only).
- Worktree layout: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t3-precision/`. Frozen baseline at `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/`. The venv is `.venv/` symlinked to the main checkout's `.venv`; activate with `source ../.venv/bin/activate` from `ml/`.

## In flight when paused

- `ml/out/t3/remeasure4.sh r4` is running in the background (pid 1114171 for the wrapper; python eval child was pid 1114182 at pause). It is doing scoreboard #5 (geometry --refine on 200 mpl-val) at HEAD 9b82fba right now; next planned steps in order: #1 e2e --ocr --refine 200 mpl-val, #2 e2e --ocr --refine 150 plotly-v1, eval_corpus, probe peaks (240) --refine, probe spikes (160) --refine, BASE peaks and spikes if `out/t3/base-peaks.txt` and `out/t3/base-spikes.txt` are missing.
- Step 1 (#5) started at 17:05:20 and had been running 22+ min at pause due to 8-to-11-way GPU contention from t1, t2, t4, t5 running their own evals.
- How to tell if it has completed by the time you resume: `ls -s /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t3-precision/ml/out/t3/r4-score5.txt`. Zero bytes means still running; non-zero means done. The full chain writes an `=== ALL DONE ===` marker to `out/t3/remeasure4.log` at the end. `pgrep -af "[t]3-precision.*evaluate\|[t]3-precision.*remeasure4"` tells you if any process is still alive.
- Script itself: `ml/out/t3/remeasure4.sh`. It passes `--refine` on all e2e commands so the harness revert in 4c56536 does not accidentally measure the baseline.
- Older chains: r2 and r3 wrappers were killed before pause (the predecessor to r4 is r3; r3's data at `out/t3/r3-*.txt` was partially measuring the wrong harness state). Do not rely on r2 or r3 txt files other than r3-score5 (clean at 8053952) and r3-score1 (at 5b90499 with the harness change still on; useful as "what the harness change does on e2e").

Background watcher tasks (will send a `[cross-session delivery notice]` or task-notification when they fire):
- `bc90egdwz` (foreground wait moved to background at 10 min cutoff): until r4-score5.txt is non-empty.
- `bjyptzdnr` (foreground wait moved to background at 10 min cutoff): until r4 log contains "ALL DONE".
- `b4knspwjr` (same for r3 ALL DONE): obsolete since r3 was killed, will probably expire.
- `b12mb3dje`, `b9u5xhzbo`, `bm22ezwsj`: older waits, already fired or now stale.

## Hypotheses still open

- Scoreboard #5 at 9b82fba: expected simple RMS 0.11-0.13% (from the brainstormer's iter_refine 0.089% signal on the 60-cache, modulo the 200-chart harder tail). r3-score5 at 8053952 was 0.136% simple.
- E2e scoreboard #1 and #2 at 9b82fba (with --refine passed): the harness revert made them refine=False by default; passing --refine turns measure.py on in the e2e path. Simple RMS likely 0.37% as in r3-score1 (-0.064 vs baseline 0.31%), which is a loss. The REPORT should document this and not claim an e2e win: the submission is a geometry win.
- Corpus series_median: brainstormer's local run says 0.067% -> 0.085% (slight corpus regression). My r3 and r2 corpus runs are both tainted (brainstormer edits during the chain). r4-corpus will be the clean reading.
- Probe peaks / spikes: never measured yet with either tree. The baselines (`base-peaks.txt`, `base-spikes.txt`) are also missing - r4 will produce them. Expected: peaks probe `peak_err_median` drops sharply from the base number thanks to the classical turn rule.
- The "all" chart dense-tail regression (0.311% baseline -> 0.323% r3-score5 at 8053952, down to 0.245% on cache-val60 iter_refine with 4b3b172) is the one open open regression; the brainstormer tried a ridge-top correction and it regressed narrow-peaks, so left for future work.

## Pending experiments

- Verify r4 numbers once ALL DONE fires:
  - `cat ml/out/t3/r4-score5.txt`, compare to the baseline at `out/base/v3-pixel.txt` (0.189 simple RMS).
  - `cat ml/out/t3/r4-score1.txt` and `r4-score2.txt`: expect e2e refine=on gives +0.06 simple median regression per r3; confirm.
  - `cat ml/out/t3/r4-corpus.txt`: narrow-peaks around 0.29%, log-log around 0.77%, series median around 0.085%.
  - `cat ml/out/t3/r4-peaks.txt` and `r4-spikes.txt`: probe peak_err_median; compare to `base-peaks.txt` and `base-spikes.txt`.
- If r4 numbers are in: update CASES.md section 7 with "probe sets: peaks and spikes before/after" and add the final scoreboard table.
- If the chain errored on something (e.g. `--no-refine` was still in a kept-live step), the log in `out/t3/remeasure4.log` says which step; fix and relaunch only that step.
- Deep probe analysis with diag.py (`out/t3/probe-diag.sh`, already written, not yet run): per-factor breakdown by prominence, half_cols, lw, join, scale. Useful for the REPORT only if time; the headline is scoreboard #5.
- Scoreboard #1 and #2 regression investigation: pick 5 charts with the biggest simple-RMS regression on e2e, look at what's different between refine=False (right trace) and refine=True (wrong trace); run `scripts/colres.py` or `scripts/diag.py` on them if GPU is free.

## Mail unread

The mailbox `mail/to-curator.md` ends with brainstormer's 01:51 EDT entry (the error-budget piece) from before cutoff - everything after that is via `SendMessage` which is not durable, so a replacement should assume no durable mail is unread. The important things from the SendMessage stream between 16:12 and 17:28 EDT are summarised below in SCRATCH.

## Resume plan

1. First: `cat ml/out/t3/remeasure4.log` to see where the chain is. If `=== ALL DONE ===` is there, read all `r4-*.txt` and build the comparison table in NOTES.md + CASES.md section 7. If not, `pgrep -af "[t]3-precision"` to see if it is still alive; if not alive but incomplete, relaunch only the missing steps using the step list in remeasure4.sh.
2. Second: write the final scoreboard table into NOTES.md with r4 numbers, update CASES.md section 7 with probe peaks/spikes before/after (base-peaks.txt vs r4-peaks.txt, same for spikes). Commit as `t3: scoreboard numbers and probe set evidence at 9b82fba` (no co-author line, plain Markdown, single hyphen never em dash).
3. Third: send a brief summary to `main` with the final numbers and the paths to CASES.md, REPORT.md, NOTES.md. The headline is: scoreboard #5 simple line_rms_median -28% vs baseline (0.189 -> 0.136 at 8053952, likely close to 0.12 at 9b82fba); simple peak_err_median -10%; both p90s win. The harness change is NOT in the submission. The all-chart dense tail is a known residual regression.

Then back to standing by for the brainstormer, if partner is still active.
