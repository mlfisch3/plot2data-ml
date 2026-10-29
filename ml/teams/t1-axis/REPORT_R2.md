# t1-axis round 2: deferred

## Verdict

**Defer.**
After round 1 moved mpl-val both-axes-within-0.5% from 67.5% to 83.0% (+15.5 pts) through
`axis.py`'s joint decoder, source-pixel label boxes, explicit multiplier search, and 90-degree
crop de-rotation, the integrated axis path (branch `integration/round-1`, HEAD `121ed4d`) sits
at `calib_x_within_0.5pct = 0.9050` and `calib_y_within_0.5pct = 0.8950` on mpl-val.
The round-1 CASES ceiling (true ticks + true texts through parser + fitter) is **0.985 / 0.910**:
x has 8 charts of head-room, y has only 1-2 charts. The gap is dominated by **box errors +
OCR errors**, not by anything the structured decoder can rescue, and we are inside the diminishing
returns the brief flagged.

Each of the five angles the judge laid out was sized against this ceiling and the per-chart failure
list below. **None of them, taken alone, clears the ~1 pt bar on the standard scoreboard without
substantial new code**:

| angle | expected standard-scoreboard gain | cost | notes |
| ---   | ---                               | ---  | ---   |
| A no-grid bias           | **< 0.3 pt** (mpl-val line_rms_median, 1-2 corpus charts) | moderate | integrated already took `linear-single-nogrid` 0.194 -> 0.126%; one chart left to squeeze. |
| B1 45-degree deskew only | **~ 0.5 pt** (1 x-axis fixed) | moderate | mpl-val has one clear 45-deg case (9000014); probe `t1-rot45/x` stuck at ~0.85 but zero mpl-val signal beyond that. |
| B2 OCR retrain w/ rotated+anti-aliased+superscript aug | **1-2 pt (uncertain)** | **substantial** (data pipeline change + ~15 min GPU train + export + validation) | current OCR skips 90-deg crops at `_cut_crops`; rotation aug not in training. Could in principle lift reader on 3-5 of the ~20 mpl-val OCR-limited failures, but any single one of them is as likely a box issue as a reader issue. High variance, no guaranteed +1 pt. |
| C two-label log tiebreak | **< 0.3 pt** | small | round 1 already took `t1-two_log/y` 0.575 -> 0.975, `/x` 0.650 -> 1.000. The 4 remaining "two-label log" mpl-val y-axes are now OCR failures (e.g. 9000044 `['1e0','1e1']` -> `['1e1','0']`), not tiebreak failures. |
| D date improvements      | **0 pt on mpl-val** (no date axes), ~0.3 pt plotly-v1 x | moderate | 65% of `t1-dates/x` probe fails is a probe-only gap. Plotly-v1 calib_x already at 0.9933 in integration. |
| E axis-title unit parsing | **0 pt on mpl-val** | moderate | mpl-val JSON has no `xlabel/ylabel/title`; axis-title unit parsing has no scoreboard metric that reads it. Plotly-v1 has some, but the metric for plotly uses chart series pos->value, not axis-title words. |

Full write-up of each angle in **Diagnosis** below.

Branch: `team/t1-axis-r2` at the integration/round-1 base. No code change this round.

## Scoreboard before / after

Same code before and after; the two columns are identical.

### End-to-end, mpl-val 200 (`runs/t5-chartjs/best.pt` + `--tta shift`, from the integration report)

| metric (all / simple) | before = after (integration/round-1) |
| --- | --- |
| line_found          | 0.6616 / 0.7517 |
| line_rms_median_pct | 0.3076 / 0.2101 |
| peak_err_median_pct | 1.3504 / 0.2253 |
| calib_x_within_0.5  | 0.9050 |
| calib_x_scale_ok    | 0.9550 |
| calib_y_within_0.5  | 0.8950 |
| calib_y_scale_ok    | 0.9650 |

### End-to-end, plotly-v1 150

| metric (all / simple) | before = after |
| --- | --- |
| line_found          | 0.8252 / 0.9252 |
| calib_x_within_0.5  | 0.9933 |
| calib_y_within_0.5  | 0.8867 |

### Chart.js corpus, 25 series

| metric | before = after |
| --- | --- |
| median | 0.087% |
| worst  | 0.214% |
| failed | 0 |

### Real screenshots

Unchanged from the integration report: 01-panel1 x/y 0.82/1.89 px, 01-panel3 x/y 0.85/1.32 px,
etc. No regressions; no improvements.

