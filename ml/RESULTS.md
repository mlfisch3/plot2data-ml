# Results

Measured 25 Oct to 1 Nov 2026 across five rounds of a research-contest cycle.
Current state: `main @ d72abb0` (120 → **162 pytest pass**).
Checkpoint `runs/t5r2-clutter/best.pt` + `--tta shift` + tick-reader `runs/ocr1/best.pt`.

The pipeline is the product of a five-team contest (axis / trace / precision / markers / robustness) that ran two full rounds plus three focused follow-up rounds, each round starting from the previous round's integrated baseline.
Each integration pass added measurement to the standard scoreboard based on failures the previous round surfaced; round 4 grew the real-chart benchmark from 30 to 110 charts with published data; round 5 fixed the catastrophes the expanded benchmark revealed.

Errors are a percentage of the plot's full height (the unit of `../ACCURACY.md`): 0.1% is a tenth of a percent of full scale.
"Simple" means at most three series and fewer data points than pixel columns.
"Good coverage" is the fraction of a true curve's pixel columns where the extraction is within 1% of the truth; a trace that wanders onto the wrong curve counts as wrong.

## Headline comparison

Comparing today's `main` with the pre-contest `v3` baseline (same v3 checkpoint, no code changes):

| | pre-contest v3 | **main (post 5 rounds)** | delta |
| --- | --- | --- | --- |
| mpl-val 200 line_found (all) | 55% | **69%** | +14 pt |
| mpl-val 200 line_rms_median (all) | 0.44% | **0.28%** | -36% |
| plotly-v1 150 line_found (all) | 75% | **82%** | +7 pt |
| plotly-v1 150 line_rms_median (all) | 0.27% | **0.20%** | -26% |
| Chart.js corpus worst-case (over 25 series) | 61.22% | **0.56%** | -99.1% |
| Chart.js corpus median | 0.067% | 0.071% | +0.004 pt |
| Chart.js corpus `offset-annotation` | 61.22% | **0.045%** | -99.9% |
| Real-world benchmark median (t5-real-100) | n/a (not built) | **0.37%** | - |
| Real-world benchmark within 0.5% | n/a | **50%** | - |
| Real-world benchmark failed charts | n/a | **20 / 110** | - |

The real-world benchmark did not exist at the start.
Team 5 built the 30-chart `t5-real` in round 1; round 4 expanded it to the 110-chart `t5-real-100` with FRED, OWID, World Bank, BLS, NOAA, GISS sources; round 5 fixed the catastrophic failures the expansion surfaced.

## End to end on synthetic charts

### Matplotlib validation set (200 charts, including house styles)

| | main, simple | main, all | v3, simple | v3, all | classical, simple |
| --- | --- | --- | --- | --- | --- |
| line series found (coverage > 50%) | 77% | 69% | 62% | 55% | 14% |
| good coverage of true curves | 67% | 56% | 51% | 41% | 11% |
| median RMS of found lines | 0.19% | 0.28% | 0.31% | 0.44% | 0.38% |
| peak_err_median_pct | 0.23% | 1.29% | 0.34% | 2.0% | 0.19% |
| envelope peak_err_median_pct (new metric, round 2) | 0.13% | 0.60% | n/a | n/a | n/a |
| markers found / precision | 81% / 84% | 61% / 73% | 64% / 74% | 48% / 64% | 5% / 4% |
| calibration within 0.5%, x / y (all) | | 91% / 90% | | 85% / 78% | |

The envelope-aware `peak_err_env_median_pct` is a round-2 metric: the ridge envelope was already produced by `extract.py` but was being stripped before scoring; the metric exposes a view of peak error that correctly handles columns where the drawn ink spans more than one pixel row.

### Plotly held out (150 charts; Plotly entered training in round 1 via v3)

| | main, simple | main, all | v3, simple | v3, all | classical, simple |
| --- | --- | --- | --- | --- | --- |
| line series found | 93% | 82% | 78% | 75% | 13% |
| good coverage | 88% | 70% | 70% | 61% | 11% |
| median RMS | 0.14% | 0.19% | 0.18% | 0.25% | 0.15% |
| peak_err_median_pct | 0.25% | 0.83% | 0.42% | 1.34% | - |
| markers found / precision | 84% / 91% | 40% / 81% | 76% / 78% | 42% / 77% | 32% / 16% |
| calibration within 0.5%, x / y (all) | | 99% / 89% | | 95% / 86% | |

## Chart.js corpus (end to end, `eval_corpus`)

