# t1-axis notes

Dated entries, newest last. Both agents write here.

## Wed 28 Oct 2026, 01:40 EDT brainstormer: read everything, baseline reproduced, ranked ideas

Baseline v3 end to end on mpl-val (200): line_found 0.547 all / 0.624 simple; calib within 0.5%: x 0.845, y 0.775; calibrated at all: x 0.92, y 0.94; scale right: x 0.91, y 0.89.
Geometry alone (true ticks, --refine) finds 0.757 / 0.886, so the whole gap from 0.55 to 0.76 is calibration: a chart whose x or y axis fails to calibrate loses every series, and a chart whose calibration is off by more than 1% loses all its good-coverage credit.
Note the v1 oracle-ticks run (true tick positions and values) still has calib_y_within 0.915 and scale_ok 0.915: that is the two-tick linear/log tie-break in fit_axis alone, which chooses linear for "10, 100" and for exact powers of ten with ratio below 100.

Tools added: `p2d.eval_calib --json` dumps every axis in detail (true ticks, predicted ticks, text read, confidence, parsed value, fit, error). `ocr.beam_decode` (CTC prefix beam search, top-k strings with log P) and `ocr.ctc_score` (log P of a given string under the logits), unit-checked against each other.

Ranked candidate improvements for the calibration area, with my guess of the gain on the mpl-val scoreboard (calib within 0.5%, and line_found which follows it):

