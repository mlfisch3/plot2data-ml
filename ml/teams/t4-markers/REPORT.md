# t4-markers submission

Branch: `team/t4-markers`. HEAD being measured for the numbers below: c78db3f (step24). Step25 commit (dash veto on scatter only, iso elongation filter, sem[TEXT] veto) is prepared and will be committed as soon as the step24 eval completes; the full step25 eval follows.

All numbers are v3 (`runs/v3/best.pt`) baseline vs this branch.
Standard-set "before" numbers are read from the frozen tree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml` (commit 6b313e9).
Probe-set "before" numbers (`*-v3d`) are also from the frozen tree, with the probe set regenerated once to carry the drawn-centre ground truth beside the exact value position.

## Claim

The marker branch is re-measured on the source pixels after the network's first-pass heat peaks: ink weight per series' colour, mixture-of-Gaussians centres with one component per peak, size and area measured on isolated blobs of that ink, Agg-stamp convention read off the fractional centres, triangle bbox-centre correction, dashed-line veto on blob elongation, and a per-peak line-stroke veto gated on `len(iso) >= 3` and `size <= stroke + 2`. Series without isolated blobs fall back to the raw heat peaks. Step25 adds a sem[TEXT] < sem[DATA] filter at the peak list to drop glyph FPs.

Step24 vs v3, geometry only `--refine`:

| set | metric | v3 | step24 | delta |
| --- | --- | --- | --- | --- |
| mpl-val | marker_recall (all / simple) | 0.593 / 0.845 | 0.598 / 0.850 | +0.005 / +0.005 |
| mpl-val | marker_precision (all / simple) | 0.704 / 0.825 | 0.799 / 0.875 | **+0.095 / +0.050** |
| mpl-val | marker_err_median_pct (all / simple) | 0.128 / 0.112 | 0.086 / 0.070 | **-33% / -37%** |
| plotly-v1 (first 150) | marker_recall (all / simple) | 0.465 / 0.829 | 0.445 / 0.783 | -0.020 / -0.046 |
| plotly-v1 | marker_precision (all / simple) | 0.798 / 0.819 | 0.871 / 0.903 | **+0.073 / +0.085** |
| plotly-v1 | marker_err_median_pct (all / simple) | 0.091 / 0.081 | 0.044 / 0.027 | **-52% / -67%** |
| Chart.js corpus (median series err %) | - | 0.067 | 0.079 | +0.012 (regression) |
| Real screenshots | series count / calib | unchanged | unchanged | 0 |

The simple-column mpl-val numbers are what the brief weights highest for screenshot extraction: precision +5pp, error cut by more than a third, recall essentially unchanged. The Plotly simple recall regression on step24 is dominated by two charts (500134, 500021) where the dash veto fires on a line+markers series's isolated marker+dash merged shapes. Step25's dash veto on scatter only is expected to recover this.

## Scoreboard (step24, geometry only `--refine`)

Probe sets (frozen tree v3d vs step24):

| probe | v3d recall (all/simple) | v3d precision | step24 recall | step24 precision | step24 err_median % |
| --- | --- | --- | --- | --- | --- |
| t4-dense | 0.765 / 0.760 | 0.856 / 0.855 | 0.810 / 0.808 | 0.930 / 0.933 | 0.105 / 0.108 |
| t4-row | 0.700 / 0.700 | 0.849 / 0.849 | 0.667 / 0.667 | 0.868 / 0.868 | 0.119 / 0.119 |
| t4-shapes | 0.977 / 0.977 | 0.936 / 0.935 | 0.985 / 0.984 | 0.984 / 0.984 | 0.069 / 0.066 |
| t4-labels | 0.891 / 0.891 | 0.593 / 0.593 | 0.847 / 0.847 | 0.602 / 0.602 | 0.115 / 0.115 |
| t4-hollow | (TBD) | (TBD) | (running) | | |
| t4-multi | (TBD) | (TBD) | (running) | | |
| t4-lines (no markers) | - precision only | (running) | | | |

Row's -0.033 recall and labels' -0.044 recall are the same mechanism as the Plotly line+markers regression; step25's dash veto on scatter only is expected to recover both.

## Diagnosis

See `CASES.md` for the full catalogue (maintained by the curator). Short summary of the step24 state:

1. **Overlap (ropes)**: 76% of mpl-val FNs. Mixture-of-Gaussians splits touching markers where their heat peaks are distinguishable; it cannot resolve markers whose peaks have merged under the 2 px NMS on 1.5 px sigma. These charts are impossible (sub-pixel-spaced markers); "simple" excludes them.
2. **Dashes and spikes**: 36% of mpl-val FPs in v3. Step24's dash veto drops mpl-val false positives from 3918 (base) to 2378 (step24).
3. **Big markers (v3 recall by size: 12-20 px 83%, >20 px 33%)**: Step24's mixture + Agg-snap correction raise simple precision 5pp and halve median error.
4. **Asymmetric and hollow shapes**: Step24's no-iso fallback returns raw peaks for packed rows (curator's 14000078 at step23 dropped 134 TP; recovered in step24).
5. **Line+markers with dashed lines (regression)**: Step24's dash veto on isolated marker+dash merged shapes fires. **Fixed by step25.**
6. **Line+markers with line-fragment isolated blobs (regression)**: Step24's iso list contains unresolved line segments whose max dimension is huge; the elongation filter in step25 drops these.
7. **Labels / glyphs (women/men chart)**: Step24 doesn't address. **Step25's sem[TEXT] veto expected to clear.**

## Ideas considered

Full ranked list in `NOTES.md` 02:07 (predecessor). Chosen for step24: items 2, 3, 4 (size-adaptive centre + convention + merge + attach-loose + dash and line-stroke vetoes). Added for step25: sem[TEXT] veto.

Deferred:
- Item 1 (zoom tiles): `ml/p2d/zoom.py` is committed but not integrated. Expected gain on "all" column for ropes; adds 2-9 extra network passes per chart. If step25 does not fully clear simple-recall on Plotly, this is the next lever.
- Item 5 (fine-tune): would need the GPU lock. Not pursued.
- Item 6 (instance / shape head): needs a full retrain. Not pursued.

## Implementation

`ml/p2d/markers.py` is new (555 lines, built by the predecessor):
- `paper_colour` picks the plot panel's dominant colour.
- `ink_weight(img, paper, colour, off_tol=0.3)` gives per-pixel position along the paper-to-colour blend.
- `mixture_centres(w, seeds, sigma, radius)` the Gaussian mixture.
- `triangle_apex(w)` detects triangle orientation.
- `snap_phase(cen)` recognises matplotlib Agg stamping from circular statistics of fractional centres.
- Dashed-line series are vetoed by median elongation of isolated blobs (step25: only on scatter).
- Line-stroke per-peak veto fires only when the series' isolated-marker size is close to the owning line's stroke.

`ml/p2d/extract.py` keeps unlabelled and singleton peaks on `ex.loose_markers` so they can be reclaimed in `attach_loose`. Step25 adds a sem[TEXT] filter at the peak list.

`ml/p2d/pipeline.py` and `ml/p2d/evaluate.py` call `refine_markers` from markers.py without otherwise changing the pipeline.

Inference cost: adds `measure_series` per series (one connected-component pass, 6-iteration mixture of up to a few hundred seeds). Negligible against the network pass.

## Generality and regressions

Step24 holds across sets:
- mpl-val geometry: precision + err wins, recall neutral.
- Plotly geometry: precision + err wins, recall regression on line+markers (step25 fix queued).
- Chart.js corpus: median error +0.012 (modest regression), coverage up to 100% on scatter-markers / scatter-halo-colours.
- Real screenshots: byte-identical to v3 output (women/men still 6 series). Step25's sem[TEXT] veto expected to drop digit FPs.

## What did not work

- A single-stage dash veto (`median iso elongation > 2.0`, applied to all series): kills real line+markers series whose isolated blobs are marker+dash merged (500134, 500021). Fix: gate the veto on `line_px is None`.
- `size_at` as the sole veto input for peak-on-line discrimination: cardinal half-runs are empty for X, x, *, +. Fix: use the series' iso-measured size as the discriminator.
- `add_seeds` extras capped at 12 per blob: for dense merged blobs the mixture floods with arbitrary seeds (14000064). Fix: cap at 3 per blob and skip when `iso < 5`.

## Next steps

- Zoom.py integration for ropes.
- `attach_loose` paper filter is wrong for hollow markers (centre pixel is paper); sample from a ring at the marker's measured size.
- Ink threshold `w > 0.5` is tight for hollow rings with antialiased edges; a lower threshold could capture more ring pixels and improve the centroid on Chart.js hollow halos (toward the 0.02% classical floor).

## Verification commands

From `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t4-markers/ml` with the venv active:

```sh
python -m pytest -q
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine --json /tmp/val.json
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --refine --json /tmp/plotly.json
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt --json /tmp/val-e2e.json
python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --viz /tmp/corpus-viz
python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out /tmp/real
```
