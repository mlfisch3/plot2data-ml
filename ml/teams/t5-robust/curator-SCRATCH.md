# t5-robust curator scratch (chronological)

## 16:09 EDT, Wed 28 Oct 2026 - takeover

Replacement for a6cdf1f1dddf509f8 (Fable 5.1), cut off at ~02:30 by the account's usage limit. Opus 4.7 at xhigh effort. Branch head when I started: a7aed7d.

Working tree clean, no in-flight t5-robust job. Partner id for the new brainstormer: a861ce2f76eb7c6ac.

Activated usage_minder at 50% threshold (baseline 15,000,000 tokens, pause-trigger ~7,500,000 tokens left; `/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/usage_minder.json`).

Housekeeping rule: all `pgrep`/`pkill` patterns name `t5-robust` or specific pids only. Predecessor killed another team's queue once by using a non-team-scoped `pkill -f "gpu2[.]sh"`. I did not repeat that.

## 16:16 EDT - handoff written, numbers inventoried

Wrote dated NOTES.md handoff entry and `mail/to-brainstormer.md` 16:17 EDT reply. Confirmed existing probe-set and baseline numbers in `ml/out/t5/`. The predecessor's `q1-e2e-native.txt` and `q1-plotly-native.txt` ARE still current-code (no inference-touching commits since 259b09d - 36638e3 is training-only, 804b155 TTA defaults off, rest is non-inference). Brainstormer did not know this and would have re-run.

Found two concrete corpus regressions at a7aed7d that base lacks:
- `log-log` found 24/1 at a7aed7d-native vs 2/1 at base (ghost minor-log gridlines)
- `offset-annotation` 61.222% at a7aed7d, same as base (axis_factor fix did not fire)

Noted that `a7aed7d --fit-canvas` gives essentially base numbers on mpl-val and plotly; so the native pass is the whole gain, and the 259b09d bundle is a no-op on standard sets but useful elsewhere (OWID, offset-annotation under fit-canvas).

## 16:17 EDT - real-bench baseline shim

Wrote `ml/teams/t5-robust/tools/real_bench_pkg.py`. Loads `p2d` from the frozen `base/ml` (via P2D_ROOT env) and uses the live tree's `eval_t5real.py` as a module - with the three relative imports stripped - so the baseline measurement works even though the file doesn't exist in `base/ml`. Also handles the live tree's `native=` kwarg via `inspect.signature`; the baseline pipeline doesn't have it, so the shim calls `run(net, reader, img)` without extras there.

Added one test `test_real_bench_pkg_shim_loads_loader_without_relative_imports`. 38 tests pass.

## 16:25 EDT - queue7 launched

Queue7 waits for ZOOM_DONE then runs:
1. real-bench baseline via shim (base p2d + v3 ckpt) [done at 16:25:18]
2. a7aed7d --fit-canvas on mpl-val/plotly/corpus [done 16:27, 16:28, 16:28]
3. probe_net dumps for offset-annotation and log-log at a7aed7d [done 16:29]
4. chartjs-val at t5-zoom (e2e + pixel) [done 16:30, 16:32]
5. real-bench at t5-zoom [done 16:32]

Queue7 total: ~8 min.

## 16:29 EDT - probe-regr mechanism confirmed

The `offset-annotation` and `log-log` dumps gave concrete per-pixel evidence:

- offset-annotation: `1e6` box IS in loose_labels, src[10,2,24,22], 280 px, sem argmax=TICK_LABEL on 23% of its pixels. Geometry check in axis_factor PASSES (cy=12 < y0=17.6; `|cx-x0|=9.2 < 0.25*w=212`). So the box reaches axis_factor's `cands`. But no WARN fires at a7aed7d-native. Means `_MULT.match` on the OCR output failed. The 14x20 crop at native clips glyphs; the OCR reader returns garbage that doesn't match `^(?:x|\(x)?(?:1e([-+]?\d+)|10\^([-+]?\d+))\)?$`. At fit-canvas (0.853x) the box becomes ~12x17 and OCR reads "1e6" cleanly - a7aed7d-corpus-fit.txt gives offset-annotation 0.019% WARN "y axis: values scaled by the printed '1e6'". TTA shift fixes it at native by giving a half-pixel-shifted crop; brainstormer confirmed with tta-shift-corpus.txt 0.020%.

- log-log: 23 of 24 ghost series are minor-log gridlines (col 224,224,224). GRID-fracs: 0.12, 0.34, 0.20, 0.54, 0.36, 0.51, 0.11, 0.08, 0.01, 0.08, 0.44, 0.05, 0.38, 0.00, 0.04, 0.19, 0.00, 0.34, 0.45, 0.00, 0.41, 0.00, 0.00. Only 2 of 23 exceed the 0.5 threshold of `extract._mostly(f, sem[GRID] > 0.5, 0.5)`. At native scale 1.0 gridlines are 1 pixel wide; sem's softmax spreads probability across neighbors; ridge-centre pixels often land where sem argmax = BG. zoom's training fixes it.

Added these mechanism blurbs verbatim to CASES.md section 9.1.

## 16:35-16:40 EDT - submission numbers landing

mpl-val submission (brainstormer's TTA sweep): line_rms_median 0.280 (base 0.441, -36%), marker_precision 0.640 → 0.544 → 0.719 (zoom alone drops it, TTA shift's averaging recovers it + beats base).

plotly submission (brainstormer): line_rms_median 0.234 (base 0.250, -7%), marker_precision 0.772 → 0.852 (+8pp).

Chart.js corpus submission (brainstormer): median 0.072% (base 0.067, flat), worst 0.580% (base 61.222%). The log-log and offset-annotation collapse is the headline.

## 16:38 EDT - queue8 died

Queue8 was `set -e` and died at step 2 (`real-bench-sub`) because `eval_t5real.py` did not accept `--tta` yet. Error: "unrecognized arguments: --tta shift".

Fix: committed one-line addition to `eval_t5real.py` main (29763bd). All 7 team-5 tests still pass; 38 total.

Relaunched as queue9 at 16:47.

## 16:47-16:48 EDT - queue9 steps 1 and 2

Step 1 (real-bench-sub): done at 16:48:31. Numbers:
- submission: found 63%, median 0.75%, within-1% 42%, failures **14 (lowest)**.
- Dominates base on failures (base 15) and within-1% (base 28%). Median rms 2.9x better than base. Three OWID charts move from catastrophically wrong to within 0.5%.

Step 2 (dpr2-sub): started 16:48; still running at 17:57 (~70 min elapsed, 62 min CPU). GPU heavily contested by brainstormer's `runs/t5-chartjs` training launch + 4 other teams, each with eval processes. 17+ python evaluate processes contending for GPU memory at one point.

## 17:12 EDT - final message to main

Sent summary of diagnosis counts, before/after numbers across every set, and all paths. The submission (bd6a491) has already been accepted by the coordinator (per the brainstormer's 16:47 message).

Open loose end: CASES.md section 9.5 "Image-factor probes" still shows only base vs a7aed7d; submission column pending queue9's dpr2/blur/dark/clutter output.

## 17:57 EDT - pause

5-hour usage at 64%, below my 50%-of-local-token threshold (14.6M / 15.0M = 97% remaining), but the coordinator triggered pause on account-level 5-hour usage. Stopping Monitor tasks `bath4z6dl` and `bvuocpxlv` to avoid burning quota. queue9 (pid 1105800) left running in the background - it may complete during the pause.
