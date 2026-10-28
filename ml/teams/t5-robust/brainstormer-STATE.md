## Identity

- team: t5-robust
- role: brainstormer
- my agent id: a861ce2f76eb7c6ac
- partner (curator) agent id: aecd7d976deafcfd6
- time of pause: Wed 28 Oct 2026, 17:57 EDT

## Last-committed state

Primary submission: bd6a491 on branch `team/t5-robust` (accepted by coordinator).
- Config: `runs/t5-zoom/best.pt` + a7aed7d-era code (pipeline changes 72d21cf, 259b09d, 36638e3, 804b155, 0b9ec67) + `--tta shift`.
- Report: `ml/teams/t5-robust/REPORT.md` (223 lines). Scoreboard numbers (base -> submission):
  - mpl-val line_rms_median 0.441 -> 0.280 (-36%); marker_precision 0.640 -> 0.719
  - plotly-v1 line_rms_median 0.250 -> 0.234 (-7%); marker_precision 0.772 -> 0.852
  - corpus median 0.067% -> 0.072%; worst 61.22% -> 0.58% (offset-annotation `1e6` factor read)
  - examples/real 03-women-men x axis linear (was log), 5 series (was 6)
- Full failure catalogue and ablation: `ml/teams/t5-robust/CASES.md` (sections 1-9.9).
- Tests: 31/31 pass at bd6a491.
- Verification commands (from `ml/`, with `../.venv/bin/activate`):
  - `python -m p2d.evaluate --ckpt runs/t5-zoom/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --tta shift`
  - `python -m p2d.evaluate --ckpt runs/t5-zoom/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt --tta shift`
  - `python -m p2d.eval_corpus --ckpt runs/t5-zoom/best.pt --ocr runs/ocr1/best.pt --tta shift`
  - `python -m p2d.eval_real --ckpt runs/t5-zoom/best.pt --ocr runs/ocr1/best.pt --tta shift`
  - `python -m pytest tests/test_core.py`

Experimental branch (OPTIONAL deeper submission): `team/t5-robust-chartjs` at 594bfd1.
- Branched off bd6a491. Only addition over bd6a491 is `ml/teams/t5-robust/REPORT_V2.md` (47-line skeleton with placeholders).
- No source changes. The experiment is to add `data/t5-chartjs` to the training mix and measure whether a chartjs-aware fine-tune of `runs/t5-zoom/best.pt` beats V1 on all four scoreboard sets (plus the chartjs-val probe).

Baseline comparison tree (read-only): `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` at commit 6b313e9 + v3 ckpt.

## In flight when paused

