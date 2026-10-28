# curator-SCRATCH.md (chronological, free-form)

## 16:08 EDT, resumed as Opus 4.7 curator

Predecessor cut off ~02:30 EDT. Read BRIEF, ASSIGNMENT, NOTES, CASES, scripts/, git log, measure.py, extract.py, evaluate.py, test_measure.py (new, untracked), probe sets at data/t3-*. Killed a dangling shell waiting on `out/t3/diag-plotly-base.pkl` from the predecessor's chain.

Working-tree state at resume: brainstormer's uncommitted edits on `p2d/measure.py` (bugfix `np.where(have,...)->np.where(clean,...)` plus dash-gap bridger), `p2d/extract.py` (offset-only `refine_ticks`), `p2d/evaluate.py` (`--no-refine` and default refine=True), `scripts/diag.py` (timing + partial checkpoint). test_measure.py was untracked.

Three test_measure flat_line tests failed with ends off by 0.25 px at butt caps.

## 16:12-16:22 EDT, scoreboard measurements against the WIP

Baseline for #5 (geometry --refine on 200 mpl-val) at `out/t3/base-refine.txt`: simple RMS 0.189 / all 0.311.
Pre-fix WIP (d3c4502 + brainstormer's uncommitted) score5: simple RMS 0.309 / all 0.574, p90 4.48 simple / 5.07 all. A clear regression on all headlines; peak_err_p90 slightly worse too.
corpus-new1.txt (predecessor's 02:42 run of eval_corpus): series median 0.067 -> 0.085, with narrow-peaks 0.211 -> 6.104 (disaster), linear-thick-line 0.042 -> 0.085, dark-theme 0.047/0.017 -> 0.088/0.085, big wins on log-log and sawtooth-sharp.

Pinned the regression to measure.py's spike-triangle fill + the butt-cap occlusion test + the flank-fit without a direction check (`_vertices`). Sent to brainstormer with the exact mechanism (base + (tip-base)*max(0, 1 - |x-xv|/w_half) collapsing to `base` for every q!=apex at a 1-pixel spike).

Overlay script at `/tmp/claude-1000/.../scratchpad/overlay2.py` reads BASE and LIVE pipeline outputs on narrow-peaks and draws a 3x6 panel per spike with truth / base / live traces at 4x zoom. Output at `ml/out/t3/cases/narrow-peaks-{broken,overlay}.png`. Broken is pre-fix (16:22), overlay is fixed. Gitignored path so not committed.

## 16:23-16:30 EDT, 6db13c8 lands

Brainstormer committed 6db13c8 that:
- Reverted `np.where(clean, cen, yc)` to `np.where(have, cen, yc)` for butt caps.
- Gated the occlusion test with neighbour mass.
- Added sign test to flank-fit vertex intersection.
- Deleted the spike-triangle fill block.

Tests pass (13/13).

My corpus_diag on narrow-peaks confirms: rms 0.292% (within 0.08 pp of base), trace 0.251 / calib 0.149, peaks in_p50 +0.06% (better than base at the tips, the residual is in the one-sample flank climb).

Scoreboard #5 at 6db13c8 landed: simple RMS 0.271 (still worse than base 0.189 by 0.082); all 0.397 (vs 0.311); p90 reductions dramatic vs pre-fix. iter_refine 60-cache simple RMS 0.136 (-15% vs base). So on the full 200-chart it's still a regression (fix recovers most of the pre-fix regression but not all); on the 60-cache it wins.

Pinned the 60-vs-200 discrepancy to the predecessor's cache being built from easy early seeds; the 200-chart tail has more charts where the new code misplaces columns gross.

iter_refine per-chart analysis found top regressions on 60-cache: 9000008 (6-series dense) +0.051, 9000039 (1-series 15-point sparse line) +0.042, 9000006 (area, 9 points) +0.040. Sent to brainstormer.

## 16:30-16:40 EDT, 0e9e16b lands

Brainstormer committed 0e9e16b: restored `np.where(clean, cen, yc)` and dropped the aggressive occlusion gate; flat-line test switched to noise=0 trace so end-column fallback is covered by yc.

iter_refine 60-cache: simple RMS 0.122 (-24% vs base), simple peak_err 0.144 (-52% vs base), all peak_err_p90 -0.5pp.

Scoreboard #5 at 0e9e16b (my r2 chain): simple RMS 0.167 (-12% vs base 0.189), all 0.361 (+0.050), peak_err_p90 2.890/11.476 (both wins). WIN on simple median, slight loss on all median, p90 wins both. Big step forward.

My r2 chain's score1 and score1-norefine then landed with mixed state in the measure.py file (brainstormer was editing live). Not clean. Killed and relaunched.

## 16:40-16:53 EDT, 8053952 lands (slope_yc fix)

Brainstormer committed 8053952: merged-run and occlusion tests use slope_yc (trace slope), not cen's slope. Fixes 9000039-style regressions where cen jumps huge into a fill.

iter_refine 60-cache: simple RMS 0.112 (-30% vs base), simple peak_err 0.100 (-66% vs base).

My r3 chain at HEAD f64cbc4 (REPORT draft on top) ran: #5 at 8053952 -> simple RMS 0.136 (-28% vs base), peak_err_median 0.276 (-10% vs base), peak_err_p90 2.635/11.973 (both wins). Clean result. #1 at 5b90499 (still with harness change on): simple RMS 0.374 (+0.064 regression vs baseline), simple peak_err 0.375 (-4% win). The harness change on e2e is NOT a win on simple median.

Score1-norefine at f64cbc4 identical to baseline (sanity check).

## 16:53-17:05 EDT, 4b3b172 and 4c56536 (apex both-sides + harness revert)

Brainstormer committed 4b3b172 (apex detection needs ink falling away on BOTH sides, fixes linear-thick-line and the trace-edge false apex) and 4c56536 (revert evaluate.py: --no-refine removed, --refine opt-in restored, matches original scoreboard behaviour).

iter_refine 60-cache at 4b3b172: simple RMS 0.089 (-44% vs base), all RMS 0.245 (-21% vs base), simple peak_err 0.093, all peak_err 0.909 (essentially unchanged on dense).

4c56536 means the e2e commands must have --refine PASSED to turn refinement on; without --refine, measure.py never fires on e2e (matches baseline).

My r3 chain's step #2 e2e plotly ran at 4c56536 without --refine passed, so measured baseline (byte-identical to v3-plotly-e2e.txt). Discarded r3-score2.

Killed r2 and r3 wrapper processes that were still queued in the background (they survived earlier pkills); verified clean process state.

## 17:05-17:28 EDT, r4 chain against 9b82fba

Launched `remeasure4.sh r4` with `--refine` passed explicitly on all e2e commands. Steps: #5 geometry, #1 e2e refine, #2 e2e refine, corpus, probe peaks live, probe spikes live, probe peaks base, probe spikes base (last two conditional on txt missing).

Score5 at 9b82fba (apex-both-sides fix in) started 17:05:20 and was still running at 17:28 EDT pause (22+ min in, 11-way GPU contention with other teams).

Brainstormer explored a ridge-top correction on a temporary branch to improve narrow-peaks beyond 0.292%; it regressed to 2.646%, so left HEAD at 9b82fba and the branch was deleted. REPORT.md updated at 9b82fba with the apex-end gate and the harness revert; brainstormer standing by for r4 numbers.

Partner messages confirmed: (a) e2e harness change is NOT in submission, (b) measure.py is stable at 9b82fba, (c) scoreboard #5 is the headline, (d) corpus series median 0.067 -> 0.085 is a known slight regression driven by linear-thick-line, dark-theme, narrow-peaks and narrow-small.

## Gotchas and things to remember

- Three teams run GPU evals concurrently. A full p2d.evaluate takes 3 min solo but 20+ min under 8-way contention. Plan for slow iteration.
- The brainstormer may edit measure.py while a chain is running; the Python process picks up WHATEVER measure.py is on disk when it starts, not when it was queued. The remeasure2.sh (both r2/r3/r4) logs per-step HEAD + measure.py mtime so you can tell which step ran against which code.
- Each wrapper's `set -e` means a failed step aborts the chain. A failing step (e.g. `--no-refine` after it's removed) will abort before probes.
- `pkill -f "[t]3-precision"` kills t3 python children but the bash wrapper processes can survive if they were started from a different shell session, and they will LAUNCH the next python step. Kill the bash wrapper by its PID (shown in `ps`) when fully cleaning up.
- `np.where(have, cen, yc)` vs `np.where(clean, cen, yc)` was flip-flopped three times during the brainstormer's iteration; the final answer at 9b82fba is `np.where(clean, cen, yc)` with the clean gate relaxed (occlusion test needs neighbour mass).
- The baseline tree at `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` is read-only to us; `cd` there and run eval normally for baseline measurements. `P2D_ROOT=/.../base/ml` env var is used by some scripts (diag.py, corpus_diag.py) to import p2d from the baseline tree.
- The predecessor's 60-chart `out/t3/cache-val60` is a `iter_refine`-friendly set of pre-run pipelines; CPU only; use `python teams/t3-precision/scripts/iter_refine.py --cache out/t3/cache-val60 --mode new --json ...` for fast feedback on measure.py changes. Signal is roughly `line_rms_median` ratio and `peak_err_median` ratio with 60-chart variance.
- `pkill -f ... t3-precision` must NOT appear anywhere else in the command (not even as the launch line of the kill script itself), or the kill matches its own shell.
- The task framework blocks `sleep N` as a top-level foreground command. `until <check>; do sleep <k>; done` is OK as a background job pattern. Also `run_in_background: true` on an until-loop pattern.

## Scoreboard numbers summary (as of pause, 17:28 EDT)

Scoreboard #5 (geometry --refine on 200 mpl-val):
- base v1 refine: simple 0.189 / all 0.311
- 6db13c8 r2: simple 0.271 / all 0.397 (recovers most of pre-fix regression)
- 0e9e16b r2-score5: simple 0.167 / all 0.361 (first win on simple)
- 8053952 r3-score5: simple 0.136 / all 0.323 (-28% simple, +0.012 all; peak_err_median -10% simple, -6% all; peak_err_p90 -12%/-4%)
- 9b82fba r4-score5: PENDING (expected ~0.12 simple from the brainstormer's iter_refine signal)

Scoreboard #1 e2e (refine on, --ocr on 200 mpl-val) at 5b90499 (r3-score1):
- base refine=off: simple 0.310 / all 0.441
- fix (0e9e16b/5b90499) refine=on: simple 0.374 / all 0.435 (+0.064 simple regression; +0.052 win on all peak_err_median)

Corpus (series median):
- base: 0.067
- 8053952 brainstormer local: 0.085 (slight regression)
- 9b82fba brainstormer local: 0.085 (same; linear-thick-line fix doesn't help median; narrow-peaks still 0.292)

Probe sets: NOT YET MEASURED (will land in r4 chain).

iter_refine 60-cache, simple RMS:
- base v1 refine: 0.160
- 6db13c8: 0.136 (-15%)
- 0e9e16b: 0.122 (-24%)
- 8053952: 0.112 (-30%)
- 9b82fba (apex-both-sides): 0.089 (-44%)

The gap between 60-cache (-44%) and 200-chart (-28%) is the harder-tail charts; the "all" split has a residual dense-chart regression that was not resolved before pause.
