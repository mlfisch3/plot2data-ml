# t2-trace round 2 - curator sections for REPORT_R2.md

Final-form Diagnosis and Probe-set sections. Numbers in italics are placeholders filled once the baseline-batch results land under `scratchpad/t2-baseline/ml/out/t2r2-base/`.

## Diagnosis

Round-1's `_join_cost` rewrite (60 lines) joined chain pieces of one series when a global embedding cluster boundary cut a continuous ridge in half.
It landed in the integrated model (`121ed4d`) with no changes, together with the t5 base's TTA and native-resolution reader, t3's source-pixel column measurement, t4's source-pixel marker re-measurement, and t1's structured axis decode.

**The round-1 ticket for round two was "plotly simple -0.019 end-to-end regression" (ghost+ghost merge in 1-3 series charts).**
That ticket is already closed by the integration.
On `team/t2-trace-r2 @ 121ed4d` the plotly-v1 e2e `line_found simple` is **0.9252**, +0.028 above T5 V2 isolated (0.897) and +15 pp above frozen v3 (0.776).
Reproduced byte-identical with the integration report numbers.

The t5 base's native-resolution reader produces sharper flank ridges than the fit-canvas 768x512 scalers of v3 did, and its TTA shift averages across sub-pixel offsets.
Together these dissolve the weak ghost clusters (q 0.3-0.4) that drove 500106 and 500111 on the frozen tree.
The pattern the round-1 next-step guard was designed to catch simply does not form on the integrated model's heatmap.

With the first-choice ticket off the board, the round-2 angles narrow:

- **A. Defensive ghost+ghost guard** (`min_q` 0.3 -> 0.4 and `nov >= 0.5 * min(A.n, B.n)` in the long-overlap branch of `_join_cost`).
  Applied at `b5f1a32`.
  Measured on plotly-v1 e2e: `line_found simple` TIE (0.9252 vs 0.9252), `line_found all` **-0.003** (0.8252 -> 0.8220).
  Both guards reject some legitimate overlap-merges whose signals t5 now produces cleanly.
  The deciding evidence must come from the new `t2-ghostpair` probe: does the guard improve a reproducible failure case that is not visible in the standard scoreboard?

