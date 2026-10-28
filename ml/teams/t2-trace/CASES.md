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

## 4. Probe sets

All at seeds 12,000,000 and above, 100 charts each, built with `python -m p2d.synth.probe_t2 --case <name> --count 100 --out data/t2-<name>`.
Baseline: `python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/t2-<name> --refine`.

| case | what it provokes | series | found | cov | good cov | rms median | rms p90 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cross | 2-4 smooth sines of distinct colours, 3-25 shallow crossings each | 300 | 0.827 | 0.780 | 0.714 | 0.111% | 17.2% |

`cross`: 52 of 300 lost (4% in 2-series charts, 17% in 3, 25% in 4; 6% with 3-9 crossings, 24% with 10+); of the 248 found, 66 have RMS above 5% (hopped onto another curve for a stretch), and 1.59 lines are returned per true series (38 charts return more than 1.5x). Line width does not matter here (16-18% lost at every width).

Not a tracing failure, for the record: a wrong plot frame clips the series outside it (`extract` masks the ridge to the frame's ROI), e.g. plotly 500021 where the frame's top edge cuts through the chart; but frame error does not drive the mpl-val losses (26% lost with frame error under 3 px, 19-21% with larger errors; only 9000049, 9000132 and 500021 are frame-related).

## 5. Catalogue

(one entry per failure kind: examples, overlays, diagnosis, probe, numbers; filled in as the evidence lands)