- **V2 chartjs fine-tune training**: pid 1109938 (python) under flock pid 1109937. Still running at 61 min elapsed when I paused. Target: 3,000 iters, `--eval-every 1000`, `--zoom 0.35`, init from `runs/t5-zoom/best.pt`, data mpl-v1 + mpl-v2 + plotly-train-x8 + t5-chartjs (67,385 samples).
  - Launch script: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t5-robust/ml/out/t5/chartjs-train.sh`
  - Log: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t5-robust/ml/out/t5/chartjs-train.log` (currently only "train 67385 val 1000"; iter JSON goes to the file below)
  - Iter JSON: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t5-robust/ml/runs/t5-chartjs/log.jsonl` (empty when I paused; first entry appears at it=1000 and `best.pt` / `last.pt` are written there too)
  - Expected completion: ~140 min total under t5-zoom pacing but GPU is heavily contended by other teams' evals; may take 180-240 min.
  - To check completion: `cat ml/runs/t5-chartjs/log.jsonl` should show it=1000, 2000, 3000 lines; `ls ml/runs/t5-chartjs/best.pt` exists when training is done; `grep CHARTJS_TRAIN_DONE ml/out/t5/chartjs-train.log` is the sentinel.

- **V2 scoreboard evaluation (NOT yet launched)**: Script ready at `ml/out/t5/chartjs-eval.sh`. Measures `runs/t5-chartjs/best.pt` on all four scoreboard sets + chartjs-val, with `--tta shift`. Writes to `out/t5/chartjs-{corpus,real,mplval,plotly,chartjsval}.{txt,err,rows.json}`.

- **Floor-plotly eval**: ABORTED (I ran `pkill -f "[t]5-zoom.*floor-plotly"` at ~17:12 EDT to free GPU for V2 training). The frame-floor patch is already reverted (not in bd6a491); the mpl-val measurement showed it was a no-op and that is captured in REPORT.md section 8 and the "Next steps" item about tick-anchor-hull. No action needed.

- **Monitors I have active at pause**: One Monitor at task id `b3h19tukr` (chartjs iter progress), and one bg bash task `b5y3xhu3w` (waits for log.jsonl non-empty). I will TaskStop both before idling as the pause note instructed.

## Hypotheses still open

- The V2 chartjs fine-tune should fix:
  - `nogrid` corpus 0.19% (y-tick label-bias) -> expected <0.05%. Mechanism: chartjs training teaches em-box label convention; v3's -1.04 px bias on unsnapped chartjs y ticks disappears (`out/t5/tick-bias-v3.txt`).
  - `chartjs-val` frame_found 0.89 -> 0.93+ because chartjs charts now have TRAINING-DISTRIBUTION frames.
  - FRED and OWID y-axis calibration errors on real screenshots (same bias mechanism; see CASES section 9.7).
- Risks: slight regression on mpl-val or plotly where chartjs convention conflicts (digit-centre vs em-centre). The chartjs portion of training is 4,000 / 67,385 = 5.9% of the mix, small enough that a hard regression is unlikely but a 1-2 pp shift is possible.
- A tick-anchor-hull fallback in `plot_frame` (the frame must contain >=70% of detected tick anchors, else use the hull of the ticks) is the real fix for the mpl-val frame_err_p90 regression (base 13.2 -> submission 20.7 px). I did NOT ship this in V1 or V2 - code change, needs its own measurement cycle. Flagged in REPORT.md section 8.

## Pending experiments

Only the V2 experiment is in flight. If V2 beats V1 on all four scoreboard sets, V2 becomes the deeper submission on `team/t5-robust-chartjs` with REPORT_V2.md filled in. If V2 misses on any scoreboard set, V1 (bd6a491) stands and V2 is noted as a negative result in REPORT_V2.md.

Follow-up ideas, not scheduled, from REPORT.md section 8:
- Widen OCR crop pad in `axis_factor` from (2,2,2,2) to (4,4,4,4) specifically for multiplier crops (strictly-better fix for offset-annotation than --tta shift; already in Next steps).
- Tick-anchor-hull frame fallback.
- Lower sem[GRID] threshold in `_mostly` from 0.5 to 0.3 as a safety net.
- Chroma/ink channel canonicalisation (coordinator asked to hold this for after the contest).
- `parse_value` fallback for unit-word labels ("80 years"), unlocks OWID family in real benchmark.

## Mail unread

Nothing. Last curator inbound at 16:32 EDT (real-bench baseline shim and three-chart OWID wins) was read. My last outbound at ~17:00 EDT announced V2 training. Curator was running queue9 and committing section 9 updates; their latest commits (bd6a491's parents) are 760afa3, 1c01ff3, 29763bd.

If any curator mailbox entry appears while I am idle, the resumer should read `ml/teams/t5-robust/mail/to-brainstormer.md` for anything after the 16:17 EDT entry.

## Resume plan (first three things)

1. Check training completion: `ls ml/runs/t5-chartjs/log.jsonl ml/runs/t5-chartjs/best.pt && cat ml/runs/t5-chartjs/log.jsonl`. If `best.pt` exists and log.jsonl shows it=3000 (or at least it=2000 with converged val loss), training is done; move to step 2. If still running, re-arm a Monitor on `ml/out/t5/chartjs-train.log` with filter `"it":|CHARTJS_TRAIN_DONE|Traceback|Error|FAILED|Killed|OOM` and keep working on something else.
2. Launch V2 scoreboard eval: `nohup bash ml/out/t5/chartjs-eval.sh > ml/out/t5/chartjs-eval.log 2>&1 &`. Monitor on CHARTJS_EVAL_DONE and the `^---` headers. Expect ~30-60 min on the submission's `--tta shift` config.
3. Compare V2 vs V1 numbers side by side; update REPORT_V2.md's section 2 placeholders. If every scoreboard metric is non-worse than V1 AND at least two metrics are measurably better, commit REPORT_V2 fully and message main that V2 is the deeper submission on `team/t5-robust-chartjs`. If V2 regresses on any scoreboard set, note the trade honestly in REPORT_V2 and leave `team/t5-robust` (bd6a491) as THE submission.

Rules reminder: never touch `team/t5-robust` or its REPORT.md unless you want to supersede the primary submission; keep probes in `data/t5-*`, runs in `runs/t5-*`, pkill patterns always with `[t]5` in a bracketed match naming the team; GPU training through flock.
