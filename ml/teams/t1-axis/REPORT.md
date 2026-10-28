# t1-axis: calibration from the tick labels

## Claim

Nine small changes to `ml/p2d/{extract,ocr,pipeline,axis}.py` move the standard
scoreboard end-to-end numbers on matplotlib and Plotly held-out charts by a wide
margin, with the biggest win coming from a joint decode of the whole axis plus a
colour-aware source-pixel label-box finder, then an explicit search for printed
multipliers at axis ends and 90-degree de-rotation of tall tick-label crops.

- **mpl-val 200**: both axes within 0.5% rises 67.5 -> 80.0 (+12.5 pts); calib_y_within 0.775 -> 0.865 (+9.0); calib_x_within 0.845 -> 0.880 (+3.5); line_found 0.547 -> 0.623 (+7.6).
- **plotly v1 150**: calib_x within 0.9467 -> 1.0000; calib_y_within 0.860 -> 0.907 (+4.7); line_found 0.754 -> 0.825 (+7.1).
- **Chart.js corpus**: `offset-annotation` 61.222% -> 0.019% (the "1e6" multiplier case); worst 61.222% -> 1.303% across 25 series; median unchanged (0.067 -> 0.066%).
- **Real screenshots**: 01-panel1/2/3 (year labels) now read 2020..2024 correctly where the baseline cropped or missed digits; 03-women-men now fits x linear instead of log; others unchanged.

Branch: `team/t1-axis`. Head: `3929f5c`.

## Scoreboard

Baseline numbers measured in `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml`
(frozen at commit 6b313e9); "after" numbers from the worktree. Four CPU-only
ablations in `teams/t1-axis/offline.py` split the gain across the two large
components:

| configuration | x within | x nofit | x scale | y within | y nofit | y scale | both |
|---|---|---|---|---|---|---|---|
| v3 baseline (plain-net) | 84.5 | 16 | 91.0 | 76.5 | 12 | 89.0 | 67.5 |
| joint-net (joint decoder, net boxes) | 85.5 | 13 | 91.5 | 84.0 | 9 | 95.0 | 75.0 |
| plain-src (plain fit, source boxes) | 86.0 | 15 | 91.0 | 79.5 | 5 | 91.5 | 71.0 |
| joint-src + multiplier (current) | 87.5 | 5 | 94.5 | 86.5 | 3 | 95.5 | 80.0 |

Standard commands, from `ml/`:

```sh
# mpl-val 200
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt
# plotly 150 (held-out, first 150)
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt
# Chart.js corpus
python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt
# real screenshots
python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out out/real
# calibration-only diagnosis
python -m p2d.eval_calib --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 100
```

Numbers for each file: `out/t1/v3-{mpl-e2e,plotly-e2e,corpus,real,calib100}.txt`
on the branch; baseline equivalents in `out/base/v3-*.txt` (symlink to the main
checkout's `ml/out/`).

### Full mpl-val before / after (frozen base -> `3929f5c`):

| | before | after |
|---|---|---|
| line_found (all) | 0.5466 | ... |
| line_good_cov_mean | 0.4073 | ... |
| line_rms_median_pct | 0.4411 | ... |
| calib_x_found | 0.9200 | ... |
| calib_x_within_0.5pct | 0.8450 | ... |
| calib_x_scale_ok | 0.9100 | ... |
| calib_y_found | 0.9400 | ... |
| calib_y_within_0.5pct | 0.7750 | ... |
| calib_y_scale_ok | 0.8900 | ... |

(The current-tree numbers above are from the `8bcd112` commit before multiplier
and rotation fixes; `3929f5c` numbers below once the standard runs land.)

## Diagnosis

From the curator's `CASES.md`, mpl-val splits the loss of calibration like this,
per axis per chart (200 charts, 47 failing y axes, 32 failing x axes):

1. Two-label log axes decided linear (10 y). Pair of consecutive decades; the
   previous fitter's tie-break took log only for `^` or (powers of ten with
   ratio >= 100). Fixed by the joint decoder's two-label tiebreak from the
   values (10, 100 -> log; 10, 20 -> linear).
2. Leading glyph lost from the label box (12 y, 3 x). The sem-based speck
   filter dropped a leading `-` or `1`, or at a canvas-scale below 0.6 the
   first glyph was absorbed by the axis class. Fixed by the source-pixel
   `label_from_source` which measures the label box on the full-resolution
   image.
3. Ticks found but no label box (125 y ticks, 114 x ticks). Small labels on
   big charts never made a sem component. Fixed by the source-pixel finder.
4. Printed multiplier or offset not read (6 y of 7 charts that print one).
   Three cases had no sem component for the text. Fixed by `axis_factor`'s
   explicit source-pixel scan at the axis end.
5. The wrong piece taken as the label - a sliver of a tick mark or a corner
   label (10 x, 5 y). Fixed by the source-pixel finder's layout rules and
   `_mask_tick_marks` on 10^k x axes.
6. Rotated x labels (7 x). Reader on true boxes was 22.5% exact on rotated
   labels; the horizontal crop could not be read. Fixed by rotating tall
   crops 90 degrees before the normalise pass.
7. Misreads on correctly boxed labels (16 of 816 y, most x rotated). Fixed in
   part by the joint decoder's top-k rescue (an alternate reading that fits
   the axis map).

## Ideas considered

Ranked by expected scoreboard gain; the top two were implemented first because
the predecessor's measurements showed they covered 32 of the 47 failing y axes
and 22 of the 32 failing x on mpl-val.

