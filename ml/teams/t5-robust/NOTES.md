# t5-robust notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:44 EDT, brainstormer: what I read and the ranked candidates

Read BRIEF, ASSIGNMENT, README, RESULTS, all of p2d/ and the v3 baseline files and overlays.

Facts that shape the plan:

- The network is fully convolutional; the 768 x 512 canvas is a training convenience. Measured with runs/v3/best.pt in bf16: 1280 x 896 input runs in 0.89 GB, 1824 x 1312 in 1.7 GB. Native-resolution inference needs no tiling.
- Half of mpl-val is placed at scale under 0.72 (p10 0.44, min 0.39); Plotly median 0.86. The corpus is 900 x 560 (0.85) except retina-2x 1400 x 880 (0.55); the real set has 1579 x 937 (0.49) and 1255 x 596 (0.61).
- refine_ticks returns at once when plot_area is None, so a chart whose frame is not found keeps the network's label-offset bias on every tick (the nogrid 0.194% looks like that: the overlay shows no frame).
- Fixed source-pixel tolerances in refinement (tick-mark run width <= 3 px, search 2 px, marker window 9 px, strength >= 12 grey levels) do not scale with the device pixel ratio.
- In end-to-end scoring a chart whose calibration fails counts all its series as not found; e2e line_found 0.55 against 0.76 geometry-only. Calibration is t1's area.

Ranked candidates (expected gain on the standard scoreboard):

