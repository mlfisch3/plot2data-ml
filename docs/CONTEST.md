# The research contest

How the plot2data-ml pipeline went from `v3` (`line_found` 55%, Chart.js worst case 61%) to today's `main` (69% / 0.56%) through a structured multi-agent research contest.

## 1. Why a contest

The post-v3 improvement list was long and heterogeneous.
Calibration from tick labels, series tracing through crossings, sub-pixel refinement, marker measurement, robustness to unseen renderers and screenshot clutter: five distinct problem areas, each with its own ideas and failure modes.
A single sequential effort would have had to pick an order; a parallel contest with explicit pairings turned the ordering into a dependency the pairs would resolve among themselves.

The brief, laid out in `ml/teams/BRIEF.md`:

- Five pairs of agents.
  Each pair owns one problem area and has two roles: a brainstormer who owns the ideas and the implementation under `ml/p2d/`, and a curator who finds failing cases, builds targeted probe sets with exact ground truth, measures the brainstormer's changes, and keeps a failure catalogue (`CASES.md`).
- A fixed scoreboard: `data/mpl-val` (200 synthetic matplotlib charts with house styles), `data/plotly-v1` (150 held-out Plotly), `../corpus/` (18 Chart.js charts with published data), `examples/real/` (five real screenshots with hand-measured anchors).
  Each team compares its "before" (frozen baseline worktree) and "after" (its own worktree) using the same commands.
- Each team's own worktree, branch, and probe-set namespace.
- Shared machine rules: a single flock on `ml/out/gpu.lock` serialises GPU work; `nice -n 19` and `OMP_NUM_THREADS=2` for everything heavy; `pkill`/`pgrep` patterns must name the team directory (never a generic script name).
- A judge (the main Claude Code session) integrates the winners.

The judging rules were spelled out:

1. Measured scoreboard improvement, weighted to the standard sets, accuracy over speed.
2. Generality: a gain across matplotlib, Plotly, Chart.js and real screenshots, not only the team's own probe set.
3. No unreported regressions.
4. Honesty and clarity of the report.
5. Simplicity of the implementation, last.

Teams were explicitly allowed to write ugly code, large code, new models, chained models, pre-processing steps, or whatever moved the measured scoreboard.
Research cost was not a constraint; result was.

## 2. The teams

- **t1-axis** - calibration from tick labels; the biggest end-to-end loss at the start.
- **t2-trace** - finding every line series and following it to the end: crossings, same-colour pairs, fragmentation, hopping between curves.
- **t3-precision** - the last fraction of a pixel on lines, turning points, ticks and the frame; the gap between the classical engine and the ML pipeline on the Chart.js corpus.
- **t4-markers** - every drawn marker returned exactly once at its true centre; nothing else returned as a marker.
- **t5-robust** - renderers the network has never seen, resolutions, clutter, photographed and scanned charts.

Each pair's `ASSIGNMENT.md` named the known failure modes, pointed at the files the pair would touch, and listed seed ideas without constraining the pair to them.
Agents were told to work from assumptions where they must and to ask their partner to check them with images.

## 3. Round 1 - the five submissions

Each pair worked for roughly 90 minutes before the Fable 5.1 account hit the five-hour usage window and the whole fleet died.
A pause-and-resume protocol would land in a later round of the research cycle; at that moment the response was to spawn ten Opus 4.7 replacements, each pointed at the full JSONL transcript of its predecessor plus the two files (`NOTES.md`, `CASES.md`) the predecessor had committed.
The replacements picked up where the originals left off; the brainstormer-curator pairings and the team-directory ownership were preserved.

### Submissions

- **t1-axis** (`team/t1-axis @ 3c73e75`) - `ml/p2d/axis.py` (389 lines), the structured axis decoder: beam-search top-k CTC readings per label, RANSAC over pairs for linear or log, score each hypothesis by inliers + nice-step bonus + expected-text penalty + log-decade enforcement.
  Also `extract.py` additions (colour-aware label finder, tick-mark masking, raw-ink along-axis extent), a `pipeline.py` axis-end multiplier scan, a 90-degree rotation of tall label crops in the OCR normaliser, and the `_OFFSET` regex tightening that killed a false positive on `9000096/x`.
  Headline: mpl-val `line_found` 55% → 66% end to end, both-axes-within-0.5% 67.5% → 83.0% (+15.5 pt), Chart.js `offset-annotation` 61.22% → 0.019%.
