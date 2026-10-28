# Predecessor transcript salvage (a33a9de7fe0759d04, Fable 5.1)

Spawned about 01:30 EDT Wed 28 Oct 2026; cut off at the account's usage limit about 02:30 EDT.
Transcript: /tmp/claude-1000/.../tasks/a33a9de7fe0759d04.output (740 lines).

## Chronology from the assistant's own messages

- Read brief/assignment/mailbox, then the calibration code; kicked off a 60-chart baseline.
- Extended `p2d.eval_calib` with `--json` to dump every axis of every chart in detail.
- Launched detailed per-axis dumps over mpl-val (200) and plotly-v1 (150); nine agents sharing the GPU slowed everything to a crawl.
- Built the pieces the joint-decode idea needed independently: `ocr.beam_decode` (CTC prefix beam search) and `ocr.ctc_score` (forward alg).
- Wrote the whole axis decoder in `ml/p2d/axis.py` with top-k candidates, expected-text, two-label linear/log tiebreak, nice-step and arithmetic-progression bonuses, and a dedicated test file `ml/tests/test_axis.py` (10 unit tests).
- Wired `decode_axis` through `p2d/pipeline.py`; added `refine_labels` to re-measure every tick's label box on the source pixels using an ink/band walker (`extract.label_from_source`); added `apply_factor` for multipliers/offsets.
- Added `teams/t1-axis/offline.py`: cache the net's extraction once (CPU-only inference afterwards), then iterate the reader + decoder on CPU, with four ablations (plain/joint x net/src boxes).
- First four CPU ablations (02:06-02:09, mpl-val 200, before the colour-aware box finder):
  - plain-net:  x within 84.5% / scale 91%,  y within 76.5% / scale 89%,  both 67.5%
  - joint-net:  x within 85.5% / scale 80%,  y within 83.5% / scale 94.5%, both 75.5%
  - plain-src:  x within 87.0% / scale 94%,  y within 75.5% / scale 88.5%, both 68.5%
  - joint-src:  x within 87.5% / scale 82.5%,y within 82.0% / scale 95%,   both 75.0%
  Key finding: joint moves both-axes-within-0.5% by +8 points but regresses x-scale by 11 points (24 charts flipped linear->log; mostly year-labelled axes like 9000042 '1,910'...'1,950' and 9000130 '2.78'...'2.88').
- Rewrote `label_from_source` with colour-aware ink extraction and a cleaner `_label_band` after reading the curator's test_boxes report (seven mechanical bugs listed, 02:16). Box-finder recall jumped on mpl-val from 0.882 to 0.921 (0.888 to 0.945 on y). But: 30 new "elsewhere" cases, mostly '10^k' axes where the superscript "1" is taken as its own label.
- Spotted and fixed a `parse_value` OverflowError on beam candidates like `1e400`.
- Last message: "Let me clean up the longest-run expression I left convoluted in `_row_shapes`, then run the tests and the curator's box test on both sets." The usage limit hit before this landed.

## State at handover

- Nothing committed since the curator's 02:21 commit `284902a`.
- The modified files were working: pytest results unknown (not reported in the transcript); chart 9000042 now fits as linear with the current tree (verified by the replacement) - the colour-aware boxes fix the x-scale regression on year axes.
- 02:09 ablation JSONs under out/t1/abl-*.json are stale (pre-colour-aware). A fresh ablation on the current tree is the first measurement after a commit of the salvaged state.

## What the replacement will do first

1. Commit the predecessor's uncommitted state as `wip(t1): salvage brainstormer snapshot (predecessor a33a9de7)`.
2. Run pytest; fix anything that fails without changing the design.
3. Re-run the four CPU ablations on the current tree with offline.py; locate residual regressions.
4. Only then: investigate the superscript "elsewhere" cases, finish any decoder polishing, measure the full scoreboard.

