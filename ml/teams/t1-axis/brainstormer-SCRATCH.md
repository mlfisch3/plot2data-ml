# Brainstormer scratch notes

Free-form chronological. Pause at Wed 28 Oct 2026, 18:00 EDT.

## Gotchas and findings not in NOTES.md

- `pgrep -af`/`pkill -f` match their own shell command line. If the pattern string appears anywhere in an ancestor shell's eval (because Claude Code wraps each command in a long `bash -c '...'`), you self-match. Rule: use `[p]attern` with a bracket on the first char, or (more robust) a sentinel file / PID instead of pattern matching. The predecessor's `diag-probe-base.sh` wedged for 14 h on this; the curator caught and killed it.
- Backgrounded `python ... &` from Claude Code's wrapped bash dies when the Claude-Code task completes, even with `nohup` on just the python call. The whole wrapper gets killed. For a job that must survive the Claude-Code task boundary, write the python command into a shell script file, then `nohup bash SCRIPT.sh > LOG 2>&1 &; disown`; the parent task can then exit and the python survives.
- `offline.py eval` is CPU-only by default (`device = "cuda" if a.gpu else "cpu"`); it is the right tool for iterating the reader + decoder without the GPU. Normal time about 60-130 s on 200 charts; under contention it stretches to 5-9 min.
- The frozen base ocr.py `parse_value` raises OverflowError on beam candidates like `1e400` or weird exponent fragments like `e+01`; the live tree in commit 244ce7b wraps it in try/except. Any CPU helper on the frozen base (diag.py, test_reader.py) that calls `parse_value` through import needs the same guard (curator added a monkey-patch in diag.py).
- A joint-decoder regression on year-labelled x axes was fixed by `nice_step`'s decade tolerance: a linear fit of `0.0, 0.1, 0.2` gives slope 0.0003373 and the step 0.09997 was floored to decade -2 (mantissa 9.997), missing the nice-step bonus. Fix: `math.floor(math.log10(s) + 1e-3)` and 2% mantissa tolerance.
- The colour-aware label finder (`label_from_source`) originally stripped the leading/trailing glyph of small labels because the colour-filter rows ran across the leftmost and rightmost ink. The fix is `band_ink = raw_ink[r0:r1 + 1]`: use the colour-filtered band ROWS but the raw ink COLUMNS. This looked tiny in code but moved the box test by about 1 point and fixed 9000081, 9000085, 9000093.
- `_mask_tick_marks` must blank the line rows (plot border, gridlines) BEFORE connectedComponents, otherwise the tick mark hangs off the border and the CC spans the whole window width (not narrow, not masked). Also `max_w` for a tick mark is 6 not 4: anti-aliased edges at the tick base add 1-2 px to the component width (9000162).
- The `_mask_tick_marks` isolation guard (12 cols) is why narrow glyphs like a leading `1` of `1,000` or `1e2` are kept: a text glyph has neighbouring ink in the same row range, a tick mark stands alone.
- `normalise_crop`'s rotate-tall-crops branch is a 2-line change but moved reader-on-true-boxes/rotated from 22.5% to 97.5% exact.
- My `axis_factor` explicit source-pixel scan at the axis end: the hyphen support (`h < 1`, not `h < 4`) was critical for `1e-5` and `1e-6`; the merge gap tolerance `max(10, 1.2 * h_est)` lets `1e` + `-` + `5` end up as one box.
- `extract.group_labels` on 01-panel1 real screenshot emits TWELVE ticks for FIVE year labels - duplicates at the same (pos, anchor_y). Fixed downstream by dedup in `refine_labels` (window spacing) and `fit_reads` (decoder input), but the upstream fix would be more efficient. Not my hunk.

## Where to look if we come back

- `out/t1/abl-mpl-v5.txt` and `abl-mpl-v5.json`: the 83.0 both-axes result from the HEAD-matching ablation on cd1956d, used for the +15.5 pts claim.
- `out/t1/v3-mpl-e2e.txt` (misleading name, really cd1956d full-scoreboard run; written at 16:56 EDT): the full mpl-val numbers in REPORT come from this. If the v5-mpl-e2e.txt finishes it will replace this.
- `out/t1/v3-corpus.txt` has the offset-annotation 0.019% line; keep this.
- `out/t1/v3-real.txt` has 01-panel1/2/3 and 03-women-men fixed.
- `teams/t1-axis/{diag,compare,test_boxes,test_reader,sheet,offline}.py` are the curator's and my CPU-only diagnostic set; `offline.py eval` is the fastest way to re-measure the whole axis stack when iterating.
- `CASES.md` has 12 failure classes with chart ids; the first 10 are the predecessor's catalogue, 11-12 are my regressions chased by the curator.
