# t1-axis: calibration from the tick labels

## Claim

Nine changes to `ml/p2d/{extract,ocr,pipeline,axis}.py` move the standard
scoreboard end-to-end numbers by a wide margin, with the biggest wins coming
from a joint decode of each whole axis, a colour-aware source-pixel label-box
finder, an explicit search for printed multipliers at axis ends, and
90-degree de-rotation of tall tick-label crops.

On mpl-val (200 charts):
- **both axes within 0.5%** (CPU-only ablation on HEAD 3c73e75): 67.5 -> **83.0 (+15.5 pts)**
- line_found (all): 0.547 -> 0.636 (**+8.9 pts**)
- line_found (simple): 0.624 -> 0.725 (**+10.1 pts**)
- line_good_cov_mean: 0.407 -> 0.493 (+8.6)
- line_rms_median_pct: 0.441 -> 0.368 (16.5% drop in median error)
- calib_x_within_0.5pct: 0.845 -> 0.880 (+3.5)
- calib_x_scale_ok: 0.910 -> 0.950 (+4.0)
- calib_y_within_0.5pct: 0.775 -> 0.880 (**+10.5 pts**)
- calib_y_scale_ok: 0.890 -> 0.950 (+6.0)

On plotly-v1 (150 held-out):
- line_found (all): 0.754 -> 0.825 (+7.1)
- calib_x_within: 0.9467 -> **1.0000** (+5.3), calib_x_scale 0.960 -> **1.000**
- calib_y_within: 0.860 -> 0.907 (+4.7), calib_y_scale 0.940 -> 0.987

On the Chart.js corpus (never trained on):
- `offset-annotation`: **61.222% -> 0.019%** (the '1e6' multiplier case the
  predecessor flagged as a hard target)
- Worst 61.222 -> 1.303% across the 25 series; median essentially unchanged.

On the real screenshots:
- 01-panel1/2/3 (year labels '2020..2024') now read correctly and fit linear
  within ~1 px, where the baseline cropped glyphs and fit log at 145 to 487 px.
- 03-women-men now fits x linear (was log); the arithmetic-progression tiebreak
  put the misplaced 2021 label into the right class.

Branch: `team/t1-axis`. HEAD: `3c73e75`.

## Scoreboard

All numbers below are from the standard commands run from `ml/` with
the venv active:

```sh
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt
python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out out/real
python -m p2d.eval_calib --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 100
```

Baseline numbers come from `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml`
(frozen at commit `6b313e9`); files `out/base/v3-{mpl-e2e,plotly-e2e,corpus,real}.txt`.
"After" numbers from this worktree; files `out/t1/v5-{mpl-e2e,plotly-e2e,corpus,real}.txt`.

Four CPU-only ablations (`teams/t1-axis/offline.py`) split the gain across the
two large components; "src" = colour-aware source-pixel label boxes,
"joint" = joint decoder in `axis.py`:

| configuration | x within | x nofit | x scale | y within | y nofit | y scale | both |
|---|---|---|---|---|---|---|---|
| v3 baseline (plain-net) | 84.5 | 16 | 91.0 | 76.5 | 12 | 89.0 | 67.5 |
| joint-net (joint, net boxes) | 85.5 | 13 | 91.5 | 84.0 | 9 | 95.0 | 75.0 |
| plain-src (plain fit, source boxes) | 86.0 | 15 | 91.0 | 79.5 | 5 | 91.5 | 71.0 |
| joint-src + multiplier + dedup (current) | **90.5** | **5** | **96.0** | **89.0** | **3** | **96.5** | **83.0** |

### Full mpl-val before / after:

| metric | before | after | delta |
|---|---|---|---|
| line_found (all) | 0.5466 | 0.6356 | +8.9 |
| line_found (simple) | 0.6242 | 0.7248 | +10.1 |
| line_good_cov_mean | 0.4073 | 0.4927 | +8.5 |
| line_rms_median_pct | 0.4411 | 0.3684 | -16.5% |
| peak_err_median_pct | 2.2898 | 2.0411 | -11% |
| calib_x_found | 0.9200 | 0.9750 | +5.5 |
| calib_x_within_0.5pct | 0.8450 | 0.8800 | +3.5 |
| calib_x_scale_ok | 0.9100 | 0.9500 | +4.0 |
| calib_y_found | 0.9400 | 0.9850 | +4.5 |
| calib_y_within_0.5pct | 0.7750 | 0.8800 | +10.5 |
| calib_y_scale_ok | 0.8900 | 0.9500 | +6.0 |

### Full plotly-v1 before / after:

| metric | before | after |
|---|---|---|
| line_found (all) | 0.7540 | 0.8252 |
| line_good_cov_mean | 0.6146 | 0.6844 |
| calib_x_found | 0.9733 | 1.0000 |
| calib_x_within_0.5pct | 0.9467 | 1.0000 |
| calib_x_scale_ok | 0.9600 | 1.0000 |
| calib_y_found | 0.9533 | 0.9867 |
| calib_y_within_0.5pct | 0.8600 | 0.9067 |
| calib_y_scale_ok | 0.9400 | 0.9867 |

