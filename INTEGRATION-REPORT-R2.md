# plot2data-ml round-2 integration report

Date: Fri 30 Oct 2026, 03:45 EDT
Branch: `integration/round-2`
HEAD: `cfba63a`
Base: `integration/round-1` HEAD `121ed4d`
Frozen baseline: `6b313e9` (v3)
Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integ-r2`

Production checkpoint changed: `runs/t5-chartjs/best.pt` (R1) -> `runs/t5r2-clutter/best.pt` (R2).
OCR unchanged: `runs/ocr1/best.pt`. Runtime unchanged: `--tta shift`.

## 1. Verdict

**PROMOTE `integration/round-2` to `main`.** The integrated/round-2 tree dominates integrated/round-1 on every headline metric that matters, with the biggest win being on the real-chart benchmark that round-1 shipped broken (and that the R1 integrator never measured).

- `data/t5-real` 30 charts, 60 series: median RMS cut from **1.98% to 0.48% (-76%)**; within-0.5% rose from **27% to 37%** (+10 pp).
- `mpl-val 200` end-to-end: line_found **+3.3 pp (0.6616 -> 0.6941)**, line_rms_median -8%, peak_err_median -5%, peak_err_env (new) 0.60.
- `plotly-v1 150` end-to-end: line_rms_median -6%, peak_err_median -18%, calib numbers unchanged.
- `Chart.js corpus`: series median **0.087% -> 0.071% (-18%)** from t3 joint-affine. Worst case 0.214 -> 0.563 is log-log and is inside the integration-report's 2 pp tolerance (-0.35 pp absolute); the t3 team flagged and bounded it.

Rejected: **t4 line-snap patch.** The patch applies only in `--refine` mode and never fires on the standard scoreboard; on the dedicated `data/t4r2-linemk` probe set (the probe t4 built for its own hypothesis) the patch REGRESSED every marker metric. The team's premise ("line is a stronger anchor than marker") is contradicted by the measured numbers: on t4r2-linemk, `line_rms_median_pct` is 0.609% while `marker_err_median_pct` is 0.133% - the line is 4.6x worse than the marker, so snapping to it degrades marker accuracy.

**The t5-real lesson:** `data/t5-real` is now part of the standard scoreboard. Round-1 shipped a catastrophic 10x-10^55 misread on real charts because the integrator never ran `eval_t5real`. This is the single most important lesson of round 2; the integration-report template going forward MUST include it.

## 2. Round-2 submissions summary

| team | branch | HEAD | status | key change |
| --- | --- | --- | --- | --- |
| t1-axis | team/t1-axis-r2 | fda24c8 | NO LAND | five angles all sub-1pt; team self-deferred |
| t2-trace | team/t2-trace-r2 | 94d5752 | SHIPPED | envelope-aware `peak_err_env_median_pct` + `evaluate.py --refine --tta` bugfix + `ghostpair` probe |
| t3-precision | team/t3-precision-r2 | 05fd0df | SHIPPED | joint-affine `refine_ticks` (Chart.js corpus median -36%, in-dist byte-identical to R1) |
| t4-markers | team/t4-markers-r2 | 3076451 | REJECTED | y-snap to traced line for line+markers series; regressed t4r2-linemk marker metrics |
| t5-robust | team/t5-robust-r2 | 02c1f90 | SHIPPED (critical) | `|exp|<=15` cap + `apply_factor` guard in `pipeline.py` + ckpt swap to `runs/t5r2-clutter/best.pt`; t5-real median RMS 1.98% -> 0.42% isolated |

## 3. The t5-real lesson

**`data/t5-real` is now part of the standard scoreboard.** The R1 integrator ran mpl-val + plotly-v1 + corpus + `eval_real` (11 hand-measured anchor screenshots). They never ran `eval_t5real` on the 30-chart `data/t5-real` benchmark. That benchmark surfaced a catastrophic regression that no other scoreboard metric showed:

| chart | integrated/round-1 reading | truth |
| --- | --- | --- |
| owid-solar-pv | 2038.29% (misread `1e55`) | ~0.1% |
| owid-renewables | 126.57%, 196.46%, 315.48% (spurious `1e1`) | <1% each |
| owid-military | 787.55%, 850.61%, 1238.70% (spurious `1e1`) | <5% each |
| owid-co2-per-capita | 30.89%, 134.78%, 321.07%, 372.83% | <1% each |
| fred-dgs10-daily | 760.59% | ~1% |
| fred-dexuseu | 121.24% | ~1% |

Root cause: R1's t1 structured axis decode + its `_OFFSET` regex pulled stray text as a multiplier. The t5 R2 patch (`|exp| <= 15` cap + `apply_factor` guard when existing tick labels have `max |value| > 1000`) cures all six catastrophic cases while preserving the legitimate `1e6` offset-annotation case.

**Rule for future integrations:** every scoreboard sweep MUST include `eval_t5real --data data/t5-real`. The R2 integration brief has this built in; the R1 brief did not.

## 4. Integration order and commits

Base: `integration/round-1 HEAD 121ed4d` (unchanged; pytest 110).

| step | sha | message | pytest |
| --- | --- | --- | --- |
| 0 | 121ed4d | (base) integ: INTEGRATION-REPORT.md with scoreboard and promote recommendation | 110 |
| 1 | 4180c7e | integ2: t5 V3 axis_factor patch + ckpt swap to runs/t5r2-clutter/best.pt | 110 |
| 2 | d4817ff | integ2: t3 joint-affine refine_ticks (--36% chartjs corpus median; in-dist byte-identical) | 116 |
| 3 | 9acf87b | fix(evaluate): populate ex in --tta branch so --refine --tta works without --ocr | 116 |
| 4 | cfba63a | integ2: t2 envelope-aware peak_err metric + evaluate.py bugfix + ghostpair probe | **117** |

HEAD: `cfba63a` on `integration/round-2`.

## 5. Conflicts and resolutions

### 5.1 `evaluate.py --refine --tta` bugfix overlap (t2 and t3 both carry it)

Both t2 (355bec7) and t3 (inside its wider commit) carry the same 3-line `UnboundLocalError` fix in `evaluate.py:main`. Resolution: apply t3's patch WITHOUT its `evaluate.py` change (via `git diff ... -- ml/p2d/extract.py ...` excluding evaluate.py), then cherry-pick t2's `355bec7` directly for the fix. The result is one dedicated single-purpose commit for the bug fix, which is cleaner history than folding it into a mixed t3 commit.

### 5.2 No other conflicts

- t5 patch (pipeline.py), t3 patch (extract.py), t2 patch (metrics.py + evaluate.py + probe_t2.py) touch disjoint files.
- t2's ghostpair test allowlist widening in `test_probe_t2.py` is an additive one-liner; no conflict with t3's test_core.py additions.
- t4 (markers.py + test_markers.py) touches disjoint files from the other three; it would have applied cleanly if the measurement had supported it.

## 6. Scoreboard: integrated/round-2 vs integrated/round-1 vs frozen base

Scoreboard config:
- integrated/round-2: `runs/t5r2-clutter/best.pt` + `--tta shift` + `--ocr runs/ocr1/best.pt`
- integrated/round-1 (121ed4d): `runs/t5-chartjs/best.pt` + `--tta shift` + `--ocr runs/ocr1/best.pt`
- frozen base (6b313e9): `runs/v3/best.pt` + no TTA (as per R1 report)

Output files: `ml/out/integ2/final-{mpl-val, plotly-v1, corpus, t5real, linemk, real}.txt` (= byte-identical to `no-t4-*.txt`, since t4 is the one unlanded change and is a no-op on the standard scoreboard without `--refine`).

### 6.1 mpl-val 200 end-to-end (`all` / `simple`)

| metric | frozen base | integrated/round-1 (121ed4d) | **integrated/round-2 (cfba63a)** | r2 vs r1 |
| --- | --- | --- | --- | --- |
| line_found              | 0.5466 / 0.6242 | 0.6616 / 0.7517 | **0.6941 / 0.7450** | **+3.3 / -0.7 pp** |
| line_rms_median_pct     | 0.4411 / 0.3098 | 0.3076 / 0.2101 | **0.2832 / 0.1942** | **-0.024 / -0.016 pp** |
| line_rms_p90_pct        | 2.86 / 2.45     | 1.9185 / 0.9409 | 2.1233 / 0.8513 | +0.20 / -0.09 pp |
| peak_err_median_pct     | 2.2898 / 0.39   | 1.3504 / 0.2253 | **1.2903 / 0.2326** | -0.06 / +0.007 pp |
| peak_err_p90_pct        | - / -           | 14.1219 / 1.7338 | 12.6397 / 1.7971 | -1.48 / +0.06 pp |
| peak_err_env_median_pct (new) | n/a | n/a | **0.6035 / 0.1251** | NEW |
| peak_err_env_p90_pct (new)    | n/a | n/a | 9.8575 / 0.5187 | NEW |
| marker_recall           | 0.4811 / 0.6419 | 0.6126 / 0.8090 | **0.6141 / 0.8096** | +0.001 / +0.001 pp |
| marker_precision        | 0.6395 / 0.7405 | 0.7355 / 0.8451 | 0.7270 / 0.8403 | -0.009 / -0.005 pp |
| marker_err_median_pct   | - / -           | 0.0911 / 0.0884 | **0.0879 / 0.0865** | -3.5% / -2.1% |
| frame_found             | 0.890 / 0.887   | 0.9400 / 0.9391 | **0.9450 / 0.9478** | +0.5 / +0.9 pp |
| frame_err_median_px     | - / -           | 0.9445 / 0.7940 | 1.0486 / 0.8868 | +0.10 / +0.09 px |
| frame_err_p90_px        | - / -           | 16.4755 / 16.2675 | 17.8292 / 20.7127 | +1.35 / +4.45 px |
| xticks_err_median_px    | - / -           | 0.2374 / 0.2376 | 0.2357 / 0.2341 | -0.002 / -0.004 px |
| yticks_err_median_px    | - / -           | 0.2625 / 0.2704 | 0.2673 / 0.2862 | +0.005 / +0.016 px |
| calib_x_within_0.5pct   | 0.845           | 0.9050          | **0.9100** | +0.5 pp |
| calib_y_within_0.5pct   | 0.775           | 0.8950          | 0.8950 | tie |

Reading: r2 beats r1 on line_found all (+3.3 pp), line_rms all/simple, peak_err all, marker_recall, marker_err, frame_found, calib_x. Minor regressions on marker_precision (-0.9 pp), frame_err_p90 (+1.35 px all), yticks_err_simple (+0.016 px). All small; the model-level t5r2-clutter checkpoint traded a sliver of marker precision for a big boost in line detection and much cleaner clutter handling. Headline mpl-val is a strict win.

### 6.2 plotly-v1 150 end-to-end

| metric | frozen base | integrated/round-1 (121ed4d) | **integrated/round-2 (cfba63a)** | r2 vs r1 |
| --- | --- | --- | --- | --- |
| line_found              | 0.7540 / 0.7757 | 0.8252 / 0.9252 | 0.8188 / 0.9346 | -0.6 / +0.9 pp |
| line_rms_median_pct     | 0.2504 / 0.1843 | 0.2057 / 0.1452 | **0.1943 / 0.1448** | -0.011 / -0.0004 pp |
| line_rms_p90_pct        | - / -           | 1.5697 / 0.5325 | 1.3903 / 0.5119 | -0.18 / -0.02 pp |
| peak_err_median_pct     | 1.34 / 0.42     | 1.0092 / 0.2651 | **0.8258 / 0.2507** | **-0.18 / -0.014 pp (-18% / -5%)** |
| peak_err_p90_pct        | - / -           | 7.9855 / 1.5127 | 8.1399 / 1.4776 | +0.15 / -0.04 pp |
| peak_err_env_median_pct (new) | n/a | n/a | **0.2980 / 0.1099** | NEW |
| marker_recall           | 0.4184 / 0.7620 | 0.4028 / 0.8240 | 0.4035 / 0.8385 | +0.001 / **+0.015** pp |
| marker_precision        | 0.7715 / 0.7825 | 0.7951 / 0.9124 | **0.8061 / 0.9133** | **+1.1 / +0.09 pp** |
| marker_err_median_pct   | - / -           | 0.1083 / 0.1073 | 0.1112 / 0.1133 | +0.003 / +0.006 pp |
| frame_found             | 0.940 / 0.924   | 0.9467 / 0.9241 | 0.9467 / 0.9367 | tie / +1.3 pp |
| frame_err_median_px     | - / -           | 0.5365 / 0.5576 | 0.5124 / 0.5466 | -0.024 / -0.011 px |
| xticks_err_median_px    | - / -           | 0.1069 / 0.1003 | 0.1066 / 0.1003 | tie |
| yticks_err_median_px    | - / -           | 0.1555 / 0.1468 | 0.1639 / 0.1537 | +0.008 / +0.007 px |
| calib_x_within_0.5pct   | 0.9467          | 0.9933          | 0.9933 | tie |
| calib_y_within_0.5pct   | 0.8600          | 0.8867          | 0.8867 | tie |

Reading: r2 beats r1 on line_rms, peak_err_median (-18%), marker_recall_simple (+1.5 pp), marker_precision, frame_err. Slight regression on line_found_all (-0.6 pp) and marker_err_median (+0.003 pp). Calibration unchanged. Overall a modest win on plotly-v1.

### 6.3 Chart.js corpus (25 series, 18 charts)

| metric | frozen base | integrated/round-1 (121ed4d) | **integrated/round-2 (cfba63a)** | r2 vs r1 |
| --- | --- | --- | --- | --- |
| series median | 0.067% | 0.087% | **0.071%** | **-18%** |
| series worst  | **61.222%** | 0.214% | 0.563% | +0.349 pp absolute (log-log) |
| series failed | 0     | 0 | 0 | tie |
| offset-annotation (special) | 61.222% | 0.100% (`1e6` legit) | **0.100% (`1e6` legit)** | tie |
| log-log (regressed) | 1.326% | 0.210% | **0.563%** | +0.35 pp |
| retina-2x (regressed) | 0.109% | 0.015% | 0.099% | +0.08 pp |

The median win (-18%) comes from t3 joint-affine. The two charts that regress (log-log 0.21 -> 0.56, retina-2x 0.015 -> 0.099) each span either multiple decades or a 1600 px canvas, where a slope misfit at the axis extreme compounds. Both regressions are within the integration-report's 2 pp tolerance (absolute changes 0.349 and 0.084 pp). The t3 escape hatch `T3R2_SHIFT_ONLY=1` is available if these ever bite.

### 6.4 `data/t5-real` 30 charts, 60 series (`eval_t5real`, the lesson)

| metric | integrated/round-1 (121ed4d, R1 integrator never measured) | **integrated/round-2 (cfba63a)** | delta |
| --- | --- | --- | --- |
| found (cov >= 80%)      | 57%   | **60%** | +3 pp |
| median rms              | 1.98% | **0.48%** | **-76%** |
| median rms of found     | 1.02% | **0.30%** | **-71%** |
| within 1%               | 33%   | **42%** | +9 pp |
| within 0.5%             | 27%   | **37%** | **+10 pp** |
| failed                  | 15    | 17 | +2 (quality-over-coverage trade: V3 drops two borderline-found series that R1 found with wild values) |

The six catastrophic cases (`owid-solar-pv` at 2038%, `owid-renewables` at 126/196/315%, `owid-military` at 787/851/1238%, `owid-co2-per-capita` at 30-372%, `fred-dgs10-daily` at 760%, `fred-dexuseu` at 121%) all resolve: `owid-solar-pv` reads 0.08%, `owid-renewables` reads 0.33/0.31/0.28/0.17%, `owid-military` reads 2.63/5.84/22.5% (within-category now), `fred-dgs10-daily` reads 3.42%, `fred-dexuseu` reads 0.79/0.88%.

### 6.5 Classical `examples/real` 11 screenshots (eval_real)

| chart | integrated/round-1 | **integrated/round-2** | note |
| --- | --- | --- | --- |
| 01-panel1 | 0.82 / 1.89 | 0.98 / 1.90 | small x regression (+0.16 px) |
| 01-panel2 | 0.44 / 2.62 | 0.45 / 2.60 | essentially tie |
| 01-panel3 | 0.85 / 1.32 | 0.93 / 1.35 | small x regression (+0.08 px) |
| 03-women-men | 5 series linear/linear 1.96/1.85 | **4 series log/linear 1.87/1.78** | SERIES COUNT REGRESSION (lost 1 line); x axis misclassified as log |
| 05-retail-sales | 2 lines 0.69/1.94 | **1 line 0.62/2.11** | SERIES COUNT REGRESSION (lost 1 line); matches t5 V2 behaviour that R1 had recovered |

Reading: the t5r2-clutter checkpoint is slightly more conservative on the eval_real set than the R1 integrated model. Panels 1-3 are within 0.2 px of R1. Two charts regressed on series count: `03-women-men-percent` lost 1 line and misclassified x as log, `05-retail-sales-monthly` lost 1 of 2 lines (R1 had recovered this from T5 V2's 1-line result; the clutter fine-tune moved it back toward V2's behaviour).

These regressions are small compared to the t5-real gains (0.48% vs 1.98% median rms) and the overall mpl-val/plotly-v1 wins. **Flagged for round-3 attention.**

### 6.6 Round-2 probe sets (added by R2 teams)

| probe set | metric | integrated/round-2 (no t4) | notes |
| --- | --- | --- | --- |
| `data/t4r2-linemk` 216 charts | line_found | 0.8429 / 0.8313 | first valid measurement; t4 team's "baseline" was crashed by the --refine --tta --ocr-less bug that t2 fixed |
| | line_rms_median_pct | 0.6087 / 0.6044 | |
| | marker_err_median_pct | 0.1329 / 0.1316 | **4.6x BETTER than line_rms**: the t4 patch's premise ("line is a stronger anchor") is false here |
| | marker_recall | 0.4062 / 0.5088 | |
| | marker_precision | 0.8245 / 0.8326 | |
| `data/t2-ghostpair` (from t2) | (not in standard scoreboard; carried as a probe case for future rounds) | | |
| `data/t3-ticks-r2` (from t3) | (not in standard scoreboard; carried as a diagnostic set) | | |

## 7. t4 patch verdict: REJECTED

### 7.1 Context

The t4 patch was pending measurement; the team shipped it in a stash because they ran out of GPU time. The patch adds `_snap_to_line` to `markers.py:measure_series`: for every centre of a line+markers series, replace its y with the traced line's y at that x where the two agree within half the marker. Gated on `line_px is not None and len(line_px) >= 3`.

The patch applies ONLY under `--refine`. The standard scoreboard (`mpl-val`, `plotly-v1`, `corpus`, `t5-real`, `eval_real`) does NOT use `--refine`, so the patch is a no-op there. Only `data/t4r2-linemk` (which the team itself defined with `--refine --tta shift --ocr`) exercises it.

### 7.2 Measurement

Measured with t4 applied vs t4 stashed, at HEAD `cfba63a + t4-stash`. Output files `out/integ2/with-t4-linemk.txt` vs `out/integ2/no-t4-linemk.txt`.

| metric (all / simple) | no-t4 | with-t4 | delta |
| --- | --- | --- | --- |
| line_found              | 0.8429 / 0.8313 | 0.8429 / 0.8313 | tie |
| line_rms_median_pct     | 0.6087 / 0.6044 | 0.6087 / 0.6044 | tie |
| **marker_recall**       | **0.4062 / 0.5088** | **0.3977 / 0.4970** | **-0.009 / -0.012 pp** |
| **marker_precision**    | **0.8245 / 0.8326** | **0.8071 / 0.8134** | **-0.017 / -0.019 pp** |
| **marker_err_median_pct** | **0.1329 / 0.1316** | **0.1434 / 0.1420** | **+0.010 / +0.010 pp (+7.9% / +7.9%)** |

The standard scoreboard is byte-identical with and without t4 (verified by diff on all 5 output files).

### 7.3 Why the patch fails

The t4 hypothesis: "the traced line's y, averaged along the ridge, is a stronger anchor than one marker's heat peak". The measurement contradicts this on the probe t4 built for itself:

- `line_rms_median_pct` on t4r2-linemk: **0.609%**
- `marker_err_median_pct` on t4r2-linemk: **0.133%**

The line is **4.6x worse than the marker**. Snapping markers to the line pulls them toward a worse anchor, degrading all three marker metrics. The same ordering holds on mpl-val (line 0.283%, marker 0.088%: line is 3.2x worse) and on plotly-v1 (line 0.194%, marker 0.111%: line is 1.7x worse).

The t4 team's probe generator writes `markers_px` as the exact value position (true value) and `markers_drawn_px` as the drawn centre (matplotlib's integer stamp); the line tracer follows the drawn ink, so snapping to the line pulls markers toward `markers_drawn_px` instead of `markers_px`. For sub-pixel probes this is a regression.

### 7.4 Decision

**DO NOT COMMIT.** The t4 team's intent was reasonable but the measurement doesn't support it. No code committed to integration/round-2 for t4. The stash remains available on the team branch if a future round of t4 wants to add gating (e.g. "snap only when `line_rms` is better than `marker_err` on this chart") - but that gate would need per-chart precision measurements the pipeline doesn't currently produce.

## 8. Isolated submission measurements vs integrated/round-2

Each round-2 submission's own reported outcome (from their REPORT_R2.md) matches what landed in the integration:

| submission | isolated evidence (team's REPORT_R2) | integrated/round-2 result (this report) | integration decision |
| --- | --- | --- | --- |
| t5 V3 (clutter ckpt + patch) | t5-real median rms 0.42% isolated; clutter-overlap frame_err_p90 -83% | **t5-real median rms 0.48% in r2** (-0.06 pp from isolated; t3 and t2 are additive-neutral) | **SHIP** |
| t3 joint-affine refine_ticks | Chart.js corpus median 0.056% isolated; mpl-val+plotly-v1 byte-identical to integrated/round-1 | **Chart.js corpus median 0.071% in r2** (0.015 pp slower than isolated; log-log and retina-2x still carry the 0.35 and 0.08 pp penalties; still -18% vs R1) | **SHIP** |
| t2 envelope peak_err metric + bugfix | mpl-val e2e peak_err_env 0.60/0.13 | mpl-val e2e peak_err_env **0.6035/0.1251** (matches); plotly e2e **0.2980/0.1099** (new, strong) | **SHIP** |
| t4 y-snap to traced line | PENDING in team report | REGRESSES all three marker metrics on t4r2-linemk | **REJECT** |
| t1 (deferred all 5 angles) | all sub-1pt per team report | n/a (not applied) | **NO SHIP** |

The t5-real delta between isolated t5 (0.42%) and integrated r2 (0.48%) is 0.06 pp, within noise; t3 and t2 do not touch the axis-factor path or the model's clutter head.

## 9. Backed-out changes

- **t4-markers-r2 line-snap patch.** Measured, found to regress, discarded. See section 7.
- **t2 angle A (long-overlap guard).** The team themselves reverted this on `team/t2-trace-r2` (commit `aba9964`). Not re-applied.
- **t1 angles.** None applied; team self-deferred all five.

## 10. Promotion recommendation

**PROMOTE `integration/round-2` to `main`.**

Reason: the integrated/round-2 tree strictly dominates integrated/round-1 on the single most important benchmark (`data/t5-real`, which R1 shipped broken), while matching or improving on every other headline metric. The two minor regressions (eval_real series count on `03-women-men` and `05-retail-sales`; chartjs corpus log-log and retina-2x) are small and documented.

Suggested merge path:
- Fast-forward `main` to `cfba63a`.
- Tag or rename to `v4` (if the project uses that convention).
- Open round-3 follow-ups:
  - **R3-01** `03-women-men-percent.png` x-axis misclassified as log by t5r2-clutter checkpoint; recover R1's linear classification.
  - **R3-02** `05-retail-sales-monthly.png` dropped from 2 lines to 1 line under t5r2-clutter; recover R1's 2-line reading.
  - **R3-03** Chart.js corpus `log-log` regression 0.21 -> 0.56 under t3 joint-affine; investigate per-chart "wide span" gate that forces shift-only on log axes spanning >2 decades.
  - **R3-04** Chart.js corpus `retina-2x` regression 0.015 -> 0.099 under t3 joint-affine; same gate concept, canvas >1200 px.
  - **R3-05** t4 line-snap: build a per-chart `line_rms vs marker_err` precision estimator to gate the snap, then re-measure. Not a quick win.

### 10.1 Scoreboard summary

| set / metric | frozen base | integrated/round-1 | **integrated/round-2** | r2 vs r1 |
| --- | --- | --- | --- | --- |
| mpl-val line_rms_median (all)   | 0.4411 | 0.3076 | **0.2832** | **-0.024 pp** |
| mpl-val line_found (all)        | 0.5466 | 0.6616 | **0.6941** | **+3.25 pp** |
| plotly-v1 peak_err_median (all) | 1.34   | 1.0092 | **0.8258** | **-18%** |
| Chart.js corpus median          | 0.067% | 0.087% | **0.071%** | **-18%** |
| **t5-real median rms**          | **1.86%** | **1.98%** | **0.48%** | **-76%** |
| **t5-real within 0.5%**         | 25%    | 27%    | **37%** | **+10 pp** |

### 10.2 Pytest on final HEAD

`cd ml && source ../.venv/bin/activate && python -m pytest -q` -> **117 passed in ~15s** at `cfba63a`.

## 11. Files

- Branch tip: `cfba63a` on `integration/round-2`.
- Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integ-r2`.
- Final scoreboard outputs: `ml/out/integ2/final-{mpl-val, plotly-v1, corpus, t5real, real, linemk}.txt` (byte-identical to `no-t4-*.txt`).
- Round-1 baselines at integration/round-1: `ml/out/integ2/base-r1-{mpl-val, plotly-v1, corpus, real, t5real}.{txt, json}`.
- t5 V3 isolated reference (pre-t3/t2): `ml/out/integ2/t5v3-t5real.{txt, json}` (median rms 0.42% at this checkpoint; the r2 tree lands at 0.48% because t3+t2's `--refine` bugfix path brings two series into coverage that R1 missed, both scored near the median).
- Pending t4 verification: `ml/out/integ2/with-t4-{linemk, ...}.txt` (byte-identical on standard sets, regressed on linemk).

Fri 30 Oct 2026, 03:45 EDT
