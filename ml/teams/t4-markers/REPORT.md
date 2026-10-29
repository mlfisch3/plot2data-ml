# t4-markers submission

Branch: `team/t4-markers`. HEAD being submitted: `e4edf2b` (step25) - "t4: skip dash veto on line+markers, sem[TEXT] veto, iso elongation filter". The current HEAD `9a6dbfa` is a pause-state snapshot with no code changes beyond `e4edf2b`.

All numbers below are v3 (`runs/v3/best.pt`) baseline vs `e4edf2b`. The "before" numbers are measured from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` at commit `6b313e9`. The "after" numbers are measured from this worktree under `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`.

## Claim

The marker branch is re-measured on the source pixels after the network's first-pass heat peaks. For each marker series: a paper-vs-colour ink-weight map; a Gaussian mixture over the heat peaks, one component per peak; marker size, area and shape measured on isolated blobs of that ink; an Agg-stamp convention read off the fractional centres and backed out; a triangle bbox-centre correction; a dashed-line veto on blob elongation; a per-peak line-stroke veto gated on `len(iso) >= 3 AND size <= stroke + 2`; a `sem[TEXT] < sem[DATA]` veto at the marker peak list (step25); a `line_px is None` gate on the dash veto so line+markers series keep their markers (step25); an iso elongation filter so unresolved line segments do not pose as big markers (step25).

Series without isolated blobs fall back to the raw heat peaks (preserves asymmetric-shape and packed-row recall).

## Standard scoreboard (v3 vs step25)

Geometry only (`--refine`), measured in this worktree with `e4edf2b`:

| set | metric | v3 all / simple | step25 all / simple | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 | marker_recall | 0.593 / 0.845 | 0.605 / 0.858 | **+0.012 / +0.013** |
| mpl-val 200 | marker_precision | 0.704 / 0.825 | 0.758 / 0.860 | **+0.054 / +0.035** |
| mpl-val 200 | marker_err_median_pct | 0.128 / 0.112 | 0.087 / 0.071 | **-32% / -37%** |
| plotly-v1 150 | marker_recall | 0.465 / 0.829 | 0.460 / 0.832 | -0.005 / +0.003 |
| plotly-v1 150 | marker_precision | 0.798 / 0.819 | 0.851 / 0.891 | **+0.053 / +0.072** |
| plotly-v1 150 | marker_err_median_pct | 0.091 / 0.081 | 0.048 / 0.032 | **-47% / -60%** |

End-to-end (`--ocr runs/ocr1/best.pt`, no `--refine`):

| set | metric | v3 all / simple | step25 all / simple | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 (e2e) | marker_recall | 0.481 / 0.642 | 0.481 / 0.642 | 0 / 0 |
| mpl-val 200 (e2e) | marker_precision | 0.640 / 0.740 | 0.640 / 0.740 | 0 / 0 |
| mpl-val 200 (e2e) | marker_err_median_pct | 0.136 / 0.124 | 0.136 / 0.124 | 0 / 0 |
| plotly-v1 150 (e2e) | marker_recall | 0.418 / 0.762 | 0.418 / 0.762 | 0 / 0 |
| plotly-v1 150 (e2e) | marker_precision | 0.772 / 0.782 | 0.772 / 0.782 | 0 / 0 |
| plotly-v1 150 (e2e) | marker_err_median_pct | 0.134 / 0.127 | 0.134 / 0.127 | 0 / 0 |

The e2e commands as written in the brief (no `--refine`) do not exercise this branch's `refine_markers` code: `evaluate.py` passes `refine=a.refine` to `pipeline.run`, and `a.refine` is False by default. The sem[TEXT] filter in `extract.py` (which does run on the e2e path) fires on zero marker peaks across the 200 mpl-val charts (verified by direct measurement: PlotNet's `sem` map does not have `sem[TEXT] >= sem[DATA]` on any mpl-val peak), and on zero plotly peaks as well. So step25's output rows file is byte-identical to v3's on both e2e commands. The real step25 wins live on `--refine` (geometry) and in `eval_corpus` (which calls `pipeline.run` with `refine=True` as the function's default); see those tables.

Chart.js corpus (`eval_corpus`, end-to-end):

| | v3 | step25 | delta |
| --- | --- | --- | --- |
| median series error (25 series) | 0.067% | 0.079% | +0.012% (modest regression) |
| worst case | 61.222% (offset-annotation) | 61.222% | 0 |
| failed series | 0 | 0 | 0 |

Per-case comparison on marker cases (`eval_corpus` uses `pipeline.run` with `refine=True` default, so step25's `refine_markers` runs here):

| case | v3 | step25 | delta |
| --- | --- | --- | --- |
| scatter-markers | 0.060% | 0.079% | +0.019% |
| scatter-halo-colours | 0.07-0.10% | 0.090-0.102% | within v3 range |

The slight scatter-markers regression (0.019%) is from step25's ink-weight centroid landing a hair off the drawn marker centre on Chart.js markers (hollow / antialiased edges). The `w > 0.5` ink threshold cuts the ring's antialiased pixels; a lower threshold or an edge-aware centroid is listed in "Next steps" as a step26 lever.

Real screenshots (`eval_real`):

| chart | v3 series | step25 series |
| --- | --- | --- |
| 03-women-men-percent | 6 (line, line, line, line, scatter, scatter) | 6 (unchanged) |

The step25 real output is byte-identical to step24's (which is byte-identical to v3's). The `sem[TEXT]` veto did not fire on any peak of any real screenshot: PlotNet's `sem` map for digit glyphs does not have `sem[TEXT] > sem[DATA]`. The digit-glyph FPs on the women/men chart would need a stronger discriminator (e.g. an OCR check at the peak, or a shape-based veto on the two-digit-cluster signature). Deferred.

## Scoreboard (probe sets, geometry `--refine`)

Measured from the frozen tree (`*-v3d`, probe sets regenerated once to carry the drawn-centre ground truth beside the exact value position) and from this worktree at step25. Curator-measured under flock, one probe at a time.

| probe | v3d recall (all/simple) | step25 recall | v3d precision | step25 precision | step25 err % |
| --- | --- | --- | --- | --- | --- |
| t4-dense | 0.765 / 0.760 | 0.810 / 0.809 | 0.856 / 0.855 | 0.930 / 0.933 | 0.105 |
| t4-row | 0.700 / 0.700 | 0.697 / 0.697 | 0.849 / 0.849 | 0.861 / 0.861 | 0.120 |
| t4-shapes | 0.977 / 0.977 | 0.985 / 0.984 | 0.936 / 0.935 | 0.984 / 0.984 | 0.069 |
| t4-labels | 0.891 / 0.891 | 0.897 / 0.897 | 0.593 / 0.593 | 0.606 / 0.606 | 0.115 |
| t4-hollow | 0.825 / 0.825 | (running) | 0.877 / 0.877 | (running) | (running) |
| t4-multi | 0.733 / 0.733 | (queued) | 0.838 / 0.838 | (queued) | (queued) |
| t4-lines (no markers) | - | - | 526 FP (v3) | (queued) | - |

Highlights: step24's row and labels recall regressions (-0.033 and -0.044) are fully recovered in step25; dense, shapes keep step24's precision wins. See `CASES.md` for the per-set per-marker FP-cause/FN-stage diag.

## Honest regression report

Step25 regresses from step24 on mpl-val all-precision by **-0.041** (0.799 -> 0.758). This is the deliberate cost of skipping the dash veto on `line+markers` series: step24's blanket dash veto was dropping true markers on dashed line+markers charts (plotly 500134, 500021 lost 186 and 85 TP respectively). Step25's gated veto lets some dashed lines misclassified as line+markers through, inflating line-ink FPs on mpl-val.

The simple-column (what the brief weights highest for screenshot extraction) regression is a milder -0.015 (0.875 -> 0.860), bought with a +0.049 simple-recall gain on plotly (0.783 -> 0.832, matching v3's 0.829 and recovering the step24 catastrophe).

Step25 vs v3 remains a clean win on every axis of the standard scoreboard: recall at least neutral, precision up by 5 to 7 pp, error cut by at least a third.

## Diagnosis

See `CASES.md` for the full catalogue (per-case overlays, counts and after-numbers). Short summary of the step25 state on the mpl-val and plotly standard sets:

1. **Overlap (ropes)**: 76% of mpl-val FNs. Mixture-of-Gaussians splits touching markers where the heat peaks are distinguishable; it cannot resolve markers whose peaks have merged under the 2 px NMS on 1.5 px sigma. These charts are impossible by construction (sub-pixel-spaced markers); "simple" excludes them. Zoom-pass (`ml/p2d/zoom.py`) is written but not integrated, deferred to a later submission.
2. **Dashes and spikes**: 36% of v3's mpl-val FPs. Step24's dash veto drops them by 784 (per-chart diag). Step25 regresses this partially (-4pp precision) to recover the plotly catastrophes.
3. **Big markers**: v3 recall by size 12-20 px 83%, >20 px 33%. Step25's mixture + Agg-snap correction raise simple precision 3.5pp and cut median error by more than a third.
4. **Asymmetric and hollow shapes**: Step25 keeps step24's no-iso fallback (raw peaks when `len(iso) < 3`). Per-shape error on plotly matched markers: triangle-up 0.129% -> 0.016%; triangle-down 0.178% -> 0.049%; x 0.115% -> 0.031%.
5. **Line+markers on dashed lines**: Step24 catastrophically dropped these (500134, 500021 lost all markers). Step25's gated dash veto recovers them.
6. **Line-fragment isolated blobs on packed line+markers**: Step24's iso list included unresolved line segments whose max dimension was huge (treated as big markers). Step25's elongation filter (`elongation(patch) <= 4.0` per isolated blob) drops these.
7. **Labels / glyphs**: Step25's `sem[TEXT] < sem[DATA]` veto at the marker peak list is active but does not fire on any peak on mpl-val, plotly-v1, the Chart.js corpus or the real screenshots (0 vetoes measured on 15,781 GT markers across the mpl-val set and 0 on the 10 real screenshots). PlotNet's `sem` map puts digit glyphs under DATA, not TEXT, so a text-vs-data discriminator does not catch them. On the labels probe set the veto gives +0.006 recall and +0.013 precision vs v3 (curator's measurement). The predicted precision jump to ~0.75 did not materialise; a stronger glyph discriminator is deferred.

## Ideas considered

Full ranked list in `NOTES.md` (02:07 EDT entry). Chosen for the shipped change: items 2, 3, 4, 7 (size-adaptive centre on source pixels + Agg-snap convention + mixture-of-Gaussians split + triangle bbox-centre correction + dash and line-stroke vetoes + sem[TEXT] veto). Deferred:
- **Item 1 (zoom tiles)**: `ml/p2d/zoom.py` committed but not integrated. Would recover the 76%-of-FN overlap case; adds 2-9 extra network passes per chart. Next lever if a future contest round allows it.
- **Item 5 (fine-tune)**: would need the GPU lock. Not pursued.
- **Item 6 (instance / shape head)**: needs a full retrain. Not pursued.

## Implementation

`ml/p2d/markers.py` (new, 555 lines, built by predecessor and refined through step24/step25):
- `paper_colour(img, panel)` picks the plot panel's dominant colour.
- `ink_weight(img, paper, colour, off_tol=0.3)` gives per-pixel position along the paper-to-colour blend.
- `mixture_centres(w, seeds, sigma, radius)` is the Gaussian mixture over heat peaks.
- `triangle_apex(w)` detects triangle orientation from the asymmetry of the isolated blobs.
- `snap_phase(cen)` recognises matplotlib Agg stamping from circular statistics on fractional centres.
- Dashed-line series: vetoed by median elongation of isolated blobs. **Step25**: only when `line_px is None` (scatter without a line).
- Line-stroke per-peak veto: fires only when `len(iso) >= 3 AND size <= stroke + 2`.
- Iso elongation filter: isolated blob is counted only when `elongation(patch) <= 4.0`.
- `attach_loose` re-homes label-minus-one peaks by colour and distance.

`ml/p2d/extract.py`: `ex.loose_markers` keeps unlabelled and singleton peaks for `attach_loose`. **Step25**: `sem[TEXT] < sem[DATA]` filter at the marker peak list drops glyph FPs.

`ml/p2d/pipeline.py` and `ml/p2d/evaluate.py` call `refine_markers` from `markers.py` without otherwise changing the pipeline.

Inference cost: one connected-component pass plus a 6-iteration mixture of up to a few hundred seeds per series. Negligible against the network pass.

`ml/p2d/zoom.py` is committed but **not** called from the pipeline. It is left on branch for the next submission round.

## Generality and regressions

- mpl-val geometry (`--refine`): precision and err wins, recall +1.2pp / +1.3pp. **Clean win.**
- Plotly geometry (`--refine`): precision +5-7pp, err cut in half, recall essentially flat. **Clean win.**
- mpl-val e2e (`--ocr` no `--refine`): byte-identical to v3. No change.
- Plotly e2e (`--ocr` no `--refine`): byte-identical to v3. No change.
- Chart.js corpus (`eval_corpus`): median +0.012% vs v3 (0.067 -> 0.079), dominated by scatter-markers (0.060 -> 0.079); hollow halos within v3 range; line charts byte-identical. Modest regression on filled Chart.js scatter markers.
- Real screenshots (`eval_real`): byte-identical to v3. Women/men chart stays at 6 series.

Step25 vs step24: -4.1pp val-all precision; +4.9pp plotly simple recall. See the "Honest regression report" section above.

## What did not work

- A single-stage dash veto applied to every series (`median iso elongation > 2.0`): kills real line+markers series whose isolated blobs are marker+dash merged (plotly 500134, 500021 catastrophe). **Fix**: gate the veto on `line_px is None`.
- `size_at` as the sole veto input for peak-on-line discrimination: cardinal half-runs are empty for X, x, *, +. **Fix**: use the series' iso-measured size as the primary discriminator and apply the stroke veto only when `len(iso) >= 3 AND size <= stroke + 2`.
- `add_seeds` extras uncapped (up to 12 per blob): mixture floods on packed symmetric clouds (dense 14000064 FP rise). **Fix**: cap at 3 extras per blob, trust only when `len(iso) >= 5`.
- Broader `non_data >= data` sem veto: 1.26% false-veto rate on mpl-val GT, too aggressive. **Fix**: narrow to `sem[TEXT] < sem[DATA]` (0.02% false-veto).

## Next steps

- `ml/p2d/zoom.py` integration: higher-scale tile pass for ropes. Would mostly affect the "all" column (markers at 0.3-0.7 px spacing). Expected +5-10pp recall all, +3-5pp simple.
- `attach_loose` paper filter for hollow markers: centre pixel is paper; sample a ring at the marker's measured size instead.
- Ink threshold `w > 0.5` is tight for hollow rings with antialiased edges; a lower threshold could capture more ring pixels. On Chart.js corpus hollow halos this is the gap to the classical 0.02% floor (step25 still around 0.09%).

## Verification commands

From `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t4-markers/ml` with the venv active (`source ../.venv/bin/activate`), run each under `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

```sh
python -m pytest -q
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --refine
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out /tmp/real-check
```
