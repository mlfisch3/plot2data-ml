# t2-trace round 2 failure catalogue

Curator's record of what survived, what regressed, and what still bleeds after integration into `121ed4d` (`runs/t5-chartjs/best.pt` + `runs/ocr1/best.pt` + `--tta shift`).
Round-1 catalogue is `CASES.md`.
Round-2 measurements under `ml/out/t2r2/` (shared tree, round-2 fix applied) and the baseline-only `scratchpad/t2-baseline/ml/out/t2r2-base/` (integrated 121ed4d code, no round-2 fix).
Round-2 probe generator adds case `ghostpair` to `p2d/synth/probe_t2.py` at seed base 12,170,000.

## 1. Starting point: integrated 121ed4d

Headline on `plotly-v1 150` end-to-end with the integrated pipeline (`--tta shift --ocr`), reproduced on this worktree:

| metric (all / simple) | base v3 | T5 V2 iso | integrated 121ed4d |
| --- | --- | --- | --- |
| line_found | 0.754 / 0.776 | 0.799 / 0.897 | **0.825 / 0.925** |
| line_rms_median_pct | 0.250 / 0.184 | 0.230 / 0.159 | **0.206 / 0.145** |
| peak_err_median_pct | 1.34 / 0.42 | 1.08 / 0.31 | **1.01 / 0.27** |
| marker_recall | 0.418 / 0.762 | 0.414 / 0.824 | 0.403 / 0.824 |
| marker_precision | 0.772 / 0.783 | 0.869 / 0.913 | 0.795 / 0.912 |
| calib_x_within_0.5 | 0.947 | 0.960 | 0.993 |
| calib_y_within_0.5 | 0.860 | 0.893 | 0.887 |

Fresh plotly-v1 e2e measurement on `team/t2-trace-r2` at 121ed4d: line_found 0.8252 / 0.9252 - byte-identical to the integration report.

**Key observation**: the round-1 submission's `-0.019` plotly simple e2e regression (vs frozen v3) is NO LONGER PRESENT in the integrated model.
Plotly simple is now 0.9252 - above the T5 V2 isolated number (0.897), and 15 pp above frozen v3.
The t5 base's native-resolution reader and TTA shift together reshape the ridge heat enough that the weak ghost clusters (q 0.3-0.4) that drove 500106 and 500111 under v3 no longer form.
**Round-2 target A (ghost+ghost guard) therefore has no reproducible failure left to recover on the standard scoreboard.**

## 2. Residual losses the integration flagged

Three residuals from the integration report, ranked by size:

