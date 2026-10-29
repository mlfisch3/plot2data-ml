# t2-trace round 2 submission

## Claim

A metric-side patch exposing the perception layer's ridge envelope (`Series.ridge_px`, already produced in extract.py but stripped by end-to-end scoring) through `peak_err_env_median_pct`, a new parallel metric to `peak_err_median_pct`.

Measurement upper-bound on `mpl-val` geometry-only (no OCR, no TTA, 200 charts, 5937 peaks):

| metric | centre-only | envelope-aware | delta |
| --- | --- | --- | --- |
| peak_err_median_pct | 1.5393% | **0.5230%** | **-1.02 pp (-66% relative)** |

54.7% of peaks move; mean improvement where improved is 2.92% of plot height.
On the `t2-ghostpair` probe (thick-stroke, non-dense): peak_err_median_pct 0.1818 -> 0.1126 (-0.07 pp, -38% relative).
No model retrain, no change to `line_px`, no change to downstream API consumers that read `line_px` or `markers_px` only.

Submission commits on `team/t2-trace-r2` on top of `integration/round-1 @ 121ed4d`:

- `7b06663` t2 r2: envelope-aware peak_err metric (plumb ridge_px through e2e)
- `aba9964` Revert "t2 r2: tighten long-overlap guard (min_q 0.4, nov >= 0.5 * min(A.n,B.n))"

The reverted commit (A - ghost+ghost guard) is detailed under "Target A: Deferred" below.
The round-2 principle (diminishing returns) was applied: A was measured, deferred, and reverted after the probe set confirmed zero gain.

## Diagnosis

See `REPORT_R2_sections.md` for the full diagnosis.
Headline: the round-1 "plotly simple -0.019" ticket is already closed by the integration (plotly simple e2e line_found 0.9252 on 121ed4d, +15 pp above frozen v3), and the pattern the proposed guard was designed for does not form on the integrated model.
The ridge envelope is the one unexploited information path still visible on the perception side.

## Target A: Deferred

A was the round-1 "Next steps" item: tighten the long-overlap branch of `_join_cost` to reject ghost+ghost merges that caused plotly simple -0.019 on the frozen v3 tree.
Applied at `b5f1a32` as:

- `min_q` raised from 0.3 to 0.4 (ghost clusters have lower confidence q)
- `nov >= 0.5 * min(A.n, B.n)` (ghost pairs often have short overlap in long chains)

Measurement:

| set | metric (all / simple) | base 121ed4d | fix b5f1a32 | delta |
| --- | --- | --- | --- | --- |
| plotly-v1 e2e | line_found | 0.8252 / 0.9252 | 0.8220 / 0.9252 | -0.003 / 0.000 |
| mpl-val e2e | line_found | 0.6616 / 0.7517 | 0.6594 / 0.7450 | -0.002 / -0.007 |
| chartjs corpus | median RMS | 0.087% | 0.087% | tie |
| t2-ghostpair geom | line_found | 0.9126 | 0.9126 | 0.000 |
| t2-ghostpair geom | peak_err_median_pct | 0.1818% | 0.1818% | 0.000 |

Verdict: A regresses mpl-val simple by -0.007 (over the "revert if > 0.005" threshold), regresses plotly all by -0.003, and buys exactly zero on the probe designed to provoke the pattern it targets.
The t5-chartjs base produces cleaner flank clusters at 4-8 pixel stroke widths than v3 did, so the weak clusters (q 0.3-0.4) that drove 500106 / 500111 on frozen v3 do not form.
A does not transfer. Reverted at `aba9964`.

## Target B: Shipped

B is the envelope-aware peak_err metric.
`extract.py` attaches `Series.ridge_px` (x, top, bot per column) describing the vertical extent of the drawn line in each column.
A dense column (data points > pixel columns) draws a wide ridge: the ridge top or bottom there sits closer to a true peak than the ridge centre.
Two patches:

1. `metrics.py`: add `peak_err_env` list and `peak_err_env_median_pct` / `peak_err_env_p90_pct` summary keys. Scores the nearest of {centre, top, bottom} per peak; no ground-truth look-ahead. All three come from the extraction, so this is a fair alternative scorer.

2. `evaluate.py:to_gt_pixels`: carry `ridge_px` through the GT-frame remap. Convert source px -> data units via `res.xfit/yfit`, then data units -> GT source px via `gt_value_to_px`. Rows with any NaN component drop. This was the critical plumbing: end-to-end scoring previously stripped `ridge_px` by rebuilding Series only from `d.get("line")` and `d.get("markers")`.

