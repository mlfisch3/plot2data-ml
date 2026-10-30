# Results

Measured on Thu 29 Oct and Fri 30 Oct 2026.
The current app is `integration/round-2` + the round-3 FRED fix, promoted to `main` at commit `4d42ad7`.
Checkpoint: `runs/t5r2-clutter/best.pt` + `--tta shift`; tick reader `runs/ocr1/best.pt`.
120 pytest pass on `main`.

The pipeline is the research product of a five-team improvement contest that ran in two rounds plus one focused round-3 fix.
Each round the five teams (axis, trace, precision, markers, robustness) worked in isolated pairs (brainstormer plus curator); their winning changes were integrated and the integrated app became the baseline for the next round.
The integration from round 1 missed a catastrophic regression on real-world charts (axis-factor misfiring on sem-less multiplier text in cluttered dashboards); round 2 caught and fixed it.

Errors are a percentage of the plot's full height, the unit of `../ACCURACY.md`.
"Simple" means at most three series and fewer data points than pixel columns.
"Good coverage" is the fraction of a true curve's pixel columns where the extraction is within 1% of the truth; a trace that wanders onto the wrong curve counts as wrong, not as covered.

## End to end on synthetic charts

### Matplotlib validation set (200 charts, including house styles never trained on)

| | main (v4), simple | main (v4), all | v3, simple | v3, all | Classical, simple |
| --- | --- | --- | --- | --- | --- |
| line series found (coverage > 50%) | 75% | 69% | 62% | 55% | 14% |
| good coverage of true curves | 67% | 56% | 51% | 41% | 11% |
| median RMS of found lines | 0.19% | 0.28% | 0.31% | 0.44% | 0.38% |
| peak_err_median_pct | 0.23% | 1.29% | 0.34% | 2.0% | 0.19% |
| envelope peak_err_median_pct (new metric) | 0.13% | 0.60% | n/a | n/a | n/a |
| markers found / precision | 81% / 84% | 61% / 73% | 64% / 74% | 48% / 64% | 5% / 4% |
| calibration within 0.5%, x / y | 91% / 90% (all) | | 85% / 78% (all) | | |

Headline move since v3: `line_found` 55% to 69% end to end on all; 62% to 75% on simple.
Median RMS of found lines dropped 36% on all; marker recall rose 13 pt.

The envelope-aware `peak_err_env_median_pct` is a new scoreboard metric from round 2: the ridge envelope was already produced in extract.py but was being stripped before scoring; the metric exposes a view of peak error that correctly handles columns where the drawn ink spans more than one pixel row.

### Plotly held out (150 charts, no Plotly chart was in training before v3)

| | main (v4), simple | main (v4), all | v3, simple | v3, all | Classical, simple |
| --- | --- | --- | --- | --- | --- |
| line series found | 93% | 82% | 78% | 75% | 13% |
| good coverage | 88% | 70% | 70% | 61% | 11% |
| median RMS | 0.14% | 0.19% | 0.18% | 0.25% | 0.15% |
| peak_err_median_pct | 0.25% | 0.83% | 0.42% | 1.34% | - |
| markers found / precision | 84% / 91% | 40% / 81% | 76% / 78% | 42% / 77% | 32% / 16% |
| calibration within 0.5%, x / y | 99% / 89% (all) | | 95% / 86% (all) | | |

## Chart.js corpus (end to end, `eval_corpus`)

`../corpus/` is the classical engine's own test set: 18 Chart.js charts tuned for it; a renderer PlotNet never saw.
RMS over 200 points, % of full scale.
All 25 series found by every version; main lists correct line counts throughout.

| | main (v4) | v3 | Classical |
| --- | --- | --- | --- |
| series median | 0.071% | 0.067% | 0.037% |
| worst case | 0.563% (log-log) | 61.22% (offset-annotation) | 0.074% (log-log) |
| offset-annotation (1e6 multiplier) | 0.045% (`WARN y axis: values scaled by 1e6`) | 61.22% | 0.032% |
| log-log coverage | 68% | 68% | 100% |
| retina-2x | 0.031% | 0.055% | 0.196% |
| log-y / log-y-multi | 0.059% / 0.056%, 0.019% | 0.170% / 0.177%, 0.021% | 0.043% / 0.047%, 0.048% |
| nogrid | 0.129% | 0.200% | 0.193% |

