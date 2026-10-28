## Identity

- Team: t4-markers
- Role: brainstormer (replacement for a21fb6c74947efb61)
- My agent id: this current Opus 4.7 session (replacement at xhigh effort, invoked at ~16:00 EDT)
- Partner (curator): a7767959dd712ee11 (Opus 4.7)
- Time of pause: `Wed 28 Oct 2026, 17:30 EDT`

## Last-committed state

- Branch head: `e4edf2b` (step25) on `team/t4-markers`
- Branch commits I added:
  - `e8d312b` arrival/notes (replacement arrived)
  - `7ddcfc1` salvage note on predecessor state
  - `c78db3f` step24: fix line-stroke false veto and triangle fallback
  - `fb5f0b3` first REPORT.md with step24 numbers and step25 plan
  - `e4edf2b` step25: skip dash veto on line+markers, sem[TEXT] veto, iso elongation filter
- Files I own under ml/p2d/:
  - `ml/p2d/markers.py` (new, 555+ lines; measures markers on source pixels, mixture-of-Gaussians centres, Agg-snap convention, dash veto, triangle fallback). Current content includes step25 fixes.
  - `ml/p2d/extract.py` (modified at lines 18 and 289 to add sem[TEXT] filter at marker peak list and `ex.loose_markers` tracking).
  - `ml/p2d/zoom.py` (committed but NOT integrated into the pipeline; predecessor's wip step 1).
  - `ml/tests/test_markers.py` (11 tests; current).
- Persistent notes:
  - `ml/teams/t4-markers/NOTES.md`: predecessor's and curator's dated entries; mine at 16:11 EDT.
  - `ml/teams/t4-markers/CASES.md`: curator-owned, step23 and step24 progression.
  - `ml/teams/t4-markers/REPORT.md`: fb5f0b3; needs step25 numbers appended.
  - `ml/teams/t4-markers/salvage/a21fb6c74947efb61-excerpt.md`: salvage of predecessor's state.
  - `ml/teams/t4-markers/mail/to-brainstormer.md` and `mail/to-curator.md`: dated mailbox.
- Step number: step25 (committed `e4edf2b`); step25 eval in progress.

## In flight when paused

- Shell/bash: `ml/out/t4/step25.sh` (pid 1117022) is running; it has written only `step25 start 1793221934` to `out/t4/step25.log`.
- GPU job: `python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine --json out/t4/rows-val-step25.json` (pid 1117026) is still active; etime ~900+ seconds (15+ min) under heavy GPU contention. Not yet produced output in `eval-val-step25.txt` (0 bytes).
- Monitors: expired or armed to tail `step25.log` / `step25.done`.
- To tell if step25 completed cleanly: `[ -f ml/out/t4/step25.done ]` and `ml/out/t4/step25.log` lists each stage with a timestamp line.
- Expected after val completes: `plotly`, then probes `dense row shapes labels hollow multi lines`, then `val-e2e`, `plotly-e2e`, `corpus`, `real`. Each takes 2-15 min depending on GPU contention.
- Partner curator is standing by to fire their `diag-step25.sh` once at least mpl-val and plotly step25 eval are complete.

## Hypotheses still open

- Step25's sem[TEXT] veto will drop the women/men chart's digit FPs; real/03 series count will go from 6 to 2.
- Step25's dash-veto-on-scatter-only will recover 500134 and 500021 catastrophic plotly regressions (step24 recall 0.783 simple -> expected ~0.83 simple).
- Step25's iso elongation filter will keep line fragments out of the shape detection on line+markers series with iso < 3.
- Step25's dash veto change may let some FPs through on dashed lines misclassified as line+markers; the per-peak line-stroke veto (gated on `size <= stroke + 2.0`) should still catch dash-sized peaks there.
- The 500107 rope case (5 line+markers, 6081 markers, 931 TP v3 -> 708 TP step24) will probably not fully recover with step25 alone; needs zoom.py integration.
- Chart.js hollow halo markers' 0.08-0.10% error vs classical 0.02% is from antialiased ring edges below the ink_weight threshold (`w > 0.5`); a lower threshold or an edge-aware centroid would help.

## Pending experiments

- Finish the step25 eval suite (`ml/out/t4/step25.sh`) to collect:
  - `eval-val-step25.txt` / `eval-plotly-step25.txt` (geometry)
  - `eval-{dense,row,shapes,labels,hollow,multi,lines}-step25.txt` (probes)
  - `eval-val-e2e-step25.txt` / `eval-plotly-e2e-step25.txt` (e2e)
  - `corpus-step25.txt` / `real-step25/` (corpus and real)
- Expected signal: mpl-val simple recall >=0.85, precision >=0.87; plotly simple recall >=0.80 (should recover from 0.783); labels precision >=0.70 (from 0.60).
- After step25 numbers land, finalise REPORT.md with the final before/after tables.
- Candidate step26 (not scheduled but tested cheaply): `_colour_at` sampling from a 5x5 patch and taking the pixel most non-paper (fixes hollow marker loose peaks losing to the paper filter in `attach_loose`).

## Mail unread

Latest curator mails are all seen and acknowledged. No pending items.

## Resume plan

1. Check `ml/out/t4/step25.log` and `ml/out/t4/step25.done`. If step25.done exists, read all `eval-*-step25.txt` and update `ml/teams/t4-markers/REPORT.md` with final before/after.
2. If step25.sh is dead (pid 1117022 not alive) and some evals are missing, relaunch `nohup bash ml/out/t4/step25.sh > ml/out/t4/step25-wrapper.log 2>&1 &`. Idempotent: `set -e` + per-stage `done` log lines allow resuming by inspecting what's missing.
3. Send final message to `main` with step25 claim, numbers, REPORT.md path, branch name, verification commands.