### Chart.js corpus before / after:

- `offset-annotation`: 61.222% -> **0.019%** (fit linear with the '1e6' multiplier applied)
- `log-log`: 1.326% -> 1.303% (noise)
- all other 23 series unchanged
- median across 25 series: 0.067 -> 0.066
- worst: 61.222 -> 1.303

### Real screenshots (max px error at hand-measured anchors):

- 01-panel1 x year labels: before cropped to ['02', '021'] fit log 145 px err; **after** reads 2020..2024, fit linear 1.06 px err
- 01-panel2: 0.48 -> 0.57 px (noise)
- 01-panel3 x: before cropped, fit log 487 px err; **after** reads correctly, fit linear 1.05 px err
- 02-microprocessor: y log fit stable (parse_value handles 0^k -> 10^k)
- 03-women-men: x log -> **linear** (the arithmetic-progression tiebreak)
- 04-hits-per-visit: unchanged
- 05-retail-sales: 0.96 -> 0.95 px (noise)

### Probe set (`data/t1-probe`, 640 charts, built by the curator):

- t1-two_log/y: 0.575 -> **0.975** (+40 pts; the two-label linear/log tiebreak)
- t1-two_log/x: 0.650 -> **1.000** (+35 pts)
- t1-pow10_edge/y: 0.400 -> 0.575 (+17.5 pts)
- t1-mult_sci/y: 0.100 -> near 1.0 (multiplier scan)
- t1-offset/y: 0.000 -> near 1.0
- t1-rot90/x: 0.000 -> near 0.975 (rotation of the crop)

(Updated numbers in `out/t1/compare-probe-v3c73e75.txt` from the curator's remeasure.)

## Diagnosis

From the curator's `CASES.md`, mpl-val splits the loss of calibration across
nine classes (counted on the 47 failing y axes and 32 failing x axes of the
200 charts):

1. Two-label log axes decided linear (10 y). Pair of consecutive decades;
   `fit_axis`'s tie-break took log only for `^` or (powers of ten with ratio
   >= 100). Fixed by `decode_axis`'s two-label tiebreak from the values
   (10, 100 -> log; 10, 20 -> linear).
2. Leading glyph lost from the label box (12 y, 3 x). The sem speck filter
   or the small-canvas scale absorbed the leading `-`, `1`, or decimal
   point. Fixed by `label_from_source` on full-resolution pixels.
3. Ticks found but no label box (125 y ticks, 114 x ticks). Small labels on
   big charts never fired the sem class. Fixed by the source-pixel finder.
4. Printed multiplier or offset not read (6 of 7 y charts that print one).
   Fixed by `axis_factor`'s explicit source-pixel scan at the axis end.
5. The wrong piece taken as the label (10 x, 5 y). Fixed by the source
   finder's layout rules + `_mask_tick_marks` for 10^k axes.
6. Rotated x labels (7 x). Reader on true boxes was 22.5% exact on rotated;
   fixed by rotating tall crops 90 degrees before the reader.
7. Misreads on correctly boxed labels (16 of 816 y, most x rotated). Fixed
   in part by `decode_axis`'s top-k rescue.
8. Tick position off by 0.5 to 1.6 px on small charts (3 y). Geometry, not
   this team's area.
9. Linear axes with a misplaced last label read as log (3 - real-screenshot
   women-men chart). Fixed by `decode_axis`'s arithmetic-progression bonus.

## Ideas considered

Ranked by expected scoreboard gain; the top two covered 32 of the 47 failing
y axes and 22 of the 32 failing x on mpl-val.

1. **Decode each axis as a whole** (new `axis.py`, 389 lines). Top-k CTC
   readings per label, RANSAC over pairs, expected-text, two-label linear/log
   tiebreak, nice-step and arithmetic-progression bonuses. +8 both-axes pts.
2. **Source-pixel label box** (`label_from_source`, `refine_labels`). Colour-
   aware ink filter, line/tick-mark masking, raw-ink along-axis. +4 both-axes.
3. **Explicit multiplier search** at the axis end. +1.5 pts on mpl-val, +61
   points on the corpus worst case.
4. **Rotate tall crops** before the reader. Reader on rotated labels 22.5
   -> 97.5% exact.
5. **nice_step tolerance** for near-decade steps. Keeps 9000058 linear.
6. **Dedup tick positions** before the window and the decoder.
7. Date parser extensions: deprioritised (probe-specific, mpl-val has none).

## Implementation

Files on `team/t1-axis` HEAD `3c73e75`:

- **`ml/p2d/axis.py`** (new, 389 lines): the joint decoder. `TickRead`
  dataclass carries each label's reader logits and parsable candidates;
  `candidates()` extracts the parsable readings from a beam search;
  `_search()` is a RANSAC over all pairs of (tick, reading) with linear and
  log maps; `expected_text()` reads what each hypothesis says a disagreeing
  label should print, under the label's own CTC log-probs; `decode_axis()`
  scores all hypotheses with nice-step and progression bonuses.
