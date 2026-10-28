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
