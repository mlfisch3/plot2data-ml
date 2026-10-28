# Team 5, "robust": charts the network has never seen

Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t5-robust`, branch `team/t5-robust`, seed base 15,000,000, run and data prefix `t5-`.

## Why this area

The pipeline must work on any screenshot, scan or PDF page, from any plotting library, at any size.
It trains on matplotlib and Plotly; the Chart.js corpus and the real screenshots are the only evidence about everything else, and both show losses: the `nogrid` offset, the `retina-2x` regression, the end values taken as markers on a news chart, the `1e6` multiplier, dashboard crops with no axis lines, dark themes.
The frame is not found on 11% of validation charts; p90 corner error is 14 px.
Large images are downscaled to a 768 x 512 canvas, which throws away resolution a careful reader would use.

## Known failure modes

- Renderers never seen: Chart.js, Highcharts, D3/Vega, ggplot2, Excel, Google Sheets, Bokeh, hand-drawn or scanned charts, charts photographed from paper (skew, lighting), charts in PDFs rendered at odd DPIs.
- Resolution: both ends; tiny thumbnails and 4K screenshots.
- Charts embedded in a page: dashboards with several panels, surrounding text, scroll bars, cursors, highlighted regions; charts cropped tight with no margin.
- Styling: dark themes, gradient fills, shaded bands, annotations, arrows, logos, watermarks, grid-heavy or grid-free, offset spines, broken axes, secondary y axes, inset panels.
- Noise: JPEG, screen-capture blur, moiré from re-photographing, anti-aliasing styles.

## Where to look first

`out/base/v3-corpus.txt`, `out/base/corpus-viz-v3/`, `out/base/real-v3/`, `out/base/v3-plotly-e2e.txt` against `out/base/v3-e2e-ocr.txt` (the Plotly gap before Plotly was in training shows what a new renderer costs); `data.fit_transform`, `data.augment_photometric`, `data._background`, `synth/presets.py`, `synth/plotly_render.py` (how a second renderer was added).

## Seeds of ideas (not a list to follow; beat it)

- Canonicalise the image before the network: estimate the paper colour and build chroma / ink channels so that data (coloured) and furniture (achromatic) separate; deskew and rectify using the perpendicular axes and equally spaced gridlines; normalise line widths and resolution by detecting the plot area first and re-rendering it to a canonical size.
- Tiles at native resolution with overlap, fused, instead of one canvas; or a two-stage pass: locate the plot panel, then run on the panel at full resolution.
- A third and fourth renderer in training (Chart.js and Vega through Chrome; `plotly_render.py` shows the pattern), and much wider domain randomisation (fonts, DPI, widths, themes, clutter).
- Test-time augmentation: scales, flips, small rotations; fuse heat maps.
- A separate "where is the chart" step for screenshots that contain more than the chart; multiple panels returned as multiple charts.
- Build a small real-world benchmark from charts whose data is published (FRED, Our World in Data, Wikipedia) so robustness is measured on real images, not inferred; put the images and the truth under `data/t5-real/` with a loader for `evaluate`.