1. Joint decoding of an axis (top-k readings per label, the linear or log map that explains the most labels, then the text the map predicts at every disagreeing label scored under its CTC log-probs, so a misread digit or a dropped minus is corrected instead of thrown away; the nice-step rule decides linear versus log on two-label axes; RANSAC ties broken by progression regularity instead of pair order). Expected: +4 to +8 points on calib_y_within, +2 to +4 on x; line_found +4 to +7 points. Also fixes the v1-oracle residual (two-tick log axes).
2. Rotated x labels (12% of mpl charts rotate 30/45/90; the reader never saw a rotated crop): estimate the angle from the label mask, de-rotate the crop, read. Expected: most of the calib_x_found gap (8%) if the no-fit axes are mostly rotated ones; to be confirmed by the buckets.
3. Multiplier and offset text (matplotlib's "1e6" and "+1.2e3", 3 to 5% of mpl y axes; the corpus offset-annotation case): read the loose text near the axis end with the beam reader and a strict grammar; also when it touches the top label.
4. Crowded labels merged into one box by the (3,5) dilation in label_boxes: split a box that spans two ticks, or read with the map-predicted text per tick. Expected: +1 to +2 points on y.
5. Fine-tune the tick reader on crops cut with the predicted boxes' statistics, rotations, more fonts (from ocr1, short). Expected: +1 to +2 points.
6. Date axes: more formats, and the mixed case where some labels parse as numbers. Small on mpl-val (12% of charts have date x axes, most already read).

Going after 1 first (it is the general mechanism the others plug into), then 2 and 3.

## Wed 28 Oct 2026, 02:05 EDT curator: baseline reproduced, diagnosis tools, first diagnosis, probe generator

- Standard mpl-val e2e run from this tree before any edit matched out/base/v3-e2e-ocr.txt exactly (out/t1/base-mpl-e2e.txt, rows out/t1/rows-mpl.json, overlays of the first 40 in out/t1/viz-mpl).
- Baseline Plotly e2e run with --viz crashes in evaluate.draw (cv2.drawMarker on a non-finite marker pixel, chart 0500012); reported to the brainstormer. The later Plotly run picked up the brainstormer's live edits, so it is not a baseline. Rule from the judge from now on: every "before" number is measured in /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base (commit 6b313e9); my diag.py takes P2D_ROOT for that.
- Tools: teams/t1-axis/diag.py (per-tick diagnosis with ink-based grouping classes, two CPU ablations, overlays with the text read), reclass.py (re-classification from the JSON), sheet.py (contact sheets), gt_overlay.py (ground truth over a render, for generator checks).
- The first diagnosis, with counts and mechanisms, is in mail/to-brainstormer.md (02:02). In one line: y loses 9 points to the fitter's two-decade tie-break, 7 to reading/grouping (leading glyph dropped by the speck filter or absorbed by the axis class; tick-mark slivers and corner labels taken as the label; rotated x labels), 7.5 to labels that get no box (small text on big charts after the canvas downscale); all 6 multiplier charts fail because the '1e6' gets no box.
- Probe generator p2d/synth/probe_t1.py (16 styles, one per failure family; style by seed), checked by overlaying the recorded geometry on the renders (out/t1/gtviz). data/t1-probe: 640 charts at seeds 11,000,000+ generating now.
- Lesson: a pkill pattern must contain the team directory name (t1-axis); a generic script name matched across worktrees.

## Wed 28 Oct 2026, 02:17 EDT curator: the brainstormer's source-resolution box finder, tested from true ticks

- teams/t1-axis/test_boxes.py scores extract.label_from_source from the true tick positions against the label ink, CPU only: mpl-val 0.882 ok of 1922 labels, probe 0.978 of 7079. Seven mechanical misses found with row profiles (tick mark one pixel off the anchor row taken as the band; max_h=70 truncation; offset spines; dense x labels read as a line; rotated labels stopping after one glyph; superscripts consumed as attached; image-edge labels). Sent as mail 02:16.
- Women/men real chart: '2021' drawn at equal spacing after 1970..2010; log absorbs the 5 px misplacement and wins on inlier count. Reproduced on the CPU; rule proposed (arithmetic progression => linear).

## Wed 28 Oct 2026, 16:10 EDT curator: Opus 4.7 replacement, taking over

Identity: Opus 4.7 replacement for a063cf4c9d3baa3c1 (Fable 5.1, cut off by usage limit at about 02:30 EDT).
Partner the replacement brainstormer is a6077483041273a9d.

Salvage: `salvage/a063cf4c9d3baa3c1-excerpt.md` holds the two numbers that lived only in the JSONL
(the reader-alone exact rate on mpl-val true boxes, 0.990; test_reader.py's OverflowError on the probe
set, needs a `parse_value` guard). The predecessor's commits already covered CASES.md, NOTES.md, the
mailbox, the probe generator (`p2d/synth/probe_t1.py`), and every diagnosis tool.

State at arrival:
- `data/t1-probe` is 640 charts, seeds 11000000..11000639, generation complete.
- Baseline mpl-val and plotly-v1 e2e, calib, oracle numbers are in `out/t1/base-*.txt`.
- `out/t1/diag-mpl` and `out/t1/diag-plotly` have full summary.txt + diag.json + overlays.
- `out/t1/diag-probe-base` is EMPTY: the predecessor's wrapper hung in a pgrep self-match for 14 h,
  so the per-style baseline on the probe set is the big open gap. Processes 829511 and 829508 killed.
- The brainstormer has four uncommitted files (`p2d/eval_calib.py`, `p2d/extract.py`, `p2d/ocr.py`,
  `p2d/pipeline.py`) and two new files (`p2d/axis.py`, `tests/test_axis.py`). Left alone for the
  brainstormer's replacement.

First steps:
1. Commit the predecessor's two curator-side untracked files (`offline.py`, `test_reader.py`), the
   salvage note and this entry.
2. Launch the fixed `diag-probe-base.sh` against the frozen tree (background). Fill the pending
   per-style table in `CASES.md` from its `summary.txt` once it finishes.
3. Fix `test_reader.py`'s OverflowError and run it on `t1-probe` for the reader-alone probe
   baseline; the number says how much the probe set loses to reading vs. boxing.
4. Introduce myself to the brainstormer by SendMessage, pointer at the ready baseline files.

/usage_minder is active at 50%; on PAUSE I will export to `curator-STATE.md` and `curator-SCRATCH.md`
and commit as `wip(t1): pause-state snapshot`, reply "paused" and idle.

## Wed 28 Oct 2026, 16:15 EDT brainstormer (Opus 4.7, replacement of a33a9de7fe0759d04): salvage, status

Took over at ~16:00 EDT after my predecessor (Fable 5.1) hit the account's usage limit around 02:30.
Transcript salvage: ml/teams/t1-axis/salvage/a33a9de7fe0759d04-excerpt.md.
Partner (replacement curator, Opus 4.7): ad4f4c6475d1a2a70.

What the predecessor left uncommitted but working:
- ml/p2d/axis.py (389 lines): the joint axis decoder - top-k CTC candidates per label, pair RANSAC over readings, expected-text under each hypothesis, nice-step and arithmetic-progression bonuses, two-label linear/log tiebreak from the values.
- ml/p2d/pipeline.py: wires decode_axis in, runs refine_labels before reading when a reader is given, applies multiplier/offset to the fit after the fact.
- ml/p2d/extract.py: colour-aware label_from_source + refine_labels (re-measures every tick's label box at source resolution).
- ml/p2d/ocr.py: beam_decode (CTC prefix beam) and ctc_score (CTC forward); parse_value OverflowError guard.
- ml/p2d/eval_calib.py: --json dumps every axis in detail.
- ml/tests/test_axis.py: 10 unit tests of the decoder.
- ml/teams/t1-axis/offline.py: cache the net's extraction once, then iterate the reader + decoder on CPU; four ablations (old/new boxes x plain/joint decode).
- ml/teams/t1-axis/test_reader.py: tick reader on TRUE label boxes, per probe style.

Last ablation at 02:09 (BEFORE the colour-aware boxes landed; stale):
- plain-net: x 84.5% y 76.5% both 67.5%  (baseline)
- joint-net: x 85.5% y 83.5% both 75.5%  (+8 points both; -11 x-scale regression)
- plain-src: x 87.0% y 75.5% both 68.5%  (+1 both)
- joint-src: x 87.5% y 82.0% both 75.0%  (+7.5 both; -11.5 x-scale)
24 charts flipped x linear->log, mostly year-labelled axes. Verified in the CURRENT tree that chart 9000042 (linear years 1910-1950) now fits as linear - so the colour-aware boxes OR the parse_value fix OR something else between 02:09 and the handover killed the regression. The 02:09 ablation JSONs are no longer the current state.

Immediate plan:
1. Commit the salvaged state (plain message, no co-author) so the curator can measure it reproducibly.
2. Run pytest; fix any failures that come from the uncommitted churn.
3. Re-run the four CPU ablations on the committed state (offline.py: cache -> eval x 4).
4. Fresh full scoreboard (data/mpl-val 200, plotly-v1 150, corpus, real) once the ablations say the regression is gone.
5. Address the predecessor's unfinished items: the superscript "elsewhere" cases from the colour-aware box finder (10^k x-axes with the superscript taken alone), the long-run convoluted expression in `_row_shapes`, and the multiplier-text explicit search (class 4).

## Wed 28 Oct 2026, 17:00 EDT curator: measurements against 244ce7b

Four runs landed and were committed-adjacent (results in `out/t1/`, scripts in the same place).

- `diag-mpl-v244` (compare-mpl-v244.txt): y within+scale 0.765 -> 0.845 (+8.0), x 0.840 -> 0.855 (+1.5). Fixed 22y + 12x. Broken 6y + 9x; 3 of 9 x are the 10^k superscript (CASES class 11); 7 of the remaining 12 are the colour-aware box cropping leading chars or overgrowing (CASES class 12). Ticks found but with no box: x 114->8, y 125->9.
- `diag-probe-v244` (compare-probe-v244.txt): y within+scale 0.778 -> 0.817 (+3.9), x 0.841 -> 0.845 (+0.4). Big style wins: t1-two_log/y +40, /x +35, t1-pow10_edge/y +17.5. Regressions: t1-crowded_y/x -12.5, t1-tiny/x -7.5, several small -2.5s. 22 broken x all "cropped", 4 broken y all "cropped" - class 12.
- `boxes-mpl-v244` and `boxes-probe-v244`: live tree label_from_source quality. mpl 0.882 -> 0.921, probe 0.978 -> 0.960.
- `reader-probe-base.txt`: tick reader alone on t1-probe true boxes: TOTAL exact 0.964, value_ok 0.874; dates/x 0.351 exact; rot90/x/rot 0.000 exact; mult_sci/y and offset/y exact 1.000 but value_ok 0 because the multiplier is not in the label text (confirms the probe y ceiling 0.830 is axis_factor-bound).

Real screenshots (v244-real.txt): 03-women-men FIXED (log -> linear, max 2.11px); 01-panel1 and 01-panel3 BROKEN (year labels "2020..2024" cropped to "02" / "021", fit as log with 145 and 487 px error). Flagged to the brainstormer.

Mailbox updates to brainstormer (3): first with probe-base + ablation table, second with compare-mpl-v244 + the per-class breakdown of the 15 broken charts, third with compare-probe-v244 + the 01-panel regression.

Next: wait for the brainstormer's next commit (prototype fix for class 11/12), then re-diag against it with the chained scripts (out/t1/diag-*-v244.sh adapt in a line).

## Wed 28 Oct 2026, 20:05 EDT brainstormer (Opus 4.7, replacement #2 of a6077483041273a9d): resumed from pause, state confirmed

Took over at ~20:03 EDT after my predecessor hit the 5-hour window cap around 19:00-20:00. Window has reset (five_hour_pct 11%).

Confirmed on resume:
- Branch team/t1-axis clean, HEAD 5af6039 (pause-state snapshot on top of 83900f0 REPORT, code HEAD 3c73e75).
- Full HEAD scoreboard that was in flight at the pause has landed in out/t1/v5-{mpl-e2e,plotly-e2e,corpus,real}.txt (predecessor's PIDs 1115090-1115093 all finished during the pause). Numbers:
  * mpl-val: line_found 0.6876 (base 0.547, +14.1pt); calib_x_within_0.5pct 0.9050; calib_y_within_0.5pct 0.9050; calib_x_scale_ok 0.9650; calib_y_scale_ok 0.9600.
  * plotly-v1: line_found 0.8058; calib_x_within 0.9933 (scale 0.9933); calib_y_within 0.8867.
  * corpus: offset-annotation 0.019% (unchanged); 25 series, median 0.066%, worst 1.326% (log-log).
  * real: 01-panel1/2/3 fit linear, max error 0.98-1.04 px (fixed); 02-microprocessor-log-scatter fits y log; 03-women-men fits x linear 2.11 px (fixed); 05-retail-sales reads correctly.
- These are HEAD numbers; the REPORT's +15.5 pt both-axes-within-0.5% comes from the abl-mpl-v5.json CPU ablation, still intact (unchanged by the live v5 run).
- pytest 54/54 passing (unchanged since 3c73e75; no uncommitted edits).
- No new mail in to-brainstormer.md since 02:16 EDT.

Judge actions during pause (per briefing): killed OTHER teams' bypass-GPU-lock processes; p2d.serve killed; team 5's V2 Chart.js checkpoint at /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/runs/t5-chartjs/best.pt now exists (not used by me). None of t1-axis's queued work was affected.

New constraints noted:
- 4 GB GPU memory cap; every GPU eval must go through flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock.
- No self-arming Monitor loops that wake us.
- pkill/pgrep -f patterns MUST name t1-axis (already-practised).

Pinged partner curator (ad4f4c6475d1a2a70). No new tasks pending. Standing by.

## Wed 28 Oct 2026, 20:07 EDT brainstormer: judge acked, curator being resumed independently

Main acked my resume: V2 scoreboard numbers confirming REPORT are noted; no further request. Partner curator (ad4f4c6475d1a2a70) is being sent USAGE_MINDER RESUME by the judge and will do its own small cleanup. I remain standing by.

## Wed 28 Oct 2026, 20:08 EDT curator: resumed from pause

5-hour window reset to 10%, 258 min to next reset. New constraints: 4 GB GPU cap, flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock, single GPU process at a time, no self-arming Monitors. usage_minder at 40%.

State at resume: HEAD 0b11266 (brainstormer's resume entry). No code changes since 3c73e75 (my pause was between 17:57 and 20:06). My `diag-mpl-v3c73e75` had completed (someone - likely my own earlier process - must have finished during pause); `diag-probe-v3c73e75` was partial (39 overlays).

- Generated `compare-mpl-v3c73e75.txt` from the existing diag-mpl-v3c73e75: x within+scale 0.840 -> 0.905 (+6.5), y within+scale 0.765 -> 0.890 (+12.5), 42 fixed (16 x + 26 y), only 4 broken (3 x: 9000096 unexplained 3922%, 9000098 overgrown 1976%, 9000169 misread 1836%; 1 y: 9000014 overgrown 155%). class 11 and class 12 regressions ALL cleared except 9000014 overgrown y, 9000098 overgrown x. Rotated x labels down from 7 to 2 first-cause. Ticks with no box: x 114 -> 9, y 125 -> 9.
- Launched `boxes-mpl-v3c73e75` (CPU) and `diag-probe-v3c73e75` (GPU under flock).
