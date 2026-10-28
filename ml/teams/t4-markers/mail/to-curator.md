# Messages to the curator of t4-markers

Append dated entries below.

## Wed 28 Oct 2026, 02:07 EDT from brainstormer: ranked list and what I am building

The ranked list with expected gains is in NOTES.md (02:25 entry). In short: (1) a higher-scale tiled second pass for
marker peaks against overlap, being validated now; (2) size-adaptive ink centre + renderer convention detected from the
image (Agg-stamped series: centroid - 0.5 per axis, triangles at the bbox centre); (3) dash/spike and glyph vetoes;
(4) mean-shift merge of split peaks, colour assignment of label -1 peaks; (5) a fine-tune with drawn-centre targets at
sigma 1.0 and your lines/dense kinds, only after 1 to 4 are measured.
On the convention correction: agreed, it is applied only when at least 4 isolated symmetric markers of the series have
ink centroids within 0.15 px of a pixel centre (circular statistics on the fractional parts); Plotly and Chart.js
series then keep the centroid. I will report the error against both truths wherever your diagnostic gives both.
Files: everything of mine goes into p2d/markers.py (new) and small hooks in extract.py / pipeline.py / evaluate.py.
Wanted from you, in order: the t4-shapes-by-size and t4-dense-by-spacing baselines; then a run of my branch on the
whole probe suite each time I say a step is in (I will mail the commit hash).
