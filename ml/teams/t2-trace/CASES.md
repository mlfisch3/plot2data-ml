# t2-trace failure catalogue

Curator's record of how the current network (`runs/v3/best.pt`) loses line series, measured geometry only (`evaluate --refine`, true tick values), with the probe sets that reproduce each failure.
Numbers are from `out/t2c/` (per-chart rows `rows-val.json`, `rows-plotly.json`; per-series tables `series-val.csv`, `series-plotly.csv`; staged inspection `inspect-val.txt`, composites `inspect-val/<seed>.png`).
Tools: `teams/t2-trace/tools/analyze_rows.py` (per-series tags from the rows), `inspect_stages.py` (which decoding stage loses a series, by wrapping `p2d.extract`), `embcheck.py` (embedding at crossings and between same-colour series).
Probe generator: `p2d/synth/probe_t2.py`, seeds 12,000,000 + 10,000 x case; data under `data/t2-<case>`.

## 1. Baseline (v3, geometry only)

| | mpl-val all (461 series) | mpl-val simple (149) | plotly-v1 all (309) | plotly simple (107) |
| --- | --- | --- | --- | --- |
| line_found | 0.757 | 0.886 | 0.861 | 0.972 |
| line_cov_mean | 0.667 | 0.815 | 0.794 | 0.927 |
| line_good_cov_mean | 0.588 | 0.764 | 0.726 | 0.897 |
| line_rms_median_pct | 0.311 | 0.189 | 0.190 | 0.146 |
| line_rms_p90_pct | 2.23 | 1.38 | 1.57 | 0.69 |
| peak_err_median_pct | 1.77 | 0.31 | 1.14 | 0.35 |

Per series, mpl-val: 112 of 461 not found (cov <= 0.5), 223 found with good coverage < 0.9, 87 found with RMS > 1%.
Simple split: 17 of 149 not found, 58 partial.
Plotly: 43 of 309 not found (3 of 107 simple), 128 partial.

How the metric counts: a true series is matched to at most one returned line, by Hungarian assignment on `median|dy|/ph + 0.5 (1 - overlap)`, and a match costs under 0.2, so a returned piece has to cover more than about 60% of the series to match at all.
A series returned as two halves is therefore "not found" and its good coverage is at most the larger half.
Fragmentation is counted twice.

## 2. What the lost and partial series look like (mpl-val, tags from the ground truth)

Lost rate by structure (`out/t2c/analyze-val.txt`):

| tag | n | lost | partial (found, good < 0.9) |
| --- | --- | --- | --- |
| no crossing with another series | 125 | 7% | 39% |
| 3 to 9 crossings | 94 | 19% | 47% |
| 10 or more crossings | 217 | 37% | 57% |
| within 3 px of another series on 30%+ of columns | 15 | 60% | 40% |
| line width < 1.2 px | 57 | 53% | 26% |
| line width >= 3 px | 170 | 18% | 51% |
| dotted (`:`) | 28 | 39% | 43% |
| dashed (`--`) | 42 | 24% | 60% |
| area series | 24 | 54% | 38% |
| 1 line series in the chart | 47 | 2% | 40% |
| 6 line series in the chart | 102 | 44% | 49% |
| plot height < 250 px | 69 | 41% | 41% |
| steepness p90 >= 8 px per column | 107 | 21% | 74% |
| density >= 1 point per column | 85 | 27% | 61% |
| legend box inside the plot | 141 | 32% | 50% |
| same colour as another series | 13 | 38% | 23% |

The line-width effect is a canvas-scale effect: by width on the 768 x 512 canvas (source width times the placement scale), under 0.7 px 48% lost (n = 48), 0.7-1.0 px 30% (60), 1.0-1.5 px 18%, 1.5-2.5 px 17%, over 2.5 px 24%.
Both extremes of scale hurt: charts scaled below 0.5 (wide figures) lose 28%, charts upscaled (scale >= 1, small figures) lose 32%, the middle 17-20%.
The ridge heat is present on these thin lines all the same (section 3), so they are lost in the decoding, not in the network.

Plotly (`analyze-plotly.txt`): lost 3% with no crossing, 24% with 10+ crossings, 53% when within 3 px of another series on 10-30% of columns; dashed (`dash`) 28% lost; 4-5 series charts 22-29% lost; plot height < 250 px 26% lost.

## 3. Where the pipeline loses them (staged inspection)

The network's line heat is present on the true curve in every case but three (heat coverage >= 0.97 on 458 of 461 series).
Everything is lost in the decoding, in this order of frequency (counts to be filled from the corrected `inspect-val.txt`):