- **B. Envelope-aware peak_err metric** (brainstormer's prototyping).
  `extract.py` already produces `Series.ridge_px` per column; `metrics.py` scores only the centre.
  A metric-side patch that scores the nearest of {centre, top, bottom} gives the ceiling on what exposing the envelope in the public API would buy in `peak_err_median_pct` on `all` splits where ground truth has multiple y per column.
  Measurement upper-bound first; no inference change.

- **Residuals the merge-side cannot touch**:
  - mpl-val `line_found` 2.6 pp behind T1 isolated (0.6616 vs 0.6876). Calibration-interaction between t3 (source-pixel measurement) and t5 (TTA shift) pushes some borderline-correct lines below the match threshold.
  - plotly `marker_recall all` -1.6 pp vs base (0.418 -> 0.403). Within noise on 309 series.
  - corpus median `+0.02 pp` (0.067% -> 0.087%). t3's source-pixel bias on easy single-solid charts; traded for the 61.222 -> 0.214 worst-case win.

The round-2 principle (diminishing returns) applies: on the integrated base, merge-side gains are hard-capped at a few tenths of a pp of the standard scoreboard.
A ship criterion is a probe-level demonstration (`ghostpair >= +0.03` from fix) if the scoreboard delta is zero or negative, or a metric-side upper-bound of >= 1 pp for the envelope lever.

## Probe set

Round-1 probe set (17 cases) re-measured on `121ed4d` with `runs/t5-chartjs/best.pt --refine --tta shift` from a separate `git worktree` at 121ed4d (`scratchpad/t2-baseline/`), symlinked to the shared data and runs so the comparison is apples-to-apples.
Round-2 new probe: `ghostpair`, case index 17 in `p2d/synth/probe_t2.py`, seeds 12,170,000..12,170,099, built at commit `431843a`.

### line_found all

| probe | n series | frozen v3 | r1 overlap | integ 121ed4d | d_int-vs-r1 | d_int-vs-frozen |
| --- | --- | --- | --- | --- | --- | --- |
| ghostpair (new r2) | 183 | n/a | n/a | **0.9126** | n/a | n/a |
| parallel | 200 | 0.7100 | 0.8100 | **0.7150** | **-0.0950** | +0.0050 |
| shallowx | 230 | 0.7576 | 0.8658 | _(pending)_ | | |
| legend | 213 | 0.8560 | 0.8971 | _(pending)_ | | |
| legocclude | 303 | 0.8179 | 0.8247 | _(pending)_ | | |
| multi | 400 | 0.6550 | 0.6567 | _(pending)_ | | |
| wide | 200 | 0.8722 | 0.8647 | _(pending)_ | | |
| area | 100 | 0.5600 | 0.5550 | _(pending)_ | | |
| cross | 300 | 0.9167 | 0.9267 | _(pending)_ | | |
| samecolour | 240 | 0.9000 | 0.9125 | _(pending)_ | | |
| dotted | 210 | 0.8714 | 0.8905 | _(pending)_ | | |
| steep | 100 | 0.8872 | 0.8910 | _(pending)_ | | |
| thin | 240 | 0.8533 | 0.8567 | _(pending)_ | | |
| small | 210 | 0.7000 | 0.7067 | _(pending)_ | | |
| dense | 220 | 0.9118 | 0.9191 | _(pending)_ | | |
| step | 215 | 0.8385 | 0.8490 | _(pending)_ | | |
| clipped | 258 | 0.8016 | 0.8054 | _(pending)_ | | |
| markers | 240 | 0.9167 | 0.9167 | _(pending)_ | | |

Comparison helper: `teams/t2-trace/tools/compare_r1_r2.py` (prints the table for any metric).
Baseline outputs: `/tmp/claude-1000/.../scratchpad/t2-baseline/ml/out/t2r2-base/int-<probe>-refine.txt`.

### `ghostpair`: provoke the r1 plotly-simple regression

Case design (committed in `p2d/synth/probe_t2.py` at `431843a`):

- 1-3 series per chart (narrow set, matches 500106 / 500111).
- Thick strokes `lw` 3-5 pt at `dpi` 100-120 -> 4-8 canvas-pixel stroke.
- Wide figures: `wpx` 900-1400, aspect 0.4-0.6 (presentation shape).
- Smooth shapes (sines, trend_noise, poly, logistic, walk).
- Mix of solid / dashed / dashdot.
- Plotly-presentation palette included; same-family colours (blue vs cyan, orange vs red) occur so a ghost of series A can land near the real of series B.
- `ylim` padded 30% so ghost flanks fit inside the plot area.

Mechanism being provoked: thick anti-aliased strokes produce weak "flank" clusters (q 0.3-0.5) parallel to the real ridge.
Round-1's overlap-aware `merge_fragments` sees `|median| < 6`, `MAD < 1.2`, `drift < 2.5` across the overlap of two flank clusters and joins them into one longer ghost that passes `drop_duplicates`.
Round-2's guard raises `min_q` to 0.4 and requires `nov >= 0.5 * min(A.n, B.n)`, rejecting weak and short-overlap ghost pairs.

Sample mosaic in `ml/out/t2r2/ghostpair-samples.png`.

### Decision gates on `ghostpair`

- **Baseline ghostpair `line_found` >= 0.95**: the pattern does not reproduce on the integrated model (t5-chartjs's cleaner ridge dissolves the flanks even at 4-8 px stroke). Defer A entirely, revert `b5f1a32`.
- **Baseline in 0.70-0.90, fix line_found >= +0.03**: well-defined behavioural improvement. Ship A as defensive guard, cite ghostpair in the submission.
- **Baseline < 0.70 OR fix no better than baseline**: either the probe over-provokes (needs tamer stroke widths) or the fix undershoots. Defer A regardless.

### What the probe does NOT cover (round-1 cases that still bleed on `multi` and `wide`)

The ghostpair probe isolates ONE failure (ghost+ghost merge). It does not provoke:

- C2 (hopping at a crossing) - needs `cross` or `shallowx`.
- C3 (steep interruption) - needs `steep`.
- C4 (dense/steep one-value-per-column) - needs `dense` or `multi`; this is the territory for target B.
- Wide-figure p90 blow-outs - needs `wide`.
- Area-top ridges - needs `area`.

The round-1 probe set re-measurement (section above) is the picture of how those still look.

### Expected pattern on the integrated model (verified when batch lands)

Round-1 wins came through the embedding of v3-trained PlotNet; t5-chartjs is a different checkpoint but shares the extraction pipeline.
Expected: the big three (parallel +0.100, shallowx +0.108, legend +0.041) hold at the same magnitude or better because they are purely extractor-side changes.
The small r1 regressions (area -0.005, wide -0.008) MAY be eliminated or AMPLIFIED by t5-chartjs's cleaner ridge, depending on how it re-balances flank clusters at wide/filled shapes.

Thu 29 Oct 2026, 02:15 EDT (table pending the baseline batch under GPU lock contention; estimated 1-2 hours).