`../corpus/` is the classical engine's own test set: 18 Chart.js charts tuned for it, a renderer PlotNet has never seen.
RMS over 200 points, % of full scale.
All 25 series found by every version from v3 onward; `main` reads correct line counts throughout.

| | main | v3 | classical |
| --- | --- | --- | --- |
| series median | 0.071% | 0.067% | 0.037% |
| worst case | 0.56% (log-log) | 61.22% (offset-annotation) | 0.074% (log-log) |
| offset-annotation (`1e6` multiplier) | **0.045%** (`WARN y axis: values scaled by 1e6`) | 61.22% | 0.032% |
| log-log coverage | 68% | 68% | 100% |
| retina-2x | 0.031% | 0.055% | 0.196% |
| log-y / log-y-multi | 0.059% / 0.056%, 0.019% | 0.170% / 0.177%, 0.021% | 0.043% / 0.047%, 0.048% |
| nogrid | 0.129% | 0.200% | 0.193% |

The classical engine still wins the easy-case median on its own corpus, but main dominates the hard cases: offset-annotation 61% → 0.045% (a 1,500× reduction), nogrid -35%, retina-2x -44%, log-y and log-y-multi roughly a third of the v3 figure.

## Real-world benchmark (`t5-real-100`)

110 real charts (237 series) with published numeric truth: FRED daily/monthly economic series, OWID country-level panels, World Bank and BLS synthesised from the official APIs, GISS global/hemispheric temperature, NOAA Mauna Loa CO2/CH4/N2O/SF6, and Chart.js in-the-wild captures.
Expanded from the 30-chart `t5-real` in round 4; is now in the standard scoreboard as of round 4's lesson that the round-1 integrator missed the regression on it.

| | main | round-4 baseline (`d55bcc7`) | round-1 integrated | pre-contest v3 |
| --- | --- | --- | --- | --- |
| median RMS | 0.37% | 0.57% | 1.86% (not expanded set) | n/a |
| median RMS of found | 0.33% | 0.54% | n/a | n/a |
| within 0.5% | 50% | 41% | 25% | n/a |
| within 1% | 59% | 48% | 28% | n/a |
| found (coverage ≥ 80%) | 76% | 63% | n/a | n/a |
| **failed** | **20** | 52 | 15 | n/a |

Round-5 wins: `fred-dgs10-dgs2` 32,752% → 2.76% (false-positive `1e3` from legend text); OWID billion-suffix labels (`owid-cumulative-co2` 49% → 0.12%, `owid-co2-per-capita` 110% → 0.23%, `owid-co-emissions-per-capita` 114% → 0.19%); five FRED charts whose y axes had no visible tick marks all recovered from `nan` or 70%+ error (`fred-dgs10-daily` 1.63%, `fred-dexuseu` 0.87%, `fred-fedfunds-small` 2.90%, `fred-mortgage-tiny` 4.19%, `fred-sp500` 0.88%, `fred-houst-thick` 5.12%, `fred-gdp-log` 0.44%, `fred-m2sl-log` 0.60%).

Per-source share of charts within 0.5%:

| source | n | within 0.5% | within 1% | failed |
| --- | --: | --: | --: | --: |
| BLS | 8 | 62% | 100% | 0% |
| World Bank | 33 | 82% | 85% | 3% |
| NOAA | 12 | 67% | 75% | 0% |
| OWID | 96 | 68% | 74% | 1% |
| FRED | 53 | 21% | 43% | 0% |
| GISS | 35 | 6% | 6% | 51% |

GISS is dominated by `giss-seasonal` (143 monthly curves overplotted) and the hemispheric/lat-band charts whose published CSVs carry more columns than the chart draws; these are either genuinely out of scope or ground-truth cleanup rather than extraction fixes.
FRED has a long tail of chart variants with 2-tick axes where the fit lacks redundancy.

## `examples/real/` screenshots

| image | main | notes |
| --- | --- | --- |
| 01 dashboard panels 1, 2, 3 | 1, 1, 1 lines (correct); x within 0.9 px, y within 2.6 px | no axis lines |
| 02 microprocessor trend (log y, 5 marker series) | 5 marker series (correct), y read as log | `10^k` labels still read as `0^k`, numeric value correct via `parse_value` |
| 03 women/men percent (news style) | 2 lines + 2 scatter + 2 end-value markers, x linear | round-4 regression fix restored |
| 04 hits per visit | 2 lines (correct) | |
| 05 retail sales | 1 line (correct); spikes traced to their tips | round-2 diagnosed as physically one series; round-1's "second line" was a model artefact |

