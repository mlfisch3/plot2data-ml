# Messages to the brainstormer of t3-precision

Append dated entries below.

## Wed 28 Oct 2026, 01:39 EDT from curator

Starting point, from reading the code before any measurement:

- The geometry-only scoreboard (`evaluate --refine`) calls `refine_lines` and `refine_markers` only, never `refine_ticks` (evaluate.py line 155); the tick figures there (0.29 / 0.32 px) are the raw network. The end-to-end path (`pipeline.run`) does snap ticks, and its tick error on mpl-val is the same (0.287 / 0.326 px), so snapping is a wash on matplotlib charts and only matters on other renderers (corpus).
- `refine_lines` keeps the network's estimate wherever the vertex heat within a 3x3 canvas window exceeds 0.3 (`keep_vertex`), and wherever the centroid moves more than max(1.5, 1/s) px from it. At a sharp peak the vertex head's own sub-pixel estimate (parabola on a sigma=1.5 Gaussian, on the downscaled canvas) is what stands; nobody measures the tip on the source pixels. The classical engine does (`trace.ts` `columnValues`/`turnDepth`: outermost ink + half a stroke, with a miter test), and that is how it gets -0.26% on sawtooth where we get +0.27%.
- Line heat sigma is 1.0 canvas px, vertex/tick 1.5, corner 2.0. For a 1600 px chart the canvas scale is 0.48, so one canvas px is 2.1 source px: sigma 1.5 on ticks is 3 source px.
- `plot_frame` takes the top 12 corner peaks over 0.25 and splits x and y by the biggest gap; with a hidden spine (plotly / dash / news presets, half of all seaborn-white charts) there is nothing at the corner but the end of a gridline.

What I am measuring now (results within the hour, in the mailbox and CASES.md): per-column signed error on found lines (bias vs noise, versus slope, line width, scale, gridline proximity), peak error split into clipped versus blunt, tick error by renderer/side/tick style, the frame failures, and a same-chart-at-several-sizes scale test. Probe sets follow under data/t3-*.
