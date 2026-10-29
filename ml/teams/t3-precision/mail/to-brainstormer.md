# Round 2 messages to the brainstormer of t3-precision

Append dated entries below.

## Thu 29 Oct 2026, 02:40 EDT from curator

Status snapshot for the mailbox record (SendMessage is the primary channel; this is here for audit):

- probe generator `p2d.synth.probe_t3_r2` committed (9daca35, 79fad60)
- 1000-chart dataset `data/t3-ticks-r2` generated with 100% N hit rate across {3,4,5,6,8,10,12} and 259/1000 charts carrying a y-offset axis
- `CASES_R2.md` committed (458132b) with integration scoreboard, round-1 corpus wins/losses table, round-2 probe-set factor grid, and the tick-floor diagnosis
- helper `teams/t3-precision/scripts/t3r2_compare.py` committed (dcd4524) for probe before/after rows
- Diagnosis + Probe-set sections for REPORT_R2.md sent via SendMessage; your 1df698b folded them in. Thanks.
- Integ probe batch (run_integ_probes.sh, --refine --tta shift, no --ocr) queued on gpu.lock behind the training job and your three scoreboards. Will fill CASES_R2.md section 3 (`data/t3-peaks`, `data/t3-spikes`, `data/t3-ticks`, corpus) when it lands.

Blocker fixed: evaluate.py's `--tta` branch did not call `extract` + `refine`, which crashed geometry-only probe runs with an UnboundLocalError. Fix in a99c1fa (116 tests pass).

Final message to 'main' will drop once the integ probe numbers land.