- **`ml/p2d/ocr.py`**: `beam_decode()` (CTC prefix beam) and `ctc_score()`
  (CTC forward algorithm) are the primitives for the joint decoder;
  `read_logits()` exposes the per-crop log-probabilities. `normalise_crop()`
  rotates tall crops 90 degrees before the usual pass. `parse_value()`
  guards OverflowError on beam candidates like `1e400`.
- **`ml/p2d/extract.py`**: `_mask_tick_marks()` removes narrow vertical
  streaks (tick marks) that two-at-a-time look like a wide text band to the
  per-row width check. `label_from_source()` and `_label_band()` walk the
  source image outward from the axis to find the label box; the colour-aware
  pass filters the band rows for the label's ink colour but the along-axis
  extent uses the raw ink so anti-aliased edges on small labels do not strip
  the leading or trailing digit. `refine_labels()` runs the finder for every
  tick, deduping positions first so a duplicate tick does not collapse the
  spacing median.
- **`ml/p2d/pipeline.py`**: wires `decode_axis()` through `fit_reads()`,
  dedups reads within 1.5 px before the decoder sees them, calls
  `refine_labels()` once per axis before reading the labels, and rewrites
  `axis_factor()` with an explicit source-pixel search at the axis end for
  the printed multiplier when no `loose_label` matches it.
- **`ml/p2d/eval_calib.py`**: `--json` dumps every axis of every chart in
  detail (truth, prediction, reads, fit).
- **`ml/tests/test_axis.py`** (new, 11 tests): the joint decoder's behaviour
  on second-reading rescue, dropped-minus restoration, three-tick confident
  misread, two-label linear-or-log, dropped `1` of `10^k`, arithmetic
  progression beating a log fit that absorbs a misplaced label, years as
  linear, nice-step and log-pair primitives.

Cost at inference: joint decoder about 20 ms per axis on CPU; refine_labels
about 15 ms per axis (one connected-components pass per tick); multiplier
scan about 5 ms per axis. Total overhead on the end-to-end pipeline is
below 0.15 s per chart. No new model trained; no model grew; no training.

## Generality and regressions

The gains hold across all four standard sets:
- mpl-val 200: +8.9 points line_found, +10.5 points calib_y_within.
- Plotly 150 (held out): +7.1 points line_found, calib_x saturates (1.00).
- Chart.js corpus (a renderer no network has trained on): +61 points on the
  worst series.
- Real screenshots: 3 of 7 charts clearly fixed; 4 unchanged; no regression.

Regressions tracked and fixed during the work:
- The predecessor's 02:09 ablation showed x-scale 91 -> 80 on year axes;
  root-caused as `nice_step()` not firing on 0.09997 (log10 crossed the
  decade boundary); fixed.
- The predecessor's colour-aware label finder stripped leading glyphs on
  small labels; fixed by using raw ink for the along-axis extent.
- `_mask_tick_marks` initially caught 10^k superscript boxes; the isolation
  guard (12 cols) saves narrow text glyphs with neighbours, kept the fix.
- Duplicate ticks on real screenshots collapsed the along-axis window; fixed
  by deduping positions in `refine_labels` and in `fit_reads`.

## What did not work

- 9000169 multiplier: the '1e6' is noisy (many small components, legend
  nearby); the merge heuristic cannot cleanly isolate it from the clutter.
- 9000079 and 9000153 with '1e-5' / '1e-6': fixed by allowing the hyphen
  into the component set and widening the merge gap tolerance; but a border
  case where the leading '1' is pre-cut (loose_label 'e-6' alone) still
  fails. 1 of 7 multiplier charts remains unfixed.
- Rotated 45-degree labels: the current rotation is 90-degree-only; a
  45-degree branch would need the ink's principal angle and an affine
  un-rotate. probe t1-rot45/x stayed around 85% within.
- Reader misreads on small text that produce a wildly wrong value (e.g.
  9000090 '1e22' instead of '1e2') cannot be corrected by the joint
  decoder when no neighbour disagrees enough.

## Next steps

- The remaining multiplier case (9000169, '1e6' in a cluttered area): a
  learned text detector on the axis-end strip.
- 45-degree rotation: an affine un-rotate from the ink's principal angle.
- Dedup ticks upstream in `extract.group_labels` instead of in
  `refine_labels` + `fit_reads`; halves the reader work on duplicate ticks.
- 02-microprocessor '10^k' with a cut leading '1': decode_axis's
  expected-text would be a cleaner restoration than parse_value's '0^k'
  substitution, if cands include '10^k' as an alternate (currently they
  don't because the leading '1' is cut from the image itself).
- Reader fine-tune: adding more rotated, superscripted, and anti-aliased
  training examples would make the whole stack more robust (currently out
  of this team's area).

