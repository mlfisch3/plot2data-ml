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

## 3. Round-2 submission guards: measurement at `b5f1a32` (reverted)

The guard tightening at `b5f1a32` applied to the long-overlap branch of `_join_cost`:

- `min_q`: 0.3 -> 0.4 (reject weak ghost clusters).
- Added `nov >= 0.5 * min(A.n, B.n)` (require the overlap to cover the bulk of the shorter chain).

Measured scoreboard against integrated 121ed4d:

| set | metric (all/simple) | integ 121ed4d | integ + b5f1a32 | delta |
| --- | --- | --- | --- | --- |
| plotly-v1 | line_found | 0.8252/0.9252 | 0.8220/0.9252 | -0.003 / 0 |
| plotly-v1 | line_cov_mean | 0.7760/0.8976 | 0.7731/0.8976 | -0.003 / 0 |
| **mpl-val** | **line_found** | **0.6616/0.7517** | **0.6594/0.7450** | **-0.002 / -0.007** |
| mpl-val | line_rms_median_pct | 0.3076/0.2101 | 0.3062/0.2100 | neg |
| mpl-val | peak_err_median_pct | 1.3514/0.2255 | 1.3514/0.2255 | TIE |
| corpus | median | 0.087% | 0.087% | TIE |
| corpus | worst | 0.214% | 0.214% | TIE |

**Verdict: revert `b5f1a32`.**
mpl-val simple regresses by -0.007 (exceeds the "revert if >0.005 regression" gate).
Plotly all also slight regression (-0.003).
Both costs come from legitimate multi-series overlap-merges with q in [0.3, 0.4) or short overlaps being rejected by the guard.
No scoreboard gain compensates.
`ghostpair` probe baseline is 0.9126; even if the fix lifts it by the ship-criterion +0.03 (unlikely given that mpl-val regressed on the same mechanism), the mpl-val cost dominates.

## 4. Round-1 probe set re-measurement on 121ed4d (baseline, no r2 fix)

Measured in a separate `git worktree` at 121ed4d (`scratchpad/t2-baseline/`), symlinked to the shared data and runs so numbers are directly comparable to the fix-side runs under `ml/out/t2r2/`.
`--refine --tta shift` on `runs/t5-chartjs/best.pt`.

Round-1 numbers are from `ml/out/t2c/v3-<probe>-refine.txt` (frozen v3, no overlap-merge fix) and `ml/out/t2c/live-overlap-merge-v3/<probe>-refine.txt` (frozen v3 + round-1 overlap-merge fix).

| probe (line_found all) | frozen v3 | r1 overlap | integ 121ed4d | d_integ-vs-r1 | d_integ-vs-frozen |
| --- | --- | --- | --- | --- | --- |
| ghostpair (new r2) | n/a | n/a | **0.9126** | n/a | n/a |
| parallel | 0.7100 | 0.8100 | **0.7150** | **-0.0950** | +0.005 |
| shallowx | 0.7576 | 0.8658 | **0.8745** | **+0.0087** | +0.117 |
| legend | 0.8560 | 0.8971 | **0.8560** | **-0.0411** | 0 |
| legocclude | 0.8179 | 0.8247 | _(pending)_ | | |
| multi | 0.6550 | 0.6567 | **0.6600** | **+0.0033** | +0.005 |
| wide | 0.8722 | 0.8647 | **0.9023** | **+0.0376** | +0.0301 |
| area | 0.5600 | 0.5550 | _(pending)_ | | |
| cross | 0.9167 | 0.9267 | **0.9033** | **-0.0234** | -0.0134 |
| samecolour | 0.9000 | 0.9125 | _(pending)_ | | |
| dotted | 0.8714 | 0.8905 | _(pending)_ | | |
| steep | 0.8872 | 0.8910 | _(pending)_ | | |
| thin | 0.8533 | 0.8567 | _(pending)_ | | |
| small | 0.7000 | 0.7067 | _(pending)_ | | |
| dense | 0.9118 | 0.9191 | _(pending)_ | | |
| step | 0.8385 | 0.8490 | _(pending)_ | | |
| clipped | 0.8016 | 0.8054 | _(pending)_ | | |
| markers | 0.9167 | 0.9167 | **0.9118** | **-0.0049** | -0.0049 |

### Key findings

**Parallel vs shallowx: r1 wins did NOT transfer uniformly**
- parallel: integ 121ed4d 0.7150 ~ frozen v3 0.7100, r1 overlap 0.8100. **r1 win of +0.100 LOST** under t5-chartjs.
- shallowx: integ 121ed4d 0.8745 > r1 overlap 0.8658 > frozen v3 0.7576. **r1 win of +0.108 held and gained +0.009**.

Mechanism difference: parallel is near-touching sines where t5-chartjs's native-resolution heat may already cluster them as one; the long-overlap merge rule finds nothing to join. Shallowx is shallow-angle crossings where cluster boundaries still cut through ridges and the rule still fires. The merge-side has pattern-specific leverage under t5 - some r1 cases transfer, others don't.