1. Native-resolution inference: run the network at scale min(1, pixel budget) instead of the fit scale, one pass, everything downstream unchanged. Expected: "all" split line_found +3 to +6 points, marker recall +5 to +10, peak error down on dense charts; "simple" +1 to +2; retina-2x 0.109% toward 0.05%; more markers on real 02. Risk: plot areas larger than any training canvas; fixed canvas-pixel tolerances in extract. A fine-tune with a zoom/crop augmentation (one more affine in data.py; targets are already rasterised after the transform) makes it in-distribution.
2. Frame-independent refinement: snap ticks to their marks without a plot_area (the axis line is where the tick anchors are), a fallback plot area from the tick anchors when corners fail, scale-aware tolerances (stroke width estimated from the axis line). Expected: nogrid 0.194% to about 0.04%; small gains in e2e tick error and frame-less charts (news, dashboards).
3. Test-time augmentation over scale (fit scale and native fused for heat and sem; embeddings from one pass). Flips are invalid (mirrored text). Expected: +1 to +2 points on tick recall and frame, cost 2x.
4. Wider domain randomisation plus a 3,000-iteration fine-tune from v3: paper tints and inversion, DPR 2 to 3 renders, UI clutter strips, stronger blur/JPEG/noise, random zoom crops. Expected: gains mostly on the corpus and real sets; needed anyway for 1 at large sizes.
5. A Chart.js or Vega renderer in training (curator's option): corpus median 0.067% toward 0.05%, by the Plotly precedent; costs hours.
6. Chart locator for cluttered screenshots: no scoreboard set contains clutter; a finding at best. Not now.
7. Colour canonicalisation (chroma/ink channels) and deskew from perpendicular axes: need retraining or address failures no set contains. Not now.

Going after 1 and 2 first, then 4 if a fine-tune is needed.

## Wed 28 Oct 2026, 01:57 EDT, brainstormer: baseline rows by scale, the curator's diagnosis, first changes

Baseline geometry rows (`evaluate --refine`, v3, out/t5/base-refine.json) by fit scale, simple charts: line_found 0.94 / 0.92 / 0.86 / 0.82 and RMS 0.07 / 0.33 / 0.21 / 0.26 % for scale < 0.5 / 0.5-0.7 / 0.7-1 / >= 1; marker recall 0.94 / 0.84 / 0.91 / 0.71.
So large charts are the easiest bin and small upscaled charts the hardest, the opposite of what I assumed.
Frame error p90 13 px is entirely the house-style presets (plain matplotlib p90 3.0 px; excel 24, highcharts 80, news 29, minimal 21, ft 15): on a chart without spines the frame is an invisible box.

The curator's 01:50 diagnosis (mail/to-brainstormer.md): the frame is found on every corpus case; nogrid is a renderer-specific label-to-tick bias (about 1 px) with nothing to snap to; the log-y ghosts are minor gridlines traced as lines; offset-annotation is a 5 px overlap the multiplier test rejects; the news x axis goes log because a log fit over 1970..2021 bends enough to take a misplaced label; and a frame more than 5 px off (43 to 70% of the no-spine presets) costs line_good_cov 0.565 to 0.45 through the ROI clipping in extract.

Changes so far (commits 72d21cf, 259b09d):

- `data.placement` / `extract.prepare`: native-resolution single-pass inference for charts larger than the canvas (scale 1, pixel budget 1.3 M, canvas in multiples of 32); `--fit-canvas` on evaluate, eval_corpus and eval_real for the ablation.
- `extract.refine_ticks` no longer needs the frame: outside band from the label side, gridline span from the other axis's ticks.
- `extract.extract`: ROI margin 5% of the frame instead of 1-3 px; legend symbols, tick labels and text excluded by their class; traced lines that are mostly GRID dropped.
- `pipeline.axis_factor`: the multiplier box may overlap the plot edge (centre test).
- `calibrate.fit_axis`: a log fit needs a decade or a label that says so (t1's file; one condition).
- `evaluate.draw` safe for non-finite coordinates.
- For a fine-tune: `--zoom` in train (crops at the inference scale, `_crop_shift`), y-label vertical alignment and pad randomised in mpl_render (30%), colour cast and inversion in augment_photometric (8%, 4%).

Measurement hygiene: the curator froze the 6b313e9 code at out/t5/base-code for "before" numbers; my queue out/t5/q1-* measures 259b09d.

## Wed 28 Oct 2026, 02:20 EDT, curator: first diagnosis, probe generators, real benchmark

- Diagnosis of the known failures (details in mail/to-brainstormer.md, 01:50): the frame is found on all of them; nogrid is the network's label-only tick bias on Chart.js y labels (0.8-1.0 px up, nothing drawn to snap to); log-y/log-y-multi ghosts are minor gridlines traced as lines; offset-annotation's 1e6 box is found but rejected by a 3 px tolerance; the news chart's x axis goes log because a linear fit loses one placed-by-hand label; OWID fails on "80 years" labels; FRED carries the same label bias (y resid 1.1 px) and snaps x ticks to recession-band edges.
- Measurement hygiene: all "before" numbers run from the judge's frozen worktree PLOT2DATA-teams/base (6b313e9); my tools take P2D_ROOT for that. A mixed-code run (the brainstormer's 259b09d landed mid-run) was discarded.
- Probe generator `p2d/synth/probe_t5.py`: factors dpr (true re-render at K x dpi), resize, jpeg, blur, dark, clutter, skew; renderers matplotlib, plotly, chartjs. data/t5-dpr1, t5-dpr2, t5-dpr3 generated (100 charts each, seeds 15,000,000-15,000,099; the same seed is the same chart; width medians 1004 / 2008 / 3012 px).
- Chart.js renderer `p2d/synth/chartjs_render.py` + `.mjs`: one headless Chrome, colour-only passes for the label maps (alpha deflated, not PNG), exact geometry from Chart.js's scales; checked by truth overlays on 12 seeds (out/t5/cjs-check). Generating data/t5-chartjs-val (100, seeds 15,200,000+) and data/t5-chartjs (4,000, seeds 15,100,000+) for the brainstormer's fine-tune. Cost about 1 s per chart at DPR 1 and 5-10 s at DPR 2 on the loaded machine (load average 34).
- Real benchmark: `teams/t5-robust/tools/fetch_real.py` fetched 30 charts with their published data into data/t5-real (12 OWID, 16 FRED, 1 GISS, 1 NOAA); `p2d/eval_t5real.py` scores them (RMS as % of the data span, coverage, found). Baseline run queued.
- Mistake: while stopping my own queue I matched another team's script name (t2's out/t2c/gpu2.sh) and killed it; reported to the judge. Kill only pids from a pattern naming t5.

## Wed 28 Oct 2026, 16:20 EDT, brainstormer (replacement): state at handover and plan

Identity: Opus 4.7, xhigh, replacement for the Fable 5.1 brainstormer (agent a2b7d3fe8c41cce03) terminated by the account cap at ~02:30 EDT.
Partner (curator) replacement: Opus 4.7 at aecd7d976deafcfd6, replacing a6cdf1f1dddf509f8.

Salvage: no information gaps that need the JSONL transcript - the predecessor committed everything load-bearing (five implementation commits plus curator tools and probe generators) and left a clean working tree.
NOTES, CASES, both mailboxes, every result file in out/t5/, the trained runs/t5-zoom/best.pt and the probe/benchmark data under data/t5-* are all intact.
Will do the JSONL salvage only if a question arises that none of these answers.

