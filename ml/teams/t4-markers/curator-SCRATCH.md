# t4-markers curator - scratchpad

Chronological, every finding and gotcha. Captured at pause 17:30 EDT, Wed 28 Oct 2026.

## Takeover (16:08-16:15 EDT)

- Predecessor was Fable 5.1 agent `a1abc77f3414bcec7` cut off at ~02:30 EDT; brainstormer predecessor was similar.
- Partner replacement is Opus 4.7 at `a1d4346bed4bd4f04`.
- Honored predecessor's GT convention: `markers_px` = exact value position, `markers_drawn_px` = drawn centre beside it. Verified in `ml/p2d/synth/probe_t4.py` lines 491-511 and in `ml/teams/t4-markers/tools/marker_diag.py` lines 135-146.
- Found an untracked `ml/p2d/zoom.py` (brainstormer predecessor's step-1 WIP tiled higher-scale pass) - left alone.
- Found an untracked `ml/tests/test_probe_t4.py` (predecessor's probe generator tests) - committed as mine (72247be).

## Standard baseline (16:08 context read)

- Standard sets (frozen tree v3): mpl-val recall 0.593/0.845, precision 0.704/0.825, err 0.128/0.112. plotly-v1 recall 0.465/0.829, precision 0.798/0.819, err 0.091/0.081.
- Probe sets: already measured by predecessor, outputs under `ml/out/t4/eval-<k>-v3d.txt` and `diag-<k>-v3/`.
- Corpus v3 (classical baseline): series median 0.067%, scatter-halo-colours 0.079-0.100% (vs classical 0.02%).

## Step23 diag (= af04090)

Dense/shapes/row were measured BEFORE the brainstormer's 16:21:17 edit to markers.py. Labels/hollow/multi/lines/val/plotly were measured AFTER - so those are actually step24 behaviour tagged step23 for file names.

Key finding (dense): recall 0.765 → 0.812 (+0.046), precision 0.856 → 0.925 (+0.069), err 0.168 → 0.105 (-0.063). Dense is a clear win.

Key finding (shapes): recall 0.977 → 0.985 (+0.008), precision 0.936 → 0.984 (+0.048), err 0.118 → 0.069 (-0.049). Shapes win.

Key finding (row): recall 0.700 → 0.667 (-0.032), precision 0.849 → 0.868 (+0.019). **Regression** on recall. `dropped` FN stage up +1062. Diagnosis pointed to line-stroke veto false-firing on line+markers at tight sizes.

## F10 and F11 (new failure kinds I added to CASES)

**F10**: Asymmetric shapes under centroid-based refinement, no isolated examples to measure convention. Example: seed 14000078 (one series of 200 "^" triangles 17.5 px, nn_rel 0.93). v3 TP 168, af04090 TP 34 (dropped 134 TP). The triangle correction (centroid offset to bbox centre) didn't fire because no isolated triangles. Fix: step24's no_iso fallback returns raw peaks.

**F11**: `add_seeds` overshoots in merged blobs. Example: seed 14000064 (3 series o/v/o, 15.8 px, nn_rel 0.42). v3 TP 221 pred 514, af04090 TP 182 pred 623 (lost 39 TP, +148 FP). Fix: step24 cap of 3 extras per blob, require iso >= 5.

## `size_at` false veto verification

Direct smoke test on synthetic shape masks: `_half_runs` returns zeros for X and * at any size (both are diagonal strokes with no cardinal arms). `size_at` returns 1-3 regardless of actual size. Reported to brainstormer; they gated the line-stroke veto with `len(iso) >= 3 AND size <= stroke + 2` (step24 fix). Snippet: `/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/sizeat_test.py`.

## sem[TEXT] veto verification

Tool: `teams/t4-markers/tools/verify_text_veto.py` on labels GT sem maps.
- `text >= data` false-veto rate: 0.09% on t4-labels, 0.02% on mpl-val. **Safe to use** (well below brainstormer's 3% threshold).
- `non_data >= data` (broader): 0.10% on labels, 1.26% on mpl-val. Still OK but risk on cramped-layout real charts.
- Recommendation: use `text >= data` only. Brainstormer followed this in step25.

## Step24 (c78db3f)

Standard sets vs v3:
- mpl-val --refine: recall +0.005/+0.005, precision +0.095/+0.050, err -33%/-37% (dense win)
- plotly --refine: recall -0.020/-0.046, precision +0.073/+0.085, err -52%/-67% (precision/err win, recall regression on simple)
- Chart.js corpus: median err +0.012 (small regression). scatter-markers coverage 96% → 100%, scatter-halo-colours all four at 100% coverage (vs 95% for some in v3).
- Real: byte-identical to v3.

Probe sets vs v3 (brainstormer's eval-<k>-step24.txt for dense/row/shapes/labels/hollow; multi/lines/e2e abandoned due to GPU thrash):
- dense: recall +0.045, precision +0.074, err -37%
- row: recall -0.033 (regression - fixed in step25), precision +0.019
- shapes: recall +0.008, precision +0.048, err -42%
- labels: recall -0.044, precision +0.008 (step25's sem-TEXT veto expected to fix)
- hollow: recall -0.003, precision +0.045

## Per-shape error improvements on Plotly (step24 vs v3, median %)

- triangle-down 0.178 → 0.049 (-0.129) **big win from triangle correction**
- triangle-up 0.129 → 0.016 (-0.113)
- x (thin strokes) 0.115 → 0.031 (-0.084)
- star 0.187 → 0.120 (-0.067)
- hexagon 0.049 → 0.022 (-0.026)
- hollow symbols (circle-open, diamond-open, square-open, triangle-up-open): unchanged (ring ink below mask threshold - a known-pending next-step)

## Per-chart Plotly catastrophes (step24 regressions)

- 500134 (triangle-up-open + diamond + hexagon on dashed line+markers): TP 186 → 0, pred 226 → 0 (!!). Dash veto fired on marker+dash merged isolated blobs. Fixed in step25 (dash veto on scatter only).
- 500021 (square line+markers on solid line): TP 85 → 1, pred 110 → 2. Isolated "blobs" were line fragments of 60+ px length. Fixed in step25 (iso elongation filter).
- 500099 (triangle-down line+markers on dashdot): TP 41 → 20. Same cause.
- 500003 (pentagon line+markers): TP 20 → 7. Same.
- 500107 (6081-marker rope, 5 line+markers): TP 931 → 708. Hard to fix (ropes).

## Returned-centre bias on isolated symmetric mpl-val markers

- v3: median (dx, dy) = (-0.00, -0.00), abs 0.00 (centred on drawn)
- step24: median (-0.50, -0.50), abs 0.71 (centred on EXACT VALUE POSITION, 0.5 px up-left of drawn)
- The snap back-out works: pred now aligns with `markers_px` (ground truth value), not `markers_drawn_px` (snapped position). This is correct behaviour.
- Plotly bias stays 0.04 px abs (no snap - nothing to correct, correctly left alone).

## Gotchas

- `pgrep -f "x"` without a `[x]`-style bracket matches own shell if the pattern appears anywhere. I accidentally killed a predecessor's shell this way (per my 02:08 EDT NOTES carried over) - use `[x]name` pattern.
- Python modules are loaded per process. When brainstormer edited markers.py mid-flight (16:21:17), my step23 diag's labels/hollow/multi/lines/val/plotly imports happened after the edit, picking up step24 behaviour. Dense/shapes/row started before the edit and got clean af04090. This mixed-tag issue is documented in CASES.
- A shell-redirect `>` truncates on open. If two processes write to the same filename concurrently, both will clobber each other. I almost did this with my step25-standard.sh duplicating brainstormer's val eval - brainstormer caught it, I killed mine.
- Long leading `sleep` chains are blocked by the Bash tool. Use Monitor with `until <check>; do sleep 2; done`.
- GPU is shared (16 GB on an RTX 3080). Training with --workers 6 holds the GPU lock plus most memory. Multiple eval processes compete and can cause silent slowdowns (val step25 at 15+ minutes vs usual 5-6).
- The brainstormer's step24.sh `while pgrep -f "[p]2d.evaluate"; do sleep 10; done` wait-loop blocks forever when other teams run evals. Serial-no-waits is better (step25.sh is serial).

## Monitors I had running at pause

- `br1kqr3up` (val done): watches step25.log for "val done".
- `bnuktydzz` (plotly step25 eval ready): watches eval-plotly-step25.txt for non-empty.
- `bt3g15hkg` (val or plotly done): wider filter for step25.log.
- Earlier expired: `b8wqo2abp`, `bh2m6oi41`, `bqj4jblq7`, `b398o6oxs`, `bwpvw8d4x`.

## Final-summary draft

`/tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/final-summary-draft.md` has the structure and all step24 numbers filled in. Needs step25 numbers plugged in before sending to main.