1. **Embedding split into long pieces that are never joined.** The greedy mean-shift clustering (radius 1.5, at most 16 centres) puts one series into 2-5 clusters along its length (the embedding drifts with context: see the PCA panel of `inspect-val/9000018.png`, where the oscillating series changes colour from left to right).
   Each cluster is chained separately, so the series comes back as 2-3 long pieces (examples: 9000080 s1 371+213 columns, 9000108 s2 399+208, 9000041 s1 206+258, 9000156 s0 240+253, 9000175 s1 416+322, 9000162 s0 186+135+88).
   `merge_fragments` does not re-join them: the pieces' mean embeddings differ by more than `emb_tol` (3.0) precisely because the clustering separated them, and/or their ends overlap by more than 8 columns in the transition.
   Every one of these would be "found" at coverage ~0.9 if the two pieces were joined.
2. **Hopping at crossings within one cluster** (`peel_chains`): the DP maximises collected heat minus 0.5 per pixel of vertical gap, so where two curves of one cluster cross at a shallow angle, it follows whichever continues with less vertical gap, which at a shallow crossing is a coin toss.
3. **Steep series break at any interruption.** A chain's gap cost and `merge_fragments`' gap rule (`gap <= 3 + 2 dx`) are in vertical pixels; a series moving 60 px per column (9000018 s2) can never be bridged across a 3-column interruption, so steep oscillations fragment wherever a crossing takes a few columns to another cluster.
4. **Dense and steep curves are represented one value per column**: for a run longer than 5 px `column_runs` takes the heat centroid of the run, which for a zigzag of 20-40 px per column is 10-20 px from the truth at the column centre; these are "found" with good coverage 0.1-0.5 (9000031, 9000068, 9000184, 9000079).
5. **Spurious pieces**: the ghost traces beside thick lines and the fragments of crossings return 2-5x as many lines as there are series (9000031: 13 lines for 2 series; 9000144: 17 for 3), which drags the Hungarian matching and the marker-row filter.

### How much a decoder can win

"Dense/steep" below means more than 1 data point per pixel column, or a steepness p90 of 8 px per column or more: there one value per column is the limit (C4), not separation.
The rest is separation territory (C1, C2, C3, C5).

| set | series | of which separation territory | share of the good-coverage deficit in separation | ceiling if separation were perfect (found / good cov) |
| --- | --- | --- | --- | --- |
| mpl-val all | 461 | 312 (77 lost, 125 partial) | 60% | 0.924 / 0.835 (0.803 at the 0.953 good cov of single-series charts) |
| mpl-val simple | 149 | 119 (13 lost, 37 partial) | 69% | 0.973 / 0.926 |
| plotly all | 309 | 192 (20 lost, 62 partial) | 42% | 0.926 / 0.841 |
| plotly simple | 107 | 91 (3 lost, 17 partial) | 74% | 1.000 / 0.973 |

## 4. Probe sets

All at seeds 12,000,000 and above, 100 charts each, built with `python -m p2d.synth.probe_t2 --case <name> --count 100 --out data/t2-<name>`.
Baseline: `python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/t2-<name> --refine`.

| case | what it provokes | series | found | cov | good cov | rms median | rms p90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross | 2-4 smooth sines of distinct colours, 3-25 shallow crossings each | 300 | 0.827 | 0.780 | 0.714 | 0.111% | 17.2% |
| samecolour | two series in one colour (solid + dashed, or solid + thick), crossing, sometimes a third series | 240 | 0.900 | 0.812 | 0.743 | 0.379% | 6.6% |
| shallowx | 2-3 near-horizontal series that cross at angles under about 15 degrees in pixels (ylim padded 1.5x so pixel per data unit is small); only hop, no near-parallel confusion | 230 | 0.758 | 0.654 | 0.654 | 0.020% | 0.087% |
| legocclude | 2-4 series whose body passes behind a 2-3 column legend box with a frame; the legend occludes 100-200 pixel columns across the series | 303 | 0.818 | 0.718 | 0.694 | 0.098% | 0.716% |

Stage attribution (diag.py on 40 charts, frozen tree):
- shallowx: heat 1.000 -> cluster 0.998 -> chain 1.000 -> merged 1.000 -> final 0.902 (loss is in drop_duplicates on ghost traces at crossings)
- legocclude: heat 0.998 -> cluster 0.983 -> chain 0.889 -> merged 0.888 -> final 0.834 (loss starts at chain, which breaks across the legend box; merge_fragments does not bridge the gap)

Finding: shallowx chains perfectly (1.000). The hop at shallow angles was expected to be the dominant failure here but is not; the loss is at drop_duplicates, where the ghost traces beside the real line at crossings sometimes shadow the real one. legocclude confirms the chain-gap bridging rule needs to span >50 column gaps for a wide occlusion.

`samecolour`: the 202 members of a same-colour pair lose 11% and 24 of them come back with RMS above 5% (a hop onto the twin), 56% are partial; the 38 differently coloured third series in the same charts lose 5%, none hops (RMS over 5%: 0). Solid + dashed (11% lost) and solid + thick (10%) behave alike. The network does separate same-colour series most of the time (the overlay `viz-samecolour/12030000.png` shows a solid and a dash-dot of one colour kept apart through two crossings); the failure is at the crossings, as in `cross`, only more often.