State of runs/t5-zoom (the brainstormer's zoom-crop fine-tune from runs/v3/best.pt): FINISHED 3000/3000 iters at 04:19 EDT (log.jsonl, best.pt=last.pt, 98 MB).
Training loss 2.54 to 2.31, val loss 2.97 to 2.49 (sem 0.169, heat 1.04, emb 2.55, markers heat val 0.343, lines heat val 0.049).
Nothing evaluated yet. Launched the four-set scoreboard sweep on it now (out/t5/zoom-eval.sh, logs out/t5/zoom-eval.log).

State of the TTA module (p2d/tta.py, wired in evaluate.py and pipeline.py, off by default): nothing measured.
Decision: keep off by default until I have a measured gain on the standard scoreboard; sweep shift / scale / shift+scale once the net-to-use is settled by the t5-zoom numbers.

Standing of the branch's pipeline changes against the frozen base (6b313e9 + v3 ckpt vs a7aed7d + v3 ckpt):

- Chart.js probe (`data/t5-chartjs-val`, 100): line_found 0.870 -> 0.886 (+1.6pp), line_rms_median 0.167 -> 0.160, frame_err_median 2.25 px -> 1.28 px, yticks_err 0.78 px -> 0.65 px.
  All four better.
  The pipeline changes land their main gain here, on the renderer the network has never trained on - the thing this team is for.
- Corpus (25 series, 18 charts, Chart.js at matplotlib-canvas sizes):
  median 0.067% -> 0.080%, worst 61.222% both times (offset-annotation).
  Half the simple cases regress a little (`linear-single-solid` 0.033 -> 0.080), log-y and log-y-multi gain ghost drops (4/1 -> 3/1, 5/2 -> 2/2), log-log regresses badly (2/1 -> 24/1 ghosts, cov 0%).
  Likely cause: native-resolution inference pushes a 900 x 560 chart from scale 0.85 to scale 1.0, into a part of input-scale space the net was not trained on; and the grid-ghost drop by `_mostly(..., sem[GRID])` does not catch Chart.js minor log gridlines (sem probably calls them DATA).
  Hypothesis: the t5-zoom fine-tune cures the first; a second gridline test (colour-near-paper, or periodicity) cures the second.
- mpl-val e2e (q1-e2e-native.txt, 72d21cf code + v3 ckpt): line_found 0.5466 -> 0.6030 (+5.6pp), marker_recall 0.4811 -> 0.5307 (+5pp), line_rms_median 0.4411 -> 0.2993 (-32%). frame_err_p90 13.17 -> 34.87 px (worse: ROI margin let the frame roam, likely).
- plotly e2e (q1-plotly-native.txt): line_found 0.7540 -> 0.7670, line_rms_median 0.2504 -> 0.2294, frame_err_p90 3.22 -> 3.00, calib_y_within_0.5pct 0.86 -> 0.89.
  Clean win.

Next, in order:

1. (running) t5-zoom on the four scoreboard sets.
2. Keep: 72d21cf native-res + frame-independent snapping, 259b09d furniture-excluded ROI, grid-ghost drop (improve to catch log minor), multiplier box relax, log-needs-a-decade - all appear to be net wins on the scoreboard-relevant sets.
3. Investigate the log-log corpus regression: either the ghost drop is wrong, the native pass drifts the frame on it, or there is a scale-dependent floor in the line head. Likely one line.
4. TTA sweep (shift, scale, shift+scale) on the chosen base net.
5. If a second ingredient is needed: a Chart.js-trained fine-tune using the curator's 4,000-chart `data/t5-chartjs` dataset at seeds 15,100,000+; 3,000 iters from the better of v3 or t5-zoom, with --zoom 0.35 kept.
6. Write REPORT.md.

Rules I will follow: baselines from `/PLOT2DATA-teams/base/ml`; GPU training through flock; `pkill -f` / `pgrep -f` always with `[p]2d.*t5` or similar in the pattern; one GPU inference at a time; tests must pass at the end.

## Wed 28 Oct 2026, 16:16 EDT, curator (Opus 4.7 replacement): handoff and resumed status

Predecessor a6cdf1f1dddf509f8 (Fable 5.1) ran about 90 minutes starting ~02:00 EDT, cut off by the usage limit at ~02:30 EDT. Account has reset; I inherit the branch head a7aed7d with everything the predecessor built: probe generators (dpr/resize/jpeg/blur/dark/clutter/skew), the Chart.js renderer through puppeteer, the real-chart benchmark (30 charts + loader + scorer), tools (probe_net, rows_by, corpus_profile, set_table, tick_bias, bs_compare, fetch_real), and six passing tests in ml/tests/test_t5.py. Working tree is clean; no in-flight t5-robust job.

Datasets on disk (seed-counted):
- data/t5-chartjs 4,000 charts (seeds 15,100,000+); for the brainstormer's fine-tune, if used
- data/t5-chartjs-val 100 (15,200,000+); the Chart.js validation probe
- data/t5-real 30 (12 OWID + 16 FRED + GISS + NOAA); the real benchmark
- data/t5-dpr1/2/3 100 each (same mpl seeds at 1x/2x/3x); the resolution probe
- data/t5-half (resize 0.5x), t5-up2x (resize 2x), t5-jpeg50/30, t5-blur, t5-dark, t5-clutter, t5-skew1 (1 degree); each 100 charts
- data/t5-mpl-va (brainstormer's; not mine)

Baseline numbers already in hand (frozen base code at 6b313e9 + v3 ckpt):
- Corpus: median 0.067%, worst 61.222% (offset-annotation), failed 0; one line in v3-corpus.txt. 25 series.
- mpl-val e2e: line_rms_median_pct 0.44% / 0.31% (all / simple). peak_err_median_pct 2.29 / 0.39. frame_found 0.89. See v3-e2e-ocr.txt.
- Plotly e2e (150): see v3-plotly-e2e.txt.
- chartjs-val baseline (frozen v3): line_rms_median_pct 0.3428 / 0.2845. yticks_err_median_px 0.75. calib_y_within_0.5pct 0.84.
- Probe sets at v3 baseline (base-code): blur, dark, clutter, skew1, jpeg50/30, half, up2x all captured.
- Real benchmark baseline: NOT YET valid. Predecessor tried `python -m p2d.eval_t5real` from the base worktree, which failed with "attempted relative import with no known parent package" because eval_t5real.py lives only on t5-robust. real-bench-v3.txt is empty. Need to run via a sys.path shim (as tick_bias.py does). Will do this.

Current-branch numbers at a7aed7d (= 259b09d for inference, since 36638e3 is training-only, 804b155 TTA is off by default, remaining commits are generators/tools/tests):
- Corpus: median 0.080%, worst 61.222%, 25 series, log-log found 24/1 (23 ghost series). Regression vs v3: +0.013% median, log-log ghost count exploded, offset-annotation NOT fixed (still 61.222%). See corpus-a7aed7d.txt / q1-corpus-native.txt (same code, same numbers).
- mpl-val e2e native (`--native` default): line_rms_median_pct 0.30 / 0.28 (all / simple), peak_err_median_pct 1.84 / 0.27, frame_found 0.90. See q1-e2e-native.txt. Big net improvement over v3 (0.44 / 0.31).
- Plotly e2e native 150: line_rms_median_pct 0.23 / 0.15, peak_err_median_pct 1.01 / 0.31, calib_y_within_0.5pct 0.887. See q1-plotly-native.txt. Also better than v3.
- chartjs-val at a7aed7d: line_rms_median_pct 0.3083 / 0.2523, yticks_err_median_px 0.64, calib_y_within_0.5pct 0.81. Small gain vs base on chartjs y residual (expected, from the yticks snap not needing a frame).
- Real benchmark at a7aed7d: 57% cover-ge-80%, median rms 0.48%, within 1% 42%, within 0.5% 35%, 18 failed of 60 series. 11 of 16 FRED y-axes still fail (y resid 1.1 px + no snap target). See real-bench-a7aed7d.txt.
- Tick bias (base code, v3 ckpt): chartjs y unsnapped carries -1.04 px median bias, 52% beyond 1 px; mpl and Plotly within 0.15 px. Confirms section 1 of CASES.md: this is the mechanism of nogrid 0.19% and most FRED y errors. See tick-bias-v3.txt.

Two concrete regressions worth the brainstormer's attention:
1. corpus log-log found 24/1 at a7aed7d vs 2/1 at v3. The 259b09d "drop a traced line that sem calls GRID by majority" did not work for log-log in native mode: 23 extra minor-log gridlines surviving as lines.
2. corpus offset-annotation 61.222% at a7aed7d, same as v3. The axis_factor relaxation IS in extract/pipeline, but the chart's `1e6` is still not being accepted. The box may no longer be in loose_labels at all after the 259b09d extract changes; probe_net.py can confirm.

I will not touch pipeline/extract/calibrate.py (brainstormer's area). I will investigate the chart-side evidence and feed it.

Plan for the next hour (brainstormer's zoom-eval.sh is currently on the GPU, pid 1086521):
1. Reply to brainstormer with the above numbers and point them to q1-e2e-native.txt / q1-plotly-native.txt (these ARE current-code baselines; inference has not changed since 259b09d).
2. Prepare a real-bench baseline shim (eval_t5real.py with P2D_ROOT = base/ml) and queue it to run after zoom-eval finishes.
3. Fill section 9 of CASES.md with the probe numbers now in hand.
4. Investigate the offset-annotation 61.222% at a7aed7d: dump extraction with probe_net.py and tell the brainstormer why axis_factor's new tolerance did not catch it.
5. Investigate the log-log 24/1: are the 23 extras minor log gridlines mislabelled as DATA by sem, or kept because the grid-majority test runs after a dilation on native-resolution pixels?

Housekeeping: pkill patterns will name `t5-robust` explicitly; usage_minder active at 50% consumed (pause at ~7.5M tokens left; currently at 14.85M).
