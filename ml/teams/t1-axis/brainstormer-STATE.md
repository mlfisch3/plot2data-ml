## Identity

- team: t1-axis
- role: brainstormer
- agent id: a6077483041273a9d
- partner id: ad4f4c6475d1a2a70 (curator, Opus 4.7)
- predecessor: a33a9de7fe0759d04 (Fable 5.1, hit the account's usage limit about 02:30 EDT; see salvage/)
- time: Wed 28 Oct 2026, 18:00 EDT

## Last-committed state

- HEAD: `3c73e75` (code), `83900f0` (REPORT), on branch `team/t1-axis`.
- Submission accepted by the judge: "largest e2e scoreboard gains of the contest so far".
- Standing order from the judge: do not push further changes to this branch.
- pytest 54 of 54 passing. No uncommitted edits in the working tree.
- Headline numbers (cd1956d full run; HEAD ablation says +1.5 more):
  - mpl-val 200: both-axes-within-0.5% 67.5 -> 83.0 (+15.5); line_found 0.547 -> 0.657 (+11.1)
  - plotly-v1 150: calib_x_within 0.947 -> 1.000; line_found 0.754 -> 0.825
  - corpus offset-annotation: 61.222% -> 0.019%
  - real screenshots 01-panel1/2/3 and 03-women-men fixed; others held

## In flight when paused

- Full standard-command scoreboard run on HEAD 3c73e75 was launched at 17:09 EDT; still running under heavy CPU/GPU contention (16+ min elapsed at my last check). PIDs 1115090 (mpl-val), 1115091 (plotly-v1), 1115092 (corpus), 1115093 (eval_real -> out/t1/real-v5/). It will complete on its own and leave `out/t1/v5-{mpl-e2e,plotly-e2e,corpus,real}.txt`.
- No Monitors or `notify_when_idle` subscriptions open from this agent.

## Hypotheses still open

- The 02-microprocessor real chart reads '10^k' as '0^k' because the chart image itself is cut mid-glyph; parse_value handles the mapping so the log fit is still correct, but a cleaner restoration would come from decode_axis's expected-text when cands include '10^k'. Needs a reader that keeps the top-k candidates for a label whose crop is clipped at the image edge.
- The remaining three multiplier charts (9000169 of 7 on mpl-val, plus the 1e-5/1e-6 border cases where the leading '1' is pre-cut from the loose_label) likely want a learned text detector on the axis-end strip, not more ink heuristics. Marginal gain: 1 to 2 points on calib_y_within.
- 45-degree rotated labels (probe t1-rot45/x stuck at about 85% within): a 45-degree branch of normalise_crop needs an estimate of the ink's principal angle and an affine un-rotate. Marginal gain on mpl-val, bigger on the probe.
- Reader misreads on small/anti-aliased text (9000090 '1e22' instead of '1e2') cannot be rescued by the joint decoder when no neighbour disagrees enough. Would need a reader fine-tune (outside this team's area).

## Pending experiments

- Dedup ticks UPSTREAM in `extract.group_labels` instead of in refine_labels + fit_reads; halves the reader work on duplicate ticks (01-panel1/2/3). Not strictly needed because the current dedup is correct, just saves CPU. Someone else might own this.
- Fine-tune the OCR reader on the corpus of {rotated 90, superscripted, anti-aliased edges} crops cut from the probe set; several-hour short run, not a submission for this team.
- Attempt a 45-degree affine un-rotation branch of normalise_crop and re-measure probe t1-rot45/x.
- Expand the end-strip merge to be smarter about long multi-token multipliers like "x10^-5" (needs the "x", "10", "^", "-5" to join cleanly).

## Mail unread

- None pending at pause time. Last two messages from the curator (ad4f4c6475d1a2a70) were acked:
  1. v3c73e75 remeasure launched, same output pattern as earlier.
  2. Waiting on background work; result "paused".
- Last message from main (judge): submission accepted, orthogonality analysis for team-1 x team-5 x team-3 merge sent; no reply pending.

## Resume plan (first three things)

1. Check whether the full HEAD scoreboard finished while paused (`out/t1/v5-{mpl-e2e,plotly-e2e,corpus,real}.txt`). If so, mail the deltas to main under the same submission; otherwise re-run from the venv when CPU/GPU is quieter.
2. Read ml/teams/t1-axis/mail/to-brainstormer.md and the curator-STATE.md for anything new; check `git log --oneline main..team/t1-axis` for anything that landed after 83900f0.
3. If main asks for a merge-conflict resolution between team 1, team 3 and team 5 (orthogonality analysis already sent): walk `git log --oneline main..team/t5-robust` + `main..team/t3-precision` for the specific hunks they changed, and apply my merge-order preference from my 17:22 EDT message to main.

