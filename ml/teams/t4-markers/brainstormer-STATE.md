## Identity

- Team: t4-markers
- Role: brainstormer (second replacement after a1d4346bed4bd4f04 was cut off at 19:30 EDT)
- My agent id: this current Opus 4.7 xhigh session (invoked ~20:03 EDT, Wed 28 Oct 2026)
- Partner (curator): a6a58ff6a5e541736 (Opus 4.7)
- Time of last state write: `Wed 28 Oct 2026, 20:15 EDT`

## Last-committed state

- Branch head: `9a6dbfa` (`wip(t4): pause-state snapshot`) on `team/t4-markers`
- Last code commit: `e4edf2b` (step25) - dash veto scatter-only, iso elongation filter, sem[TEXT] veto
- No new code changes planned. HEAD intended for submission is `e4edf2b` (equivalent to 9a6dbfa in behaviour; 9a6dbfa is pause snapshot).

## In flight

- Background chain `ml/out/t4/step25-finish.sh` (my shell task bz1km191g; nohup pid 1194636) runs val-e2e, plotly-e2e, corpus, real under flock serially. First command (val-e2e) is active with GPU as of 20:08 EDT.
- Progress log: `out/t4/step25-finish.log` (one `<task> done <ts>` line per completion).
- Completion marker: `out/t4/step25-finish.done`.
- Monitor task `bhfj1rwbz` armed on step25-finish.log for "done|start|Error|Traceback|FAILED" patterns.
- Partner curator (a6a58ff6a5e541736) running probe suite in parallel: dense/row/shapes/labels/hollow/multi/lines, each one-at-a-time via flock.

## Numbers already in hand (step25 vs v3)

Standard-set geometry (`--refine`):

| set | metric | v3 all / simple | step25 all / simple | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 | marker_recall | 0.593 / 0.845 | 0.605 / 0.858 | +0.012 / +0.013 |
| mpl-val 200 | marker_precision | 0.704 / 0.825 | 0.758 / 0.860 | +0.054 / +0.035 |
| mpl-val 200 | marker_err_median_pct | 0.128 / 0.112 | 0.087 / 0.071 | -32% / -37% |
| plotly 150 | marker_recall | 0.465 / 0.829 | 0.460 / 0.832 | -0.005 / +0.003 |
| plotly 150 | marker_precision | 0.798 / 0.819 | 0.851 / 0.891 | +0.053 / +0.072 |
| plotly 150 | marker_err_median_pct | 0.091 / 0.081 | 0.048 / 0.032 | -47% / -60% |

Still waiting on: val-e2e (ocr), plotly-e2e (ocr), corpus, real. REPORT will be updated when they land.

## Hypotheses still open

- val-e2e step25 should mirror geometry: precision up, err cut by ~30%, recall slightly up.
- plotly-e2e step25 should mirror geometry: precision up, err cut by ~50%, recall ~flat.
- corpus step25 median series err likely between 0.067 (v3) and 0.079 (step24) - the sem[TEXT] veto is unlikely to affect the Chart.js corpus (no digit-labeled series).
- real step25: women/men chart (03) should drop from 6 series to 4 (sem[TEXT] veto removes digit glyphs taken as markers).
- step25 vs step24 regression: -4.1pp val-all precision from skipping dash veto on line+markers. Expected tradeoff; still +5.4pp vs v3.

## Resume plan if usage window hits

1. Check if `out/t4/step25-finish.done` exists.
2. If yes, parse eval-*-step25.txt files, update REPORT.md with full before/after, commit, send main final message.
3. If no, check `out/t4/step25-finish.log` for the last `<task> done` line and resume from the next item. Script is idempotent across its four flock commands - restart it from scratch; completed outputs stay.
4. Watch for curator mail with probe step25 numbers. Fold into REPORT if available.
5. Final message to `main` with claim, before/after, HEAD, verification commands.

## Verification commands (post-submission)

From `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t4-markers/ml` with the venv active:

```sh
python -m pytest -q
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt
```