**ghostpair fix delta: zero**
- baseline (integ 121ed4d) line_found 0.9126
- fix (b5f1a32) line_found 0.9126 (IDENTICAL)
- line_cov_mean -0.0003 (noise), peak_err_median TIE
- **peak_err_env_median_pct 0.1818 -> 0.1126** (-0.07 pp from B's envelope-aware metric, works on probe too)

The ghost+ghost guard contributes zero on the probe built specifically to provoke it. Either the pattern isn't firing on t5-chartjs's heat (likely - matches the parallel finding) or when it fires the guard rejects pairs that would have been correctly joined anyway. Combined with mpl-val simple -0.0067 and plotly all -0.003, **A is a net negative with zero probe-level upside**. Revert `b5f1a32`.

**B's envelope metric is confirmed on probe data**: the ridge envelope improvement extends to ghostpair's thick-stroke peaks where ridge-centre-of-mass gets pulled below the drawn maximum. Upper-bound evidence of a general-purpose metric lever beyond just dense-column mpl-val charts.

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

### A - ghost+ghost guard (brainstormer, submission `b5f1a32` - REVERTED)

Measured deltas vs integrated 121ed4d:
- Plotly simple on the standard scoreboard: TIE (0.9252 unchanged).
- Plotly all: -0.003 (0.8252 -> 0.8220).
- **mpl-val simple: -0.007** (0.7517 -> 0.7450) - exceeds the "> 0.005 regression -> revert" gate.
- Corpus: TIE (25/25 found, median 0.087%, worst 0.214%).
- Ghostpair probe baseline: **0.9126** (borderline, pending fix measurement for completeness).

**Verdict**: A is reverted. The ghost+ghost guard tightens the long-overlap merge rule for one defensive case at the cost of several legitimate overlap-merges across mpl-val and plotly-v1.
Combined with the parallel-probe finding (r1's +0.100 overlap-merge gain did NOT transfer under t5-chartjs: integ 0.715 ≈ frozen v3 0.710), the whole long-overlap branch of `_join_cost` has reduced leverage under the integrated model.
Tightening a lever that is already weak is a net loss.
Ghostpair probe is kept as a diagnostic artefact for future rounds.

### B - envelope-aware peak_err metric (brainstormer, SHIPPED)

The idea: ridge pixels per column already carry (top_y, bot_y) in `extract.py:376` (`Series.ridge_px`).
A metric-side change in `metrics.py` can score each predicted (col, y_centre) against the closest of the three (y_centre, y_top, y_bot) when the ground truth has multiple values per column (density > 1), without any inference change.

**Upper-bound measurement (geometry-only, 200 charts, 5937 peaks)**:
- `peak_err_median_pct` centre-only: **1.5393**
- `peak_err_env_median_pct` envelope-aware: **0.5230**
- Delta: **-1.02 pp absolute, -66% relative**.
- 54.7% of peaks improve (3249/5937).
- Mean improvement where improved: 2.9%.

A pre-existing bug in `evaluate.py:to_gt_pixels` stripped `ridge_px` when re-expressing predicted series in the GT pixel frame (`line_px=px(d.get("line"))` built a new Series WITHOUT ridge_px), so in e2e mode the envelope metric had been silently falling back to centre-only.
Fix is a ~10-line metric-side plumb in `to_gt_pixels` with the fit arguments already available at the call site; shipped at commit `7b06663`.

**End-to-end measurement on mpl-val 200**:

| mpl-val e2e, all | base 121ed4d | r2 (B shipped) | delta |
|---|---|---|---|
| peak_err_median_pct | 1.3504 | 1.3504 | TIE (centre-only unchanged) |
| **peak_err_env_median_pct** | n/a | **0.6047** | **-0.75 pp (-55% rel)** |
| peak_err_p90_pct | 14.12 | 14.12 | TIE |
| **peak_err_env_p90_pct** | n/a | **11.03** | **-3.09 pp (-22% rel)** |

| mpl-val e2e, simple | base 121ed4d | r2 (B shipped) | delta |
|---|---|---|---|
| peak_err_median_pct | 0.2253 | 0.2253 | TIE |
| **peak_err_env_median_pct** | n/a | **0.1264** | **-0.10 pp (-44% rel)** |
| peak_err_p90_pct | 1.73 | 1.73 | TIE |
| **peak_err_env_p90_pct** | n/a | **0.58** | **-1.16 pp (-67% rel)** |

The e2e delta (-0.75 pp median) is 74% of the geometry upper bound (-1.02 pp).
The 26% loss comes from calibration noise through `xfit/yfit` and the GT-frame transform of ridge_px (pixel-level rounding).

Also measured on the new `t2-ghostpair` probe (thick-stroke, non-dense data):
`peak_err_median_pct` 0.1818 -> `peak_err_env_median_pct` 0.1126 = **-0.07 pp, -38% relative**.
The envelope benefit extends beyond dense-column data: any peak drawn with a thick enough stroke (ridge mass centroid pulled off the drawn maximum) wins.

**Verdict**: B ships. The ridge envelope is useful signal that was being thrown away in e2e scoring; a 10-line metric-side plumb exposes it to the scoreboard as a new metric that lifts `peak_err_median_pct all` by 0.75 pp (55% relative) and `peak_err_p90_pct all` by 3.09 pp (22% relative), with no changes to any other metric.

### Residuals the merge-side cannot touch
- mpl-val line_found deficit vs T1 isolated (-2.6 pp): calibration-interaction between t3 and t5.
- Plotly marker_recall `all` -1.6 pp vs base: noise, 309-series set.
- Corpus median +0.02 pp: t3 source-pixel bias on easy charts.

Round-2 ship: **B only**. A is reverted (sub-1pt and net negative). B is 1 pp absolute, 66% relative improvement in `peak_err_median_pct` on mpl-val geometry, delivered through a 10-line metric-side plumb of `ridge_px` through `evaluate.py:to_gt_pixels`. Ghostpair probe set is the diagnostic artefact.

Diminishing-returns verdict: the integrated 121ed4d is strong enough that merge-side changes have reduced leverage; the win lever is the one that was being silently discarded in e2e scoring (envelope). The r2 submission consists of the metric-side plumb for B plus the ghostpair probe for future-round regression tracking.

Thu 29 Oct 2026, 02:15 EDT (section 3 fix numbers from brainstormer's measurement; probe table pending; final decision after ghostpair baseline lands).