- **mpl-val line_found behind T1 isolated by 2.6 pp** (0.6616 vs 0.6876).
  Calibration-interaction: T1's gained calibration is partially lost when combined with t3's source-pixel measurement and t5's TTA shift (slight calibration jitter pushes some lines below the match threshold).
  Not merge-fragments territory; any `_join_cost` change moves this at most 0.015 (round-1's mpl-val simple e2e delta was +0.013 from the merge fix alone).

- **Plotly marker_recall `all` -1.6 pp vs base** (0.418 -> 0.403).
  309-series set, single-chart noise. Not merge-fragments territory.

- **Corpus median +0.02 pp** (0.067 -> 0.087%).
  t3's source-pixel bias on easy single-solid charts; worst case went from 61.222 to 0.214. Not merge-fragments territory.

What a round-2 merge-side change can plausibly reach: the plotly-simple-regression ticket.
Measurement (section 3) shows that ticket is already closed in the integrated model.

## 3. Round-2 submission guards: measurement at `b5f1a32`

The round-2 submission at `b5f1a32` tightens the long-overlap branch of `_join_cost`:

- `min_q`: 0.3 -> 0.4 (reject weak ghost clusters).
- Added `nov >= 0.5 * min(A.n, B.n)` (require the overlap to cover the bulk of the shorter chain).

Measured on `plotly-v1 150` end-to-end with the fix:

| metric | integ 121ed4d | integ + b5f1a32 fix | delta |
| --- | --- | --- | --- |
| line_found all | 0.8252 | 0.8220 | **-0.0032** |
| line_found simple | 0.9252 | 0.9252 | TIE |
| line_cov_mean all | 0.7760 | 0.7731 | -0.0029 |
| line_rms_median_pct simple | 0.1452 | 0.1452 | 0 |

Verdict so far: on the standard scoreboard, both guards are slightly over-restrictive on `all` (-0.003 line_found) and buy nothing on `simple`.
The deciding question is whether the new `ghostpair` probe shows a behavioural improvement that justifies keeping the guard as a defensive measure.

## 4. Round-1 probe set re-measurement on 121ed4d (baseline, no r2 fix)

Measured in a separate `git worktree` at 121ed4d (`scratchpad/t2-baseline/`), symlinked to the shared data and runs so numbers are directly comparable to the fix-side runs under `ml/out/t2r2/`.
`--refine --tta shift` on `runs/t5-chartjs/best.pt`.

Round-1 numbers are from `ml/out/t2c/v3-<probe>-refine.txt` (frozen v3, no overlap-merge fix) and `ml/out/t2c/live-overlap-merge-v3/<probe>-refine.txt` (frozen v3 + round-1 overlap-merge fix).

| probe (line_found all) | frozen v3 | r1 overlap | integ 121ed4d | d_integ-vs-r1 | d_integ-vs-frozen |
| --- | --- | --- | --- | --- | --- |
| ghostpair (new r2) | n/a | n/a | **0.9126** | n/a | n/a |
| parallel | 0.7100 | 0.8100 | **0.7150** | **-0.0950** | +0.005 |
| shallowx | 0.7576 | 0.8658 | _(pending)_ | | |
| legend | 0.8560 | 0.8971 | _(pending)_ | | |
| legocclude | 0.8179 | 0.8247 | _(pending)_ | | |
| multi | 0.6550 | 0.6567 | _(pending)_ | | |
| wide | 0.8722 | 0.8647 | _(pending)_ | | |
| area | 0.5600 | 0.5550 | _(pending)_ | | |
| cross | 0.9167 | 0.9267 | _(pending)_ | | |
| samecolour | 0.9000 | 0.9125 | _(pending)_ | | |
| dotted | 0.8714 | 0.8905 | _(pending)_ | | |
| steep | 0.8872 | 0.8910 | _(pending)_ | | |
| thin | 0.8533 | 0.8567 | _(pending)_ | | |
| small | 0.7000 | 0.7067 | _(pending)_ | | |
| dense | 0.9118 | 0.9191 | _(pending)_ | | |
| step | 0.8385 | 0.8490 | _(pending)_ | | |
| clipped | 0.8016 | 0.8054 | _(pending)_ | | |
| markers | 0.9167 | 0.9167 | _(pending)_ | | |

### Key finding so far

**parallel is a leading indicator**: integrated 121ed4d gives 0.7150 (essentially frozen v3's 0.7100), NOT r1 overlap's 0.8100.
The r1 overlap-merge gain of +0.100 on parallel measured against frozen v3 did NOT carry through to the integrated model.
Mechanism: the t5-chartjs native-resolution reader with TTA shift reshapes the embedding sufficiently that the "cluster boundary splits a ridge" pattern happens differently, so the long-overlap merge rule (built on frozen v3's embedding) finds fewer same-ridge pairs to join.
Implication for round 2: the whole long-overlap branch has reduced leverage under t5, so the r2 fix (which tightens that branch) is operating on a lever that has already lost most of its force.

**ghostpair baseline 0.9126** is in the borderline zone (above 0.90, below 0.95).
The ghost+ghost pattern does form on the integrated model (~16/183 series lost).
Ship decision for A rides on whether the fix at `b5f1a32` improves ghostpair by at least 0.03.

Comparison helper: `teams/t2-trace/tools/compare_r1_r2.py`.

**Expected pattern (will be verified when the batch lands):**
Round-1 wins came through t5-chartjs's embedding too (the ridge heat is the same mechanism); the integrated model should hold most of the +0.100 parallel / +0.108 shallowx / +0.041 legend wins and keep the overall mpl-val uplift.
The r1 regressions (area -0.005, wide -0.008) may or may not persist depending on how t5-chartjs re-balances flank clusters.

## 5. Round-2 probe: `ghostpair`

Target: provoke the long-overlap ghost+ghost pattern that drove round-1's plotly simple -0.019 e2e regression (seeds 500106, 500111 in plotly-v1), on seeds >= 12,170,000 under the shared probe harness.

Mechanism: when a line is drawn thick (3-5 pt source stroke, 4-8 canvas pixels at dpi 100-120) on a presentation-sized canvas, the matplotlib anti-aliased renderer paints paired "flank" ridges either side of the stroke centreline that the network picks up as weak clusters (q 0.3-0.5).
Both flank clusters span the same column range as the real line, with a near-constant y gap of 2-5 px.
The round-1 overlap-aware `merge_fragments` sees `|median| < 6`, `MAD < 1.2`, `drift < 2.5` across the overlap of two flank clusters and joins them into one longer chain that passes `drop_duplicates`.

Spec (`p2d/synth/probe_t2.py`, case index 17, seed base 12,170,000, committed at `431843a`):

- 1-3 series per chart, each spanning most of x range (n = 80..260).
- Thick strokes: `lw` 3-5 pt at dpi 100-120, so canvas-pixel stroke 4-8 px.
- Wide figures: `wpx` 900..1400, aspect 0.4..0.6 (presentation-shape).
- Smooth shapes (sines, trend_noise, poly, logistic, walk).
- Mix of solid, dashed, dashdot (matches 500106 / 500111 line styles).
- Plotly-presentation palette shifted into the probe colour pool so some charts have same-family colours (blue vs cyan, orange vs red) to raise the chance a ghost cluster of series A overlaps the real of series B.
- `ylim` padded 30% so each series fills the middle of the plot (ghost flanks sit inside the plot area, not clipped).

Verification: 100 charts generated at seeds 12,170,000..12,170,099 in `data/t2-ghostpair/`.
Sample mosaic in `ml/out/t2r2/ghostpair-samples.png`.

### Expected measurement outcomes and decision gates

- **Baseline ghostpair line_found >= 0.95**: ghostpair cannot repro the pattern on the integrated model -> defer A entirely, revert `b5f1a32`.
- **Baseline ghostpair in 0.70-0.90, fix line_found +0.03 or more**: probe demonstrates a well-defined behavioural improvement -> ship A as a defensive guard with the probe as justification.
- **Baseline ghostpair < 0.70 OR fix no better than baseline**: either the probe over-provokes (needs a tamer version) or the fix undershoots; both cases say defer A and move to a different submission.

## 6. Framing for round-2 angles

### A - ghost+ghost guard (brainstormer, submission `b5f1a32`)

Current signal:
- Plotly simple on the standard scoreboard: no gain (TIE).
- Plotly all: small cost (-0.003).
- Ghostpair probe: _(decides whether this ships as defensive guard)_.

### B - envelope-aware peak_err metric (brainstormer, in prototyping)

The idea: ridge pixels per column already carry (top_y, bot_y) in `extract.py`.
A metric-side change in `metrics.py` can score each predicted (col, y_center) against the closest of the three (y_center, y_top, y_bot) when the ground truth has multiple values per column (density > 1), without any inference change.
Upper-bound measurement before any code is the right first step: compute the ceiling on `mpl-val all` and `plotly-v1 all` using the existing `ridge_px` field.
If the ceiling closes more than 1 pt of peak_err_median gap, pursue the submission; else defer.

### Residuals the merge-side cannot touch
- mpl-val line_found deficit vs T1 isolated (-2.6 pp): calibration-interaction between t3 and t5.
- Plotly marker_recall `all` -1.6 pp vs base: noise, 309-series set.
- Corpus median +0.02 pp: t3 source-pixel bias on easy charts.

Round-2 diminishing-returns verdict: the integrated 121ed4d is already strong enough on t2-territory metrics that merge-side gains are hard-capped at a few tenths of a pp.
Realistic ship criterion: a probe-level demonstration (ghostpair >= +0.03) if the scoreboard delta is zero.

Thu 29 Oct 2026, 02:15 EDT (section 3 fix numbers from brainstormer's measurement; probe table pending; final decision after ghostpair baseline lands).
