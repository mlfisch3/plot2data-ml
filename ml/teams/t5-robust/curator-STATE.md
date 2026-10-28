# t5-robust curator pause-state snapshot

## Identity

- team: t5-robust
- role: curator (Opus 4.7 replacement after Fable 5.1 a6cdf1f1dddf509f8 was cut off ~02:30 EDT)
- my agent id: aecd7d976deafcfd6
- partner id: a861ce2f76eb7c6ac (brainstormer, Opus 4.7)
- time of pause: Wed 28 Oct 2026, 17:57 EDT (5-hour usage at 64%, ~100 min to reset)

## Last-committed state

Branch team/t5-robust, latest curator commit 760afa3 (brainstormer landed 594bfd1 on top with the REPORT_V2 skeleton).

Head: `594bfd1 t5: REPORT_V2.md skeleton for the chartjs-aware fine-tune pivot`.

Curator deliverables committed:
- `ml/teams/t5-robust/CASES.md` through section 9.9 (full ablation grid: base / a7aed7d / zoom / submission; probe-regr mechanism blurbs; probe-set tables; real-benchmark table; submission summary). Submission column in sections 9.1, 9.2, 9.7, 9.8 is filled; section 9.5 (image-factor probes) still shows base vs a7aed7d - submission column pending queue9.
- `ml/teams/t5-robust/tools/real_bench_pkg.py` - sys.path shim that scores the real benchmark through a frozen base p2d package while using the live-tree loader; replaces the predecessor's broken `python -m p2d.eval_t5real` from the base worktree.
- `ml/teams/t5-robust/tools/probe_net.py` - enhanced with per-loose-label sem class membership and per-series GRID-fraction (used for probe-regr dumps).
- `ml/p2d/eval_t5real.py` - now accepts `--tta`.
- `ml/tests/test_t5.py` - added `test_real_bench_pkg_shim_loads_loader_without_relative_imports`; 7 team-5 tests, 38 total pass.
- Baseline + a7aed7d + zoom numbers for all probe sets and the real benchmark are in `ml/out/t5/` (gitignored directory).
- NOTES.md has a dated 16:16 EDT entry recording the handoff and plan.
- Mailboxes: `mail/to-brainstormer.md` 16:17, 16:27 entries; `mail/to-curator.md` is the predecessor's one 01:50 entry.
- Final message was sent to `main` summarising diagnosis counts, before/after numbers, and all paths.

## In flight when paused

- `t5-gpu-queue9.sh` (pid 1105800, bash) is running step 2 (dpr2-sub) under submission config (`runs/t5-zoom/best.pt + --tta shift`). The dpr2 python child is pid 1106431 at 62 min CPU time (started 16:48 EDT, now 17:57), state Running. Severe GPU contention from the brainstormer's `runs/t5-chartjs` training + 4 other teams; one chart batch takes 10x normal time.
- queue9 completed real-bench-sub at 16:48:31 (visible in `ml/out/t5/t5-gpu-queue9.log` and the full output in `ml/out/t5/real-bench-sub.txt`: found 63%, median 0.75%, within-1% 42%, failures 14 - LOWEST of base/a7aed7d/zoom/submission).
- queue9 remaining steps after dpr2-sub: `blur-sub`, `dark-sub`, `clutter-sub` (each 100 charts with `--tta shift`; expected ~5-10 min each uncontested, up to 30 min each contested).
- queue9 writes `ml/out/t5/<set>-sub-e2e.txt` for each; the final sentinel is `T5_QUEUE9_DONE` in `ml/out/t5/t5-gpu-queue9.log`.
- Also still in flight on the branch (brainstormer's): a Chart.js-aware fine-tune on branch `team/t5-robust-chartjs` writing `runs/t5-chartjs/best.pt`; the brainstormer owns this and REPORT_V2.md.
- My Monitor tasks have been stopped: `bath4z6dl` (waited queue8_done, now defunct since queue9 took over) and `bvuocpxlv` (waited queue9_done).

## Hypotheses still open

- The frame_err_p90 regression at native mode is driven by strong-but-wrong corner peaks on frameless styles, not weak corner peaks (brainstormer's measurement reverted their floor patch). A tick-hull frame prior is the fix the brainstormer wants to try post-pause.
- Chart.js y-label bias (-1.04 px, 52% beyond 1 px on unsnapped y ticks) is largely untouched by the submission ingredients. The brainstormer's t5-chartjs fine-tune should correct it.
- queue9's remaining probe-set submission numbers (dpr2 / blur / dark / clutter) are expected to track mpl-val (line_rms_median -36%, marker_precision +6pp). Dark and clutter are the two with the biggest a7aed7d-over-base deltas; TTA may further help marker_precision.

## Pending experiments

- `teams/t5-robust/tools/real_bench_pkg.py` with the `--tta` flag now that eval_t5real accepts it: a direct submission measurement is already in `real-bench-sub.txt`; no separate shim run needed.
- When queue9 finishes, update CASES.md section 9.5 "Image-factor probes" with the submission column (same shape as section 9.2 chartjs-val update).
- If the brainstormer's `runs/t5-chartjs` training finishes, measure its Chart.js-val numbers (expected: yticks_err_median_px below 0.4, calib_y_within_0.5pct above 0.85).

## Mail unread

Nothing unread. The most recent message I received from the brainstormer was about launching the Chart.js-aware fine-tune on `team/t5-robust-chartjs`; I did not need to act on it (brainstormer owns that branch).

## Resume plan

1. Check `ml/out/t5/t5-gpu-queue9.log` for `T5_QUEUE9_DONE`. If present, read `ml/out/t5/{dpr2,blur,dark,clutter}-sub-e2e.txt` and append a submission column to CASES.md section 9.5 (format of section 9.2 is the model: `| set | base | a7aed7d | submission |`). Commit.
2. If queue9 is still alive and probe-set outputs are partial, let it run; measure what's there and add a short note that the rest will land asynchronously.
3. If queue9 died while idle, restart it: `nohup bash ml/out/t5/t5-gpu-queue9.sh > ml/out/t5/t5-gpu-queue9-stdout.log 2>&1 &` (the script writes idempotent output files; existing files are only skipped by probe_t5 generator, not by evaluate; expect it to re-measure the entries it already has).

After the resume plan: check if the brainstormer's t5-chartjs training has finished; if so, measure on Chart.js-val and real-bench and update CASES.md with a V2 column.
