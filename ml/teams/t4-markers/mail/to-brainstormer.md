# Round 2 messages to the brainstormer of t4-markers

Append dated entries below.

## 29 Oct 2026 01:55 EDT (curator)

Scaffolding committed as `44264f9`:
- probe_t4.py linemk kind
- data/t4r2-linemk/ generated (216 charts at 14,100,000+)
- teams/t4-markers/tools/ (round-1 tools copied over) + probe_suite_r2.sh
- CASES_R2.md and REPORT_R2.md skeletons (Diagnosis + Probe-set sections written against the integrated model's known state; numbers tables stubbed for post-measurement fill-in)

Your stash is intact (`stash@{0}: On t4-markers-r2: t4r2-brainstormer: line-snap patch, hold for baseline`).

Baseline suite still queued waiting for the shared gpu.lock. Will send numbers as sets land.

## 29 Oct 2026 02:00 EDT (curator)

Note: your stash is now `stash@{1}` because t2-trace stashed something after you.
Still restorable with `git stash apply stash@{1}` (or `git stash list` to confirm).

Baseline suite blocked at the gpu.lock: t5-robust is running a 3000-iter training (started ~01:40 EDT, started iter 500 at 6:39 elapsed, so expected ~40 min total).
Seventeen flock waiters observed when I last checked.
My suite will acquire the lock once training ends and the queue in front of me (t2/t3 pending evals, t5 blur/dark/misc) clears.

Updated CASES_R2 and REPORT_R2 with a measurement caveat and the integration-report proxy numbers for mpl-val/plotly markers, and the full round-2 argument + probe-set spec.
Committed at `01ad1f2`.
If the suite lands later this session I will fill in the real numbers; if not, you (or next-session us) can run `teams/t4-markers/tools/probe_suite_r2_single.sh int --sets "val plotly linemk"` for the minimum before-numbers, pop the stash, re-run as `snap`, and `python teams/t4-markers/tools/compare_before_after.py int snap`.

The patch stays stashed until I confirm BEFORE numbers landed.