- **t2-trace** (`team/t2-trace @ 4ab8ee0`) - a 60-line rewrite of `merge_fragments` in `extract.py` with Hungarian assignment for overlap-aware joining.
  Headline: parallel-probe `line_found` +0.100 (0.71 → 0.81), shallowx `line_found` +0.108, legend `line_found` +0.041; mpl-val `line_found` all +0.024 end to end.
- **t3-precision** (judge took `team/t3-precision @ 8053952` after discovering 9b82fba HEAD had regressed) - new `ml/p2d/measure.py` (~450 lines): full-column source-pixel measurement with stroke-width-aware weighting, flank-fit vertex intersection, and butt-cap handling.
  Headline: simple line_rms_median -28%, Chart.js corpus `log-log` -43%, `linear-dashed` -52%.
- **t4-markers** (`team/t4-markers @ 5766131`) - new `ml/p2d/markers.py` (555 lines): Gaussian-mixture peak measurement, dash veto, iso elongation filter, sem[TEXT] veto for digit false positives.
  Headline: `--refine` marker precision +5-7 pp, marker err -32% to -47%, false-positive counts on no-marker charts -17%.
- **t5-robust V1** (`team/t5-robust @ bd6a491`) - native-resolution inference (no downscaling for images that fit), `--tta shift` TTA fusion, tolerant ROI (furniture classes dropped from frame search, grid ghosts dropped, multiplier box test, log fits require a decade), and the house-style zoom-crop training augmentation.
  Headline: mpl-val line_rms -36%, Chart.js worst case 61.22% → 0.58%, real-screenshot wins on dashboard panels.
- **t5-robust V2** (`team/t5-robust-chartjs @ 4b80228`) - V1 code + a 3,000-iter fine-tune on 4,000 synthetic Chart.js charts (`data/t5-chartjs`), rendered through Chrome puppeteer with exact ground truth.
  Trade: wins on Chart.js (nogrid -37%, dpr3 -20%, tick-bias halved) and on the first version of the real-world benchmark (median rms 0.75 → 0.61, within-0.5% +12 pp), small regression on matplotlib `line_rms_median` (+16%).

### Integration pass

A dedicated integrator agent read the five teams' orthogonality analysis (prepared by the brainstormers themselves) and merged into `integration/round-1 @ 121ed4d`:

- base: t5 V2 (changes to `extract.prepare`, `run_net`, `extract`, `refine_lines`, `refine_ticks`, `refine_markers`; `Extraction` dataclass extended; `calibrate` log-decade; new `tta.py`)
- plus: t2 overlap-aware merge_fragments (lines 544-694 of pre-contest `extract.py`, no overlap with t5's region)
- plus: t3 `measure.py` (new file) and `refine_lines` delegation
- plus: t4 `markers.py` (new file) and marker branch of `extract`
- plus: t1 `axis.py` + bottom-of-`extract.py` additions + `pipeline.py` rewrite of `run` + `ocr.py` additions

One real conflict (teams 3 and 5 both edited `refine_ticks`), resolved as a hybrid: team-5's label-box-aware per-tick line finder feeds team-3's offset-only median shift post-processing.
Two minor conflicts in `extract.py` imports and `Series` dataclass, both additive.
110 pytest pass.
INTEGRATION-REPORT.md documents the merge decisions and the before/after numbers.

### The round-1 lesson

The round-1 integrator used the standard mpl-val / Plotly / Chart.js / examples-real scoreboard.
It did not run team 5's new 30-chart real benchmark (`data/t5-real`).
This missed a catastrophic regression: integration added t1's strip-end multiplier scan (needed for Chart.js `offset-annotation`) but the scan fired on sem-less text in cluttered dashboards (OWID's "would" subtitle decoded as "1e1", a legend fragment decoded as "1e3"), destroying the real-world median from V2's 0.61% to the integrated version's 1.98%.
Round 2 would catch and fix it; the lesson was that every integration pass must run every team's benchmark.

## 4. Round 2 - revisit against the integrated baseline

Each of the five pairs re-spawned, this time with the integrated branch as its "before" baseline and with the explicit diminishing-returns rule: "if your target is a sub-1pt scoreboard gain for substantial new code, STOP and defer with a documented diagnosis".

Outcomes:

