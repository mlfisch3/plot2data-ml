# t2-trace brainstormer pause state

## Identity

Team: t2-trace. Role: brainstormer. Agent model: Opus 4.7 (xhigh effort). My agent id: (this session). Partner (curator) agent id: a2ebf18cb3759c1ce. Time of pause: Wed 28 Oct 2026, 17:28 EDT.

## Last-committed state

Branch: team/t2-trace. HEAD: 9be8e9c "t2-trace: use 1e9 not np.inf in cost matrix for linear_sum_assignment".
Submission commit: 4ab8ee0 "t2-trace: overlap-aware merge_fragments with Hungarian assignment".
Files I own under ml/p2d/: everything except p2d/synth/probe_t2*.py (curator's).
Only ml/p2d/extract.py and ml/tests/test_trace.py are modified vs 6b313e9 (extract.py has merge_fragments, _join_cost, _end_slope, and a scipy.optimize.linear_sum_assignment import; drop_duplicates is reverted to frozen).
Model, data, losses, evaluate, train carry the predecessor's direction-head scaffolding (committed in 9b97b78) which is dormant: evaluate.load_net sets dir_head=False when the checkpoint has no dir. weights (v3 doesn't), so no runtime effect.

Persistent notes:
- ml/teams/t2-trace/NOTES.md (chronological, dated, both agents write).
- ml/teams/t2-trace/CASES.md (curator maintains).
- ml/teams/t2-trace/REPORT.md (initial draft committed at bff8e88; needs updating with the full-sweep numbers as they land).
- ml/teams/t2-trace/mail/to-brainstormer.md and to-curator.md.
- ml/teams/t2-trace/tools/ for diagnostic scripts.
- out/t2c/ for every measurement; out/t2c/live-overlap-merge-v3/ for v3's "after" numbers.

## In flight when paused

1. Curator a2ebf18cb3759c1ce is running the full probe sweep (`t2c-measure-live.sh overlap-merge-v3 full`, pid 1103167). Done so far: val-refine, plotly-refine, cross, samecolour. In progress: parallel (started 17:01, GPU-contended). Pending: shallowx, legocclude, 12 more probes, val-e2e, plotly-e2e, corpus, real.
2. My own background monitors: bl0k1mtfs (waiting on val-e2e.txt - the key end-to-end result).

How to tell they completed: when out/t2c/live-overlap-merge-v3/<name>-refine.txt or <name>-e2e.txt is non-empty, that measurement is done.

Numbers for the committed v3 (geometry only, mpl-val 200):

| metric | frozen | v3 | delta |
|---|---|---|---|
| line_found (all) | 0.7570 | 0.7809 | +0.024 |
| line_found (simple) | 0.8859 | 0.8993 | +0.013 |
| line_cov_mean (all) | 0.6665 | 0.6879 | +0.021 |
| line_good_cov_mean (all) | 0.5884 | 0.6052 | +0.017 |
| line_rms_median_pct (all) | 0.311 | 0.285 | -0.026 |

plotly-v1 150: +0.013 found all, -0.009 found simple.
t2-cross 100: +0.010 found all.
t2-samecolour 100: +0.013 found.

## Hypotheses still open

1. The plotly-simple regression (0.9720 -> 0.9626, 2 of 79 charts regressed, pred counts rose) is the overlap-merge joining TWO GHOSTS of one real series into a longer ghost that then survives drop_duplicates. Guard would be: raise min_q from 0.3 to 0.4 for overlap-merge candidates, or require nov >= 50% * min(A.n, B.n) for the long-overlap branch.
2. drop_duplicates "ghost + real" (shallowx finding, 10% of column coverage lost in that probe at the final stage): a narrower envelope (window=2 instead of 4) could help, but every tried change exploded pred counts without found gain. The right fix is probably at the chain stage (peel_chains hop in a shared embedding cluster), not at dedupe.
3. The oracle cluster upper bound (0.91 found vs 0.78 now) is where the big residual lies. The direction-head + whole-ridge-graph tracker is the correct path.

## Pending experiments

1. If plotly-simple regression needs fixing: raise min_q to 0.4 or require nov/min(A.n, B.n) >= 0.5 in `_join_cost`. Then re-run mpl-val 200 + plotly-v1 150; expect found all to stay near 0.78 and plotly simple to recover to 0.97.
   ```sh
   python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --refine --json out/t2c/live-plotly-tight.json
   ```
2. End-to-end measurement to confirm the geometric gain propagates:
   ```sh
   python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
   python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
   ```
   This is in the curator's full sweep already; wait on their file.
3. Direction-head training (if time allows and the GPU lock is free):
   ```sh
   flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
     nice -n 19 python -m p2d.train --data data/mpl-v1 data/mpl-v2 data/plotly-train-x8 --val data/mpl-val \
       --run runs/t2-dirhead --init runs/v3/best.pt --iters 3000 --eval-every 1000 --workers 6
   ```
   Then write a direction-aware peel_chains that uses `out["dir"]` to pick continuations at crossings. Risk: regression without careful tuning.

## Mail unread

None pending in to-brainstormer.md. Curator's last two messages were acknowledged and acted on: dedupe pivot analysis and "ready for full sweep" cue. Curator is running the full sweep now and will relay as results land.

## Resume plan

1. Read ml/teams/t2-trace/NOTES.md tail and the curator's latest messages. Check out/t2c/live-overlap-merge-v3/ for new .txt files: parallel-refine, shallowx-refine, legocclude-refine, val-e2e, plotly-e2e, corpus, real.
2. Update ml/teams/t2-trace/REPORT.md with the new numbers under "Scoreboard" and "Generality and regressions". If any regression is large, add to "What did not work".
3. If end-to-end numbers show the geometric gain propagated (expect line_rms_median improvement), send the final message to the judge (main) with the claim + path to REPORT.md + verify commands.

Do NOT touch the merge_fragments code further unless a probe shows a REGRESSION large enough to retract the submission. The v3 is the ship-ready win; tinkering risks it.
