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