- **t1-axis-r2** - DEFER on all five angles. Oracle ceiling analysis showed y has only ~1.5 charts of headroom; of the 19 x failures, 15 are OCR-level issues the structured decoder cannot rescue. One late finding (`_OFFSET` regex false positive on bare integer "-10") landed as a one-line merge-time fix.
- **t2-trace-r2** - the "plotly simple -0.019 e2e" ticket from round 1 had already been closed by the integration (the t5-chartjs cleaner ridges obviated the ghost+ghost merge).
  Shipped: envelope-aware peak_err metric (10-line plumb exposing a ridge envelope that extract.py was already producing but evaluate.py was stripping; mpl-val `peak_err_env_median_pct` 1.35 → 0.60 at `--refine`) + a `--refine --tta` without `--ocr` UnboundLocalError bugfix + new `ghostpair` probe.
  Candidate A (ghost+ghost guard) measured as net negative and reverted.
- **t3-precision-r2** - joint-affine `refine_ticks` replacing shift-only.
  The slope DOF turned out to be the win-source: Chart.js corpus median 0.087% → 0.056% (-36%) via correcting a per-axis scale drift that only appears on out-of-distribution renderers.
  mpl-val and plotly-v1 byte-identical to integration (the min_shift gate correctly declines in-distribution).
  Regressions log-log +0.342pp and retina-2x +0.084pp, both within the integration-report tolerance.
  Shipped with a `T3R2_SHIFT_ONLY=1` env var escape hatch.
- **t4-markers-r2** - attempted y-snap of markers to the traced line for line+markers series.
  Measurement: patch regressed every marker metric on the dense-line+markers probe (marker is 4.6× better than line as an anchor on those charts).
  REJECTED by the integrator.
- **t5-robust-r2** (V3) - caught the integration-missed t5-real regression (0.61% V2 → 1.98% integrated → 0.42% V3).
  Shipped: axis_factor patch (cap `|exp| ≤ 15` + gate on existing-labels max magnitude > 1000, keeping the `offset-annotation` legitimate case) plus a 3,000-iter clutter fine-tune on `data/t5-clutter`.
  Headline: t5-real median 1.98% → 0.42% (-79%), clutter-overlap frame_err_p90 -83%, chartjs-val frame_err_p90 -46%, mpl-val line_rms_median -8%.