## Tick reader

98.8% of 9,880 validation tick labels read exactly (string match).
Reader unchanged across all five rounds.

## The research-contest story

- **Round 1** (five pairs): axis structured decode, overlap-aware merge_fragments, source-pixel column measurement, source-pixel marker re-measurement, native-resolution inference + TTA + tolerant ROI. Integrated into `integration/round-1 @ 121ed4d` with the five teams' orthogonality analysis making the merge largely conflict-free. 110 pytest.
- **Round 2** (five pairs, revisit): t1 self-deferred everything as sub-1pt (correctly); t3 added joint-affine `refine_ticks` (-36% Chart.js corpus median via slope DOF; byte-identical in-distribution); t2 shipped the envelope-aware peak_err metric + a `--refine --tta` bugfix; t5 built a 30-chart real-world benchmark and used it to find that round-1's integration had regressed t5-real by 3× (axis_factor misfiring on sem-less multiplier text in cluttered dashboards). Round-2 integrated at `integration/round-2 @ 04659b6`; t4's line-snap patch was measured and rejected (team's premise contradicted by data: on dense line+markers charts, line is 4.6× worse than marker as an anchor). 117 pytest.
- **Round 3** (one agent): FRED `dgs10-daily` 760% → 3% via nice-step 2-tick axis tiebreak + canonical-label filter (reject leading-zero integer readings a tick locator would not print). Independent, cherry-picked onto main.
- **Round 4** (three agents): round-2 regression on 03-women-men fixed (sub-decade log penalty); FRED cluster recovery (five charts from `nan` or catastrophic to <5%, via gated weak-peak pass + virtual-tick label-only promotion + scorer bugfixes); real-chart benchmark expanded 30 → 110 with per-source distribution and new ground-truth loaders. The FRED fix cost mpl-val `line_found` 2 pp because the new fallbacks over-fired on healthy mpl-val axes.
- **Round 5** (three agents): mpl-val `line_found` recovered to 69% (above pre-fred) by gating the fallbacks on strong-peak confidence AND strip-share; OWID label-poisoning + billion-suffix recognised; FRED `1e3` false-positive rejected via spine-margin on the axis-factor scan. On the 110-chart real-world benchmark, failed charts dropped from 52 to 20, within-1% rose from 48% to 59%.
- The research-contest work lives on branches `team/t1-axis`, `team/t2-trace`, ..., `team/t5-robust`, `team/t1-axis-r2`, ..., `team/t5-robust-r2`, `team/t1-sparse-r3`, `round4/regressions`, `round4/fred`, `round4/benchmark`, `round5/mpl-val-tighten`, `round5/units`, `round5/owid` (in progress), plus `integration/round-1`, `integration/round-2`, and `site/showcase` (the local project website). Reports under `ml/teams/*/REPORT.md` document each team's deliverables; the two `INTEGRATION-REPORT*.md` files on the integration branches document the merge decisions.

## What limits accuracy now

Round-6 candidates in descending expected impact:

1. **FRED long tail**: 53 FRED charts yield 43% within 1%. The remaining failures are 2-tick axes with no redundancy. A tick-detector change (fire more candidates per axis) would be the single biggest lever on real-world coverage.
2. **GISS multi-column cleanup**: 35 GISS charts yield 6% within 0.5%, mostly because the published CSV has more columns than the chart draws. Either a per-chart "cols" whitelist in the GT, or a scorer relaxation that only penalises columns actually drawn.
3. **GISS seasonal**: `giss-seasonal` has 143 monthly curves overplotted; the extractor finds 53 fragments. Legitimately out of scope for the current pipeline.
4. **OWID small-multiples / stacked**: `owid-energy-mix` and `owid-military` are small-multiples or stacked-area layouts the pipeline treats as single-panel. A locate-then-zoom pre-processing pass would help.
5. **Chart.js `log-log` coverage** stays at 68%. A specialised log-log fit (fit in log-log space rather than extracting then transforming) would likely close this.
6. **Dense data** (more points than pixel columns) still returns one value per column; the envelope-aware metric is a visibility improvement but the pipeline itself still collapses.

The research product sits at `main @ d72abb0`.
`INTEGRATION-REPORT.md` and `INTEGRATION-REPORT-R2.md` on branches `integration/round-1` and `integration/round-2` document how winning changes were integrated; `teams/*/REPORT*.md` give per-team diagnostics.