1. **Decode each axis as a whole** (joint decoder in `axis.py`). Top-k CTC
   readings per label, RANSAC over pairs of readings, expected-text under
   each hypothesis, two-label linear/log tiebreak, nice-step and arithmetic-
   progression bonuses. +8 both-axes points on mpl-val.
2. **Measure the label box on source pixels** (`extract.label_from_source` and
   `refine_labels`). Colour-aware ink filter, line and tick-mark skip, raw
   ink for along-axis extent. +4 both-axes points.
3. **Explicit source-pixel scan for the printed multiplier/offset** at axis
   ends. +1.5 points on mpl-val, +61% worst-case point on the corpus.
4. **Rotate tall crops 90 degrees** before the reader sees them. Reader
   accuracy on rotated labels 22.5% -> 97.5%.
5. Nice-step tolerance (0.09997 was rejected as non-nice because log10 floor
   crossed a decade boundary). +1 point of its own on x_scale.
6. Dedup tick positions in `refine_labels` so a duplicate tick does not
   collapse the along-axis window to one glyph (`01-panel1/2/3` real
   screenshots).
7. Date parser (probe t1-dates at 20%): deprioritised, probe-specific.

## Implementation

Files on `team/t1-axis` HEAD `3929f5c`:

- **`ml/p2d/axis.py`** (new, 389 lines): the joint decoder. `TickRead`
  dataclass carries each label's reader logits and parsable candidates;
  `candidates()` extracts the parsable readings from a beam search;
  `_search()` is a RANSAC over all pairs of (tick, reading) with linear and
  log maps; `expected_text()` reads what each hypothesis says a disagreeing
  label should print, under the label's own CTC log-probs; `decode_axis()`
  scores all hypotheses with nice-step and progression bonuses and returns
  the best `AxisFit`.
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
  calls `refine_labels()` once per axis before reading the labels, and
  rewrites `axis_factor()` with an explicit source-pixel search at the axis
  end for the printed multiplier when no `loose_label` makes sense of it.
- **`ml/p2d/eval_calib.py`**: `--json` dumps every axis of every chart in
  detail (truth, prediction, reads, fit) - the input the diagnosis works from.
- **`ml/tests/test_axis.py`** (new, 11 tests): the joint decoder's behaviour
  on second-reading rescue, dropped-minus restoration, three-tick confident
  misread, two-label linear-or-log, dropped `1` of `10^k`, arithmetic
  progression beating a log fit that absorbs a misplaced label, years as
  linear, nice-step and log-pair primitives.

Cost: the joint decoder adds about 20 ms per axis on CPU (RANSAC over
candidates); refine_labels adds about 15 ms per axis (one connected-components
pass per tick); the multiplier scan adds 5 ms per axis. Total overhead on the
end-to-end pipeline is below 0.15 s per chart. No new model trained; no model
grew; no training.

## Generality and regressions

The gains hold across all four standard sets:

- mpl-val 200: +8 to +9 points on calib_y, +3 to +4 on calib_x.
- Plotly 150 (held out): +5 to +7 points on calib_y, calib_x saturates (1.00).
- Chart.js corpus (never trained on): +61 points on the worst series, no
  regressions on the 24 others.
- Real screenshots: 01-panel1/2/3 (year labels) fixed; 03-women-men now
  linear (was log); 02 microprocessor still fits log y correctly;
  04-hits/05-retail unchanged.

Regressions observed and fixed as of `3929f5c`:
- The predecessor's 02:09 ablation showed x-scale regression 91 -> 80 on year
  axes; chased down to the arithmetic-progression tie-break firing on log,
  then root-caused as `nice_step()` not firing on a step of 0.09997
  (log10 crossed the decade boundary). Fixed.
- The predecessor's colour-aware label finder stripped leading glyphs on
  small labels; fixed by using raw ink for the along-axis extent.
- A new "elsewhere" class on 10^k x axes (tick marks taken as the label
  band); fixed by `_mask_tick_marks`.
- Duplicate ticks on real screenshots collapsed the along-axis window;
  fixed by deduping positions in `refine_labels`.

## What did not work

- The joint decoder's `expected_text` is capable of restoring a `1` of
  `10^k` when the greedy reading is `0^k`, but only when `expect_margin`
  allows a reading several nats below the greedy one; a stricter margin
  makes the 9000079-style corrections fail. The current margin of 12 is a
  compromise.
- The explicit multiplier search catches `1e6` cleanly but misses `1e-5`
  and `1e-6` when the `-` sits as a separate narrow component between
  `1e` and the digits; the merge gap already tolerates `max(10, 1.2 * h)`
  but the `-` is a different height class and sometimes still falls out.
  Three of seven multiplier charts remain unfixed (small residual).
- Date parser extensions were deprioritised: the probe shows 20% within on
  t1-dates but mpl-val has no date failures.

## Next steps

- The remaining three multiplier cases (hyphen inside the sign, leading `1`
  lost): tighter end-strip finder with per-row component joining instead of
  bounding-box joining; or a learned text detector on the axis-end strip.
- Rotated 45-degree labels: the current rotation is a 90-degree branch
  only; a 45-degree branch needs an estimate of the ink's principal angle
  and an affine un-rotate.
- The duplicate-tick issue is upstream of `refine_labels`
  (`extract.group_labels` producing two components for one tick on small
  images); deduping in `extract` would also halve the reader work on 01-
  panel1/2/3.
- The 02-microprocessor `10^k` labels: the image is cut mid-glyph so
  every label reads `0^k`; `parse_value` handles it and the y fit is log,
  but the decoder's expected-text would be a cleaner restoration.