Integration pass: `integration/round-2 @ 04659b6`.
Merged t5-V3 base + t3 joint-affine + t2 envelope metric + t2 bugfix.
Resolved one conflict (both t2 and t3 shipped the same `--refine --tta` bugfix; took t2's cleaner commit).
t4 patch applied and remeasured, measured regression confirmed, backed out.
Added `data/t5-real` to the mandatory scoreboard (the round-1 lesson).
117 pytest.

## 5. Rounds 3-5 - focused fixes and benchmark expansion

### Round 3

One agent, one target: `fred-dgs10-daily` was still showing 760% RMS error on t5-real.
Diagnosis found the error was on the y axis (not x as the brief had assumed): the OCR was reading a 3-pixel-wide "1" crop as "13" with higher log-probability, and the 2-tick decoder preferred the wrong one.
Fix (11 lines in `ml/p2d/axis.py`): reject leading-zero integer readings a tick locator would never emit, plus a nice-step bonus for 2-tick hypotheses.
Result: 760% → 3%.
No regression on the standard scoreboard.

### Round 4

Three agents on parallel targets:

- **round4/regressions** - the two documented regressions on `examples/real/`.
  Fixed: `03-women-men-percent` x axis mis-classified as log (sub-decade log penalty in `axis.decode_axis`, 11 lines).
  Deferred correctly: `05-retail-sales` 2 lines → 1; HSV histogram proved the chart physically has one series, so round-1 integrated's "second line" was a model reconstruction artefact, round-2 was right.
- **round4/fred** - the FRED cluster: 5 catastrophic charts (dexuseu 383%, fedfunds nan, mortgage nan, sp500 nan, houst 72%).
  Diagnosed: FRED charts draw y labels without tick marks, so the YTICK heat peaks are too weak to cross threshold.
  Fixed with (a) a weak-peak gated pass that fires only when ≥2 unclaimed label boxes remain in the strip, (b) a `_promote_label_only_ticks` fallback that turns unclaimed label boxes into virtual ticks when the strong pass found < 2 ticks on an axis, (c) scorer bugfixes in eval_t5real (date-axis conversion, correct log/linear transform using fit result instead of URL hint).
  Headline: 5 of 5 catastrophic charts recovered (dexuseu 383 → 0.87, dgs10-daily nan → 1.63, fedfunds nan → 2.96, mortgage nan → 4.19, sp500 nan → 0.88, houst 72 → 5.12).
  Cost: mpl-val `line_found` -2 pp (the new fallbacks over-fired on healthy mpl-val axes); round 5 would recover it.
- **round4/benchmark** - expanded the real-chart benchmark from 30 to 110 charts.
  Added 80 new real charts across FRED, OWID, World Bank (synthesised with the publisher's data), BLS (synthesised), NOAA, GISS, each with the published numeric truth and a GT loader in `eval_t5real`.
  Current `main` scored 48% within 1% on the expanded set, 52 charts failed.
  Six new failure patterns catalogued for future rounds: FRED y "could not calibrate", OWID country-end-labels poisoning y calibration, scale-factor units misread, FRED `1e3` applied wrong direction, GISS multi-column CSVs, NOAA chart window vs CSV window.

### Round 5

Three agents, targeting the round-4 cost and the round-4 benchmark's new patterns:

- **round5/mpl-val-tighten** - gated the round-4 FRED fallbacks on strong-peak confidence AND strip-share so they do not fire on healthy mpl-val axes.
  Result: mpl-val `line_found` 0.6725 → 0.6941 (above pre-fred baseline).
  All 7 FRED recoveries hold or improve (two improved: fred-gdp-log 0.90 → 0.44, fred-m2sl-log 1.04 → 0.60).
  Byte-identical on plotly, corpus, examples/real.
- **round5/owid** - OWID country-end-labels poisoning y calibration (7 charts, ~20 series lost in round 4).
  Fixed: `_drop_offside_ticks` in extract.py (drop minority-side anchors against a 3+ majority), lax parse_value for garbled OCR of composite labels ("0 births", "80,000 kWh", "1 billion t"), spine-margin filter in axis_factor.
  Result: 5 of 7 OWID targets recovered to <5% RMS. Original t5-real: within-1% 48% → 62%, failed 13 → 1.
- **round5/units** - OWID scale-factor units + FRED `1e3` wrong direction.
  Diagnosed: not a direction bug but a false positive (the strip-end scan picked up legend text as `1e3`); plus the OCR charset doesn't include `i`/`m`/`h`/`W` so OWID word suffixes come through as fragments.
  Fixed: lenient word-form suffixes in parse_value (billion, trillion, million, thousand, bn, mn), alignment-to-step prior in decode_axis (fits whose values sit on a nice-step grid beat offset-from-grid alternatives), dedup search by `(scale, tick → value)`, spine-margin filter in axis_factor.
  Result: fred-dgs10-dgs2 32,752% → 2.76%, owid-cumulative-co2 49% → 0.12%, owid-co2-per-capita 110% → 0.23%, owid-co-emissions-per-capita 114% → 0.19%.
  Aggregate on t5-real-100 (110 charts, 237 series): within-1% 48% → 59%, within-0.5% 41% → 50%, failed 52 → 20.

Integration pass: cherry-picked each round-4 and round-5 branch onto `main` in sequence.
The round-5 merges had a conflict in `test_core.py` (both t5-units and t5-owid added tests after the same base function) and in `ocr.py parse_value` (both branches reworked suffix parsing differently); the resolution merged the owid lax architecture with the units rich suffix table, requiring a narrower strict regex to avoid the engine backtracking around the optional suffix clause.
178 pytest pass on main at `0c0793b`.

## 6. Headline results

Full numbers in `ml/RESULTS.md`.
Comparing today's `main` to the pre-contest `v3`:

| set / metric | pre-contest v3 | main |
| --- | --- | --- |
| mpl-val 200 line_found (all) | 55% | 69% |
| mpl-val 200 line_rms_median (all) | 0.44% | 0.28% |
| mpl-val both-axes-within-0.5% | 68% | 83% |
| plotly-v1 150 line_found (all) | 75% | 82% |
| plotly-v1 150 line_rms_median (all) | 0.27% | 0.20% |
| Chart.js corpus median (25 series) | 0.067% | 0.071% |
| Chart.js corpus worst case | 61.22% (`offset-annotation`) | 0.56% (`log-log` 68% coverage) |
| Chart.js corpus `offset-annotation` | 61.22% | 0.045% |
| Chart.js corpus `retina-2x` | 0.055% | 0.031% |
| Chart.js corpus `nogrid` | 0.200% | 0.129% |
| t5-real-100 (110 real charts) within-0.5% | n/a (benchmark not built) | 50% |
| t5-real-100 within-1% | n/a | 59% |
| t5-real-100 failed | n/a | 20 |

The classical engine still wins the easy-case median on its own corpus (0.037%), but the ML pipeline dominates on every hard case and on every real-world chart it has been tested on.
`fred-dgs10-daily` alone moved from "unreadable" to 3% error through round 3; the aggregate on the expanded benchmark shows the same trajectory for OWID country-level panels and FRED daily series after rounds 4 and 5.

## 7. Lessons learned

- **Benchmarks win rounds.**
  Round-2's biggest find (axis-factor misfiring) came from team 5 building a 30-chart real-world benchmark that round-1's integrator had not run against.
  Round-4's benchmark expansion to 110 charts surfaced six new failure patterns that drove rounds 5 and beyond.
  Each integration pass now runs every benchmark that any team ships; the mandatory scoreboard grows with the research.
- **The pair structure made negative results cheap.**
  The curator's "my measurement shows the brainstormer's patch regresses the probe" was the fastest way to kill a bad fix.
  t4-r2's y-snap patch was built, measured, and rejected inside a single round; a sequential effort would have shipped it.
- **Diminishing returns is a discipline, not a feeling.**
  Round-2 was told explicitly to defer sub-1pt-for-substantial-code changes; t1-r2 did exactly that, with a documented oracle-ceiling analysis.
  Teams that did not pivot (t4-r2) consumed a round and shipped nothing; teams that did (t5-r2 to the axis_factor fix) delivered the round's biggest win.
- **Integration conflicts concentrate in exactly the files multiple teams independently find valuable.**
  `refine_ticks` was touched by rounds 3 and 5 beyond the original round-1 collision between t3 and t5; `parse_value` was touched by both t5-units and t5-owid.
  Having the merging agent read the brainstormers' orthogonality analyses first was the single biggest time-saver.
- **The scorer is part of the system.**
  Multiple rounds caught scorer bugs (round-2 the ridge envelope being stripped before scoring; round-4 the log/linear transform being chosen from the URL hint instead of the fit; round-5 the eval_t5real loader kinds).
  A scoreboard that measures the right thing is as important as a pipeline that extracts the right thing.

## 8. Where to find each piece

- Reports: `ml/teams/<team>/REPORT.md`, `REPORT_R2.md`, `REPORT_R3.md`, where present.
- Catalogues: `ml/teams/<team>/CASES.md` and `CASES_R2.md`.
- Integration reports: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integration/INTEGRATION-REPORT.md`, `/home/drd/PROJECT/CLAUDE/PLOT2DATA-integ-r2/INTEGRATION-REPORT-R2.md`.
- Round-5 ocr-merge debrief: inline in commit `0c0793b` on `main`.
- Branches on origin (all pushed to `mlfisch3/plot2data-ml`): `main` plus `team/t[1-5]-*`, `team/t[1-5]-*-r2`, `team/t1-sparse-r3`, `round4/{regressions,fred,benchmark}`, `round5/{mpl-val-tighten,owid,units}`, `integration/round-1`, `integration/round-2`, `site/showcase`.
- The project website (static showcase with 15 real extractions, pipeline diagram, team-by-team story): `site/showcase` branch at `/home/drd/PROJECT/CLAUDE/PLOT2DATA-site`, open with `python -m http.server 8080 --directory site` and visit `http://localhost:8080`.

## 9. What is still being left for round 6+

From `ml/RESULTS.md` section "What limits accuracy now", in descending expected impact on the real-world benchmark:

1. FRED long tail - 53 FRED charts yield 43% within 1%; the remaining failures are 2-tick axes with no redundancy.
2. GISS multi-column cleanup - 35 GISS charts yield 6% within 0.5%, mostly because the published CSV has more columns than the chart draws (GT quality rather than extraction).
3. GISS seasonal - 143 monthly curves overplotted; out of scope for the current pipeline.
4. OWID small-multiples - `owid-energy-mix`, `owid-military`; a locate-then-zoom pre-processing pass would help.
5. Chart.js `log-log` stays at 68% coverage; a specialised log-log fit (fit in log-log space) would likely close this.
6. Dense data (more points than pixel columns) still collapses to one value per column; the envelope-aware metric is a visibility improvement but the pipeline itself still does not return the envelope.

Which of these is next, if any, is a research decision rather than a measurement artefact.