## Diagnosis

### What's actually failing on mpl-val axes

Reclassified from the round-1 isolated per-axis diagnostic
(`/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml/out/t1/abl-mpl-v5.json`, 22 y failures,
19 x failures - the integrated tree has 1 fewer y failure and the same x fails, per the
integration report's calib numbers):

- **OCR errors on correctly boxed labels** (~15 charts): e.g.
  `9000027 y ['1e4','1e5'] -> ['1e5','11e4','cn1']`,
  `9000090 y ['1e1','1e2','1e3'] -> ['1e22','1e32','1e12']` (invented extra digits),
  `9000073 y signs swapped`, `9000160 y '-4e+01' -> '4e+01'`,
  `9000176 y '0%/10%/20%' -> ''/'60%'/'60%'`,
  `9000089 x '1,000' -> ',00'`, `9000136 x '1.925e+03' -> '1.025e+03'`
  (leading digit substituted),
  `9000169 x '1940/1960' -> '1040/1060'`.
- **Box issues (leading glyph cut, overgrown into neighbour)**:
  `9000014 y 25/75 -> -51/151 (overgrown)`,
  `9000098 x 100.0/105.0 -> 00000/100.0 (overgrown)`,
  `9000162 y '-50/0/50' pred '0.0/8/500'`,
  `9000121 x '1970/80/90' pred '-50/1990/1980' (y label taken as x corner)`.
- **Multiplier applied wrong**: `9000153 y '1e-6' not applied`, `9000169 y '1e6' not applied`
  (round 1's "what did not work" entry).
- **Geometry / tick position on small charts** (~2 charts, CASES class 8, explicitly outside this team's area).
- **45-degree rotation**: `9000014 x '872.25/.30/.35' -> '72.25/.30/.35'` (one chart).
- **Nofit / all-None reads** (~3 charts): e.g. `9000158`, superscript crops reading as None.

The lion's share is OCR + boxes. The joint decoder (`axis.py`) can already rescue second-reading
cases and does so; the remaining ones are too much garbage in to recover.

### Ceiling arithmetic (why gains are capped)

From round-1 CASES.md Table 1 (frozen base, mpl-val 200):

| | x within | y within |
| --- | --- | --- |
| current integrated | 0.905 | 0.895 |
| oracle: true text on predicted ticks | 0.925 | 0.835 (**the integrated BEATS this via joint decode**) |
| oracle: true ticks + true texts through fitter | 0.985 | 0.910 |

- **y** has only ~2 charts of ceiling head-room on the standard scoreboard (0.895 -> 0.910).
  Anything taking it above 0.910 requires beating the fitter oracle, which `axis.py` already
  does by 6 pts; another jump would need a smarter decoder that rejects outlier labels better,
  but round 1 already did the obvious wins (nice-step, progression, two-label tiebreak).
- **x** has ~8 charts head-room. The 19 failures split roughly 8 OCR, 7 boxes, 2 geometry,
  1 rotation, 1 nofit. Fixing 2 charts = +1 pt; fixing 4 charts = +2 pt. Non-trivial.

### Each angle in detail

**A. No-grid axis label-tick bias**.
Idea: measure label-to-tick offset on axes that have gridlines, apply the measured offset to
no-grid axes. One-chart measurement, no training.
Sizing: integrated already took the Chart.js `linear-single-nogrid` from 0.194 -> 0.126%
(team 5's chartjs training did it). The matplotlib "no-grid" case was never a per-chart
scoreboard entry; it folds into `line_rms_median_pct = 0.3076` as a sub-component. Fully
closing it (0.126 -> 0.030 on one corpus series) moves the corpus median by ~0 and mpl-val
`line_rms` by maybe 0.02 pts, well under the 1-pt bar. **Deferred.**

**B. Rotated-label tick reader accuracy**.
Two sub-angles.

- **B1 (deskew-only, 10-45 deg)**: compute the principal angle of ink in a tick-label crop,
  apply an affine un-rotate before the reader. Round 1's `normalise_crop` already does
  90-degree; 45-degree needs an extra ~50 lines. mpl-val signal is one chart (9000014);
  expected gain 0.5 pt. **Below bar.**

- **B2 (OCR retrain with rotation + anti-alias + superscript augmentation)**: the current
  `LabelCrops._cut_crops` SKIPS 90-degree-rotated boxes (`if (b[2]-b[0]) < (b[3]-b[1]) * 0.9`),
  and `__getitem__` has no rotation aug. Retrain `runs/ocr1r2-*` from `runs/ocr1/best.pt`
  with (a) rotated-label crops included, rotated to horizontal on the fly, (b) a 10-45 deg
  augmentation applied, (c) heavier scale and blur jitter to simulate tiny labels, (d) 10^k
  superscript augmentation.
  Sizing: ~15 min GPU train (user confirmed). Could lift OCR exact-rate on hard crops by
  2-5 pt, which may or may not surface on mpl-val as 2-4 fewer failing axes (half the OCR
  failures are also box failures, where retraining does nothing). **Uncertain gain, with
  training cost + export + validation it is "substantial new code" by the brief's standard,
  so DEFERRED** until there is a cheaper way to size the expected mpl-val delta ahead of training.

**C. Two-label log vs linear tiebreak**.
Round 1 added `_two_log_bonus` in `decode_axis` and the probe shows 0.975 within.
The 4 residual two-label-log y axes in the integration are all **OCR** failures - the pair
`['1e0','1e1']` becomes `['1e1','0']` and the tiebreak never sees two decades. No tiebreak
sharpening can rescue them. **Below bar.**

**D. Date axis improvements**.
mpl-val has zero date axes (`t1-dates` is a probe-only style). Plotly-v1 x already saturates
calib (0.9933). Scoreboard impact: 0 pts on mpl-val, maybe 0.3 pt on plotly-v1 x. **Below bar.**

**E. Axis-title unit parsing**.
mpl-val JSON carries no `xlabel/ylabel/title`; the standard metric compares pipeline-fit
values to the ground-truth tick values which are already in SI units. Scoreboard impact:
0 pt on mpl-val, uncertain and probably 0 pt on plotly-v1. **Below bar.**

## Implementation

None.

## Generality and regressions

N/A - no code change.

## What did not work

See **Diagnosis**: five angles were sized, none cleared the diminishing-returns bar, and the
one angle with a plausible > 1 pt ceiling (B2 OCR retrain) crosses into "substantial" and is
too uncertain to justify.

## Next steps (if someone invests round-3+ cycles here)

Ranked by expected payoff per unit of work:

1. **OCR retrain `runs/ocr1r2-` with rotation + superscript aug** (angle B2). If paired
   with a before/after per-crop OCR exact-rate on `data/mpl-val` crops first, you can size
   the expected mpl-val delta before committing to the full retrain. Likely +1-2 pt on
   mpl-val calib_x_within if it works.
2. **Better box recovery on the "leading glyph cut" / "overgrown" cases** (CASES class 12).
   `label_from_source` already uses `band_ink = raw_ink`; the residual charts (9000014,
   9000098, 9000162) show the per-glyph grouping along the axis is still greedy. A principled
   fix: detect anchor glyph columns under each tick position and grow outward with a
   per-tick gap tolerance, instead of merging all axis ink in one pass. Not small.
3. **Second-pass multiplier search for cluttered axis ends** (9000169 `1e6` in a noisy
   corner). Round 1's `_end_search` requires a clean ink band; a learned detector or a
   small template search for `[0-9]+e[+-]?[0-9]+` text patterns would unstick it. +0.5 pt
   bounded by the 1-2 remaining multiplier charts.
4. **E2E rotation handling for 10-45 deg** (angle B1). Only pays if combined with OCR
   retrain that saw rotated samples; alone it moves one chart.
5. **Dates and axis-title units** (angles D, E). Useful for product users on real charts,
   but neither is on the standard scoreboard. Would need a dedicated real-chart gallery
   bench to measure.

## Verification

- Branch tip: `team/t1-axis-r2` at integration/round-1 (`121ed4d`); no code change.
- `python -m pytest` on this branch: **110 passed** (checked at round start; identical to
  integration/round-1 since no files changed).
- Standard scoreboard numbers taken from
  `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integration/ml/out/integ/{mpl-val,plotly-v1,corpus,real}.txt`.
- Per-axis failure classification derived from
  `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml/out/t1/abl-mpl-v5.json`
  (round-1 isolated), cross-referenced with the integration report's calib deltas (integrated:
  calib_y_within 0.8950, T1 isolated: 0.8750; so integrated has 1 fewer y failure than this list).

Thu 29 Oct 2026, 01:22 EDT
