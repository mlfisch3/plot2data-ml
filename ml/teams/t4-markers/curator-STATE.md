# t4-markers curator - pause state

## Identity

- Team: t4-markers (markers and scatter plots)
- Role: curator (replacement; predecessor Fable 5.1 agent a1abc77f3414bcec7 was cut off ~02:30 EDT)
- Agent model: Opus 4.7, xhigh effort
- My agent id: not known to me; the pause message to "main" or main's own listing has it
- Partner: brainstormer a1d4346bed4bd4f04 (Opus 4.7)
- Judge: main
- Time of pause: Wed 28 Oct 2026, 17:30 EDT

## Last-committed state

- Branch: `team/t4-markers` at commit `847cf1d` ("t4: note that F10 and F11 were fixed in step24")
- Brainstormer's last commit on branch: `e4edf2b` ("t4: skip dash veto on line+markers, sem[TEXT] veto, iso elongation filter") - step25
- My own commits (newest first): `847cf1d`, `6d50c0b`, `5120274`, `727a933`, `32259eb`, `3cd6fe8`, `f140f94`, `72247be`
- Code states measured so far:
  - v3 (`runs/v3/best.pt` on frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml`): baseline
  - af04090 (= step23 in my naming): initial markers.py (brainstormer predecessor)
  - c78db3f (= step24): three guards (line-stroke gated, no_iso fallback, add_seeds cap)
  - e4edf2b (= step25): dash veto scatter-only, iso elongation filter, sem[TEXT] veto - **step25 eval incomplete** (val eval still running at pause)

### Files owned

- `ml/p2d/synth/probe_t4*.py` (probe generator)
- `ml/teams/t4-markers/CASES.md` (failure catalogue, 219 lines, comprehensive)
- `ml/teams/t4-markers/tools/` (my diagnosis scripts): `marker_diag.py`, `diag_delta.py`, `perchart_delta.py`, `verify_text_veto.py`, `probe_report.py`, `probe_suite.sh`, `suite_table.py`, `bias_check.py`
- `ml/tests/test_probe_t4.py` (probe generator invariant tests)
- Shared: `ml/teams/t4-markers/NOTES.md` (both agents write here), `ml/teams/t4-markers/mail/`

### Paths of persistent notes

- CASES: `ml/teams/t4-markers/CASES.md`
- NOTES: `ml/teams/t4-markers/NOTES.md`
- REPORT (brainstormer-owned): `ml/teams/t4-markers/REPORT.md`
- Mail to-curator: `ml/teams/t4-markers/mail/to-curator.md`
- Mail to-brainstormer: `ml/teams/t4-markers/mail/to-brainstormer.md`
- Final summary draft: `/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/final-summary-draft.md`

### Measurement artefacts

- Baselines (frozen tree v3): `ml/out/t4/base-{val,plotly}-{refine,e2e}-frozen.txt`, `ml/out/t4/eval-{dense,row,shapes,labels,hollow,multi,lines}-v3d.txt`, `ml/out/t4/diag-{val,plotly,dense,row,shapes,labels,hollow,multi,lines}-v3/summary.json`.
- Step23/step24 brainstormer evals: `ml/out/t4/eval-{val,plotly,dense,row,shapes,labels,hollow}-step24.txt`. Multi/lines/e2e step24 were abandoned (GPU thrash); step25 is supposed to cover them.
- Step23 (= af04090) per-marker diag: `ml/out/t4/diag-{dense,shapes,row}-step23/`.
- Step24 behaviour per-marker diag: `ml/out/t4/diag-{labels,hollow,multi,lines,val,plotly}-step23/` AND `-step24/` (same files - I copied to the step24 tag because the diag used step24 markers.py post-16:21:17 edit).
- Step24 corpus/real: `ml/out/t4/corpus-step24.txt` (small regression, +0.012%), `ml/out/t4/real-step24.txt` (byte-identical to v3).
- Returned-centre bias on isolated symmetric markers (step23 vs v3) demonstrates the snap back-out working correctly (val step24 abs median 0.71 px = 0.5 up-left of drawn centre = exact value position).

## In flight when paused

- Brainstormer's `bash ml/out/t4/step25.sh` (pid 1117022, child 1117026 `python -m p2d.evaluate ... mpl-val --refine ... rows-val-step25.json`), 16:10 elapsed when paused. The step25 full suite covers val, plotly, probe sets (dense/row/shapes/labels/hollow/multi/lines), val-e2e, plotly-e2e. Progress log: `ml/out/t4/step25.log` (currently "step25 start 1793221934" only). Completion marker: `ml/out/t4/step25.done`.
- No active jobs from my side. My diag-step25.sh (prepared, not yet launched) at `/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/diag-step25.sh` is waiting on brainstormer's eval.
- Monitor task `bt3g15hkg` was armed to notify when `val done` or `plotly done` appears in `ml/out/t4/step25.log`. Monitor task `bnuktydzz` was armed to notify when `ml/out/t4/eval-plotly-step25.txt` is non-empty.

How to tell if step25 completed: `ml/out/t4/step25.done` exists AND all `ml/out/t4/eval-{val,plotly,dense,row,shapes,labels,hollow,multi,lines,val-e2e,plotly-e2e}-step25.txt` are populated.

## Hypotheses still open

- Step25 Plotly recall will recover to ~0.83 simple (fix for 500134, 500021, 500099 line+markers dropped by the step24 dash veto).
- Step25 mpl-val recall will edge up (300+ TP recovered from 9000182/88/51/71 X/*/./x line+markers charts).
- Step25 labels precision will jump from 0.60 to ~0.75 (sem[TEXT] veto drops digit FPs on numbers_far mode).
- Step25 real 03-women-men chart will drop from 6 series (4 line + 2 scatter) to 4 series (just lines) due to sem[TEXT] veto. If so, the "26", "36", "46", "22" glyph marker artefacts are gone.
- Chart.js corpus error may still regress slightly on halo markers (hollow rings; ink_weight > 0.5 mask does not capture antialiased rim). A lower threshold or ring-sampling in attach_loose is a possible step26.

## Pending experiments (concrete commands and expected signals)

1. **After step25 eval lands**, run my prepared diag:
   ```sh
   bash /tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/diag-step25.sh
   ```
   Writes `ml/out/t4/diag-<k>-step25/` for val, plotly, labels, dense, row, shapes, hollow, multi, lines, plus `ml/out/t4/corpus-step25.txt` and `ml/out/t4/real-step25/`. Expected signal: labels precision up, plotly simple recall up, real 03 series count down to 4.

2. **Full before/after delta table**:
   ```sh
   cd ml && python teams/t4-markers/tools/diag_delta.py v3 step25
   ```
   Produces Markdown with per-set deltas and per-shape error breakdown.

3. **Per-chart delta on plotly step25** (critical catastrophe-free check):
   ```sh
   python -c "import json
   A = {r['id']: r for r in json.load(open('ml/out/t4/rows-plotly-base.json'))['rows']}
   B = {r['id']: r for r in json.load(open('ml/out/t4/rows-plotly-step25.json'))['rows']}
   for i in (500134, 500021, 500099, 500003):
       a, b = A[i], B[i]
       print(f'{i}: gt={a[\"n_markers_gt\"]} tp {a[\"marker_tp\"]} -> {b[\"marker_tp\"]}')"
   ```
   Expected: 500134 tp 186→~180, 500021 tp 85→~80, 500099 tp 41→~40, 500003 tp 20→~18. All recovered.

4. **Pytest check** before claiming done:
   ```sh
   cd ml && source ../.venv/bin/activate && python -m pytest -q
   ```
   Expected: 47 of 47 marker tests pass plus 4 of 4 probe tests.

## Mail unread

The last mail I sent to brainstormer was "killed my duplicate; your pid 1117026 is only one" at 17:29 EDT. No unread mail from brainstormer at pause time; their last was the "step25.sh IS still alive" correction.

## Resume plan (first three things the replacement should do)

1. Read this STATE file and SCRATCH; check `git log -5` to see if step25 eval or further commits landed; check `ml/out/t4/step25.log`, `ml/out/t4/step25.done`, and the `eval-*-step25.txt` sizes to tell if step25 completed during the pause.

2. If step25 completed, run `bash /tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/diag-step25.sh`. If it didn't complete, mail the brainstormer (`SendMessage to: a1d4346bed4bd4f04`) asking status; if the brainstormer is also paused, re-launch `bash ml/out/t4/step25.sh` and `tail` `ml/out/t4/step25.log` for progress.

3. After step25 diag done, update CASES.md with step25 numbers (new table rows beside step24), update NOTES.md with a dated entry, and commit. If the brainstormer has not updated REPORT.md with step25 numbers, send them the key data via SendMessage. Then send final summary to main (template in `/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/final-summary-draft.md`, with step25 numbers filled in).