The classical engine still wins the easy-case median on its own corpus, but main dominates the hard cases: `offset-annotation` 61% to 0.045% (a 1,500× reduction), `nogrid` -35%, `retina-2x` -44%, `log-y` and `log-y-multi` roughly a third of the v3 figure.

## Real-world benchmark (`eval_t5real`, `data/t5-real`)

30 real charts (FRED daily series, OWID country-level panels, GISS global mean, NOAA CO2, Chart.js in-the-wild) whose underlying data is published; each extraction is scored against the published numbers.
This set was built by team 5 in round 1 and was explicitly added to the mandatory scoreboard in round 2 after the round-1 integrator missed a regression on it.

| | base (v3) | round-1 integrated | **main (round-2 + FRED fix)** |
| --- | --- | --- | --- |
| median RMS | 1.86% | 1.98% (regressed) | **0.48%** |
| within 1% | 28% | 42% | **48%** |
| within 0.5% | 25% | 27% | **37%** |
| charts failed | 15 | 14 | 15 |

Round-2's axis-factor plausibility patch recovered the regression round-1 had missed; the round-3 fix added structured 2-tick nice-step tiebreaking that turned `fred-dgs10-daily` from a 760% error into a 3% error.

Residual real-world cases (round-4 candidates): `fred-dexuseu` 383% (TTA shift corrupts the 5-px label crop); `fred-houst-thick` 72% (two-tick axis still mis-fits); several FRED charts register as "could not calibrate from the tick labels".

## `examples/real/` screenshots

| Image | main (v4) | Notes |
| --- | --- | --- |
| 01 panels 1, 2, 3 | 1, 1, 1 lines (correct); x within 0.9 px, y within 2.6 px | Dashboard crops with no axis lines |
| 02 microprocessor trend (log y, 5 marker series) | 5 marker series (correct), y read as log | `10^k` labels still read as `0^k`, numeric value correct via parse_value |
| 03 women/men percent (news style, direct labels) | 4 series (lost 1 line), x mis-classified as log | Round-2 regression from the t5r2-clutter checkpoint; round-4 target |
| 04 hits per visit | 2 lines (correct) | |
| 05 retail sales | 1 line (correct) | Round-2 reduced spike recovery vs v3; round-4 target |

## Tick reader

98.8% of 9,880 validation tick labels read exactly (string match).
Reader unchanged across all three rounds.

## What limits accuracy now

Round-4 candidates in descending expected impact on the real-world benchmark:

1. 2-tick label calibration failures: several FRED and OWID axes still cannot calibrate because the pipeline only reads 2 labels and the fit has no redundancy; one of them is `fred-dexuseu` where TTA shift corrupts the label crop itself.
2. `03-women-men` regression (round-2): one line dropped and x fit as log; the t5r2-clutter checkpoint is slightly more conservative than t5-chartjs on direct-labelled news-style charts.
3. `05-retail-sales` regression (round-2): spike reading simplified from 2 lines to 1.
4. Chart.js scatter-markers filled-marker `w > 0.5` ink threshold (round-2 small corpus median regression).
5. log-log still at 68% coverage; a specialised log-log fit (fit in log-log space rather than extracting then transforming) would likely close this.
6. Dense data (more points than pixel columns) represented one value per column; envelope-aware metric is a visibility improvement but the pipeline still returns a single value.

The research product sits at `main @ 4d42ad7`.
`INTEGRATION-REPORT.md` and `INTEGRATION-REPORT-R2.md` on branches `integration/round-1` and `integration/round-2` document how each winning change was integrated; `teams/*/REPORT.md` and `teams/*/REPORT_R2.md` give per-team diagnostics.