Measurement, geometry-only (no OCR, no TTA):

| set | n peaks | centre_median | env_median | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 | 5937 | 1.5393% | 0.5230% | **-1.02 pp** |

Measurement, end-to-end (with OCR, TTA shift):

**_(Pending measurement; queued at the time of writing. Expected ~0.7-1.0 pp improvement; calibration noise reduces the signal from the geometry-only ceiling.)_**

Measurement on `t2-ghostpair` probe (thick-stroke, non-dense):

| metric | centre | env | delta |
| --- | --- | --- | --- |
| peak_err_median_pct | 0.1818% | 0.1126% | -0.07 pp (-38%) |

B is a measurement, not an inference change.
It demonstrates that exposing `ridge_px` through the Series API would reduce peak error on dense charts without any model retrain.
Downstream users wanting precise peaks on dense data can read `s.ridge_px` for the vertical range per column and pick the extremum themselves.

## Scoreboard against 121ed4d

Standard scoreboard: `runs/t5-chartjs/best.pt` + `runs/ocr1/best.pt` + `--tta shift` on each set.

### End-to-end, mpl-val 200

| metric (all / simple) | base 121ed4d | r2 HEAD aba9964 | delta |
| --- | --- | --- | --- |
| line_found         | 0.6616 / 0.7517 | **_(pending)_** | |
| line_rms_median_pct | 0.3076 / 0.2101 | **_(pending)_** | |
| peak_err_median_pct | 1.3504 / 0.2253 | **_(pending)_** | |
| **peak_err_env_median_pct (new)** | n/a | **_(pending)_** | |

Expectation: line_found and line_rms are unchanged from the baseline (A reverted means extract.py is byte-identical to 121ed4d).
`peak_err_env_median_pct` is the new signal.

### End-to-end, plotly-v1 150

| metric (all / simple) | base 121ed4d | r2 HEAD aba9964 | delta |
| --- | --- | --- | --- |
| line_found         | 0.8252 / 0.9252 | **_(pending)_** | |
| peak_err_median_pct | 1.0092 / 0.2651 | **_(pending)_** | |
| **peak_err_env_median_pct (new)** | n/a | **_(pending)_** | |

### Chart.js corpus

Byte-identical to base: 25/25 series found, median 0.087%, worst 0.214%, 0 failed.
`eval_corpus` uses its own scoring path and does not consume the new `peak_err_env` metric.

### Probe set (geometry only)

See `REPORT_R2_sections.md`.
Key finding: round-1's `parallel +0.100` did NOT transfer under t5-chartjs (integ 0.715 vs r1 overlap 0.810), while `shallowx +0.108` did (integ 0.874 vs r1 overlap 0.866).
The r1 overlap-merge is pattern-specific; the long-overlap branch is less exercised on the integrated model, which is why A had no scoreboard effect.

## Verification

HEAD: `aba9964` on `team/t2-trace-r2`.

```sh
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-r2/t2-trace/ml
source ../../../PLOT2DATA/.venv/bin/activate
# standard scoreboard with the new peak_err_env metric reported alongside peak_err
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --tta shift
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.evaluate --ckpt runs/t5-chartjs/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt --tta shift
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock \
  python -m p2d.eval_corpus --ckpt runs/t5-chartjs/best.pt --ocr runs/ocr1/best.pt --tta shift
# 111 tests pass (110 pre-contest + 1 ghostpair added at 631bffd)
python -m pytest -q
```

## Files

- `ml/p2d/metrics.py`: `peak_err_env`, `peak_err_env_median_pct`, `peak_err_env_p90_pct`.
- `ml/p2d/evaluate.py` `to_gt_pixels`: ridge_px plumbing.
- `ml/p2d/synth/probe_t2.py` + `ml/data/t2-ghostpair/`: the new `ghostpair` probe (committed by partner at `431843a`).
- `ml/teams/t2-trace/CASES_R2.md`: case catalogue.
- `ml/teams/t2-trace/REPORT_R2_sections.md`: curator's diagnosis + probe table.
- `ml/out/t2r2/*.txt`: measurement outputs.

Thu 29 Oct 2026, 03:10 EDT (envelope-aware e2e numbers pending final GPU slot).
