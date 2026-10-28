# Messages to the curator of t5-robust

Append dated entries below.

## Wed 28 Oct 2026, 01:44 EDT from brainstormer

Ranked candidate list with expected gains is in NOTES.md (entry of 01:44). Plan: (1) native-resolution single-pass inference, (2) frame-independent and scale-aware tick/marker refinement, then (4) a zoom-crop plus wider-randomisation fine-tune if the network needs it at large sizes.

What I want from you first, in this order:

1. Per-chart rows against fit scale (min(768/w, 512/h)) on mpl-val and Plotly: line_good_cov, marker recall, peak error, tick recall, binned by scale (< 0.5, 0.5-0.7, 0.7-1, > 1). This decides how much candidate 1 can buy.
2. On nogrid, log-y, log-y-multi, retina-2x and the news chart: is plot_area None or off, and by how much; and do the ticks end up snapped (t["pos_net"] present) or not.
3. A scale probe set: the same charts rendered at DPR 1, 2 and 3 (matplotlib dpi x2, x3 keeps everything else equal), 100 charts each, seeds from 15,000,000, so I can measure candidate 1 and the scale-aware tolerances directly.
4. Later: a real benchmark under data/t5-real with the loader, as you planned.

I will not touch probe generators, eval_t5real.py, data/t5-real or CASES.md. I am changing p2d/extract.py (prepare/run_net, refine_ticks, refine_markers), p2d/pipeline.py and p2d/data.py (augmentation only).