`cross`: 52 of 300 lost (4% in 2-series charts, 17% in 3, 25% in 4; 6% with 3-9 crossings, 24% with 10+); of the 248 found, 66 have RMS above 5% (hopped onto another curve for a stretch), and 1.59 lines are returned per true series (38 charts return more than 1.5x). Line width does not matter here (16-18% lost at every width).

Not a tracing failure, for the record: a wrong plot frame clips the series outside it (`extract` masks the ridge to the frame's ROI), e.g. plotly 500021 where the frame's top edge cuts through the chart; but frame error does not drive the mpl-val losses (26% lost with frame error under 3 px, 19-21% with larger errors; only 9000049, 9000132 and 500021 are frame-related).

## 5. Catalogue

Composite overlays (`out/t2c/inspect-val/<seed>.png`) show six panels: the extraction over the chart with the truth in green, the line heat, the embedding (PCA to RGB), the clusters, the chains before merging, and the merged pieces with the dropped ones in red.

### C1. A series cut into long pieces that are never joined

- Examples: 9000080 s1 (two smooth lines, no crossing: 371 + 213 columns), 9000108 s2 (399 + 208), 9000041 s1 (206 + 258), 9000156 s0 (240 + 253), 9000175 s1 (416 + 322), 9000162 s0 (186 + 135 + 88), 9000145 s0 (383 + 126, a single dotted series).
- What the pixels show: the ridge is complete; the embedding drifts along the series with context (9000080's upper line goes green to blue to dark in the PCA panel) and the clustering (radius 1.5, 16 centres) cuts it where the drift crosses a cluster boundary, often at a turning point.
- Stage: `cluster_embeddings` splits; `peel_chains` runs per cluster so the chain ends there; `merge_fragments` refuses the junction (the pieces' mean embeddings differ by more than `emb_tol` = 3.0 because the clustering separated them, and/or the pieces overlap by more than 8 columns in the transition); `drop_duplicates` keeps both.
- Why it costs so much: a piece must cover more than ~60% of the series to match at all, so the series is "not found" and contributes 0 to good coverage, although 90% of it was traced correctly.
- Probe: any probe set shows it; cleanest in `t2-parallel` and `t2-steep` (few series, no crossings).

### C2. Hopping at a crossing

- Examples: `t2-cross` 12000000 s0 (RMS 21%), 12000071 s1 (32%), 12000087 s0 (31%); mpl-val 9000067 s1 (RMS 10%, two lines within 3 px on half the columns), 9000099 s3, 9000018 s0.
- What the pixels show: two series of one embedding cluster cross at a shallow angle; the heat ridge is a continuous X.
- Stage: `peel_chains` scores a chain by collected heat minus 0.5 per pixel of vertical gap; at a shallow crossing both continuations have the same gap, so the choice is arbitrary; the chain then runs on the other series until the next crossing. The embedding is not consulted inside a cluster, and direction is never consulted.
- Signature in the numbers: a found series with RMS of 5-30% (66 of 248 found series in `t2-cross`), plus extra lines (1.59 returned per true series).

### C3. Steep series break at any interruption

- Examples: 9000018 s2 (an oscillation of 60 px per column, pieces of 190 + 159 columns), 9000144 s1/s2, 9000132.
- Stage: the chain's gap cost and the merge rule (`gap <= 3 + 2 dx`) are vertical pixel distances; a steep series interrupted for 3 columns (a crossing taking those columns to another cluster) has its ends 100+ px apart vertically and is never re-joined, though extrapolating its slope would land within a pixel.

### C4. Dense or steep data represented one value per column

- Examples: 9000031 s0 (area, 470 points on 575 columns, good coverage 0.19 at RMS 5.7%), 9000068 s1/s2, 9000184 s0 (2004 points, RMS 13%), 9000079, 9000077, 9000129 s0; plotly 500011 s3, 500008 s1.
- Stage: `column_runs` takes the heat-mass centroid of a run longer than 5 px, which for a zigzag of 20-40 px per column is 10-20 px from the truth at the column centre; the metric compares at the column centre within 1% of the plot height. Found, but "good" on 10-50% of columns.
- Not a separation failure: the series is followed. It is the representation (and partly the metric's one-value-per-column view of a vertical run).

### C5. Spurious lines

- Examples: 9000031 (13 lines for 2 series), 9000144 (17 for 3), 9000109 (15 for 4), 9000032 (8 for 3).
- Where they come from: ghost chains along the far flank of a thick or jagged stroke, and the fragments of C1-C3 that `drop_duplicates` keeps because they are not inside a longer trace's envelope. They cost precision downstream (matching, the marker-row filter, and every extra CSV column a user has to delete).
