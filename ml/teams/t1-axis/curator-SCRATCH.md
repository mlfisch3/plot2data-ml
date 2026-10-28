# curator-SCRATCH, chronological

- **~16:06 EDT**: Opus 4.7 replacement online for a063cf4c9d3baa3c1 (Fable 5.1, cut off ~02:30 EDT).
- **~16:08**: Read brief + assignment + CASES.md + NOTES.md + mail. Found 14-hour wedged `diag-probe-base.sh` (predecessor's `pgrep -f "[t]1-axis/diag.py"` matched its own ancestor shell because the pattern string was in the heredoc eval). PID 829511/829508 killed; saved to `salvage/a063cf4c9d3baa3c1-excerpt.md`.
- **~16:10**: Committed takeover (NOTES.md entry, salvage, predecessor's `offline.py` and `test_reader.py`). Launched a clean `diag-probe-base.sh` against the frozen tree. Crashed in `parse_value` (base ocr.py raises OverflowError on 'e+01' and '1e+9999'). Added monkey-patch guard in `diag.py` + try/except in `test_reader.py` (commit 253a1e6).
- **~16:13**: Relaunched probe-base diag, succeeded. Fills `out/t1/diag-probe-base/summary.txt` (overall x 0.841/0.945, y 0.778/0.942). Committed per-style baseline table + class 11 (superscript regression on 10^k x axes) in CASES.md (8ef8cd3).
- **~16:15**: Brainstormer (a6077483041273a9d) up; committed its predecessor's snapshot as 244ce7b (axis.py 389 lines, colour-aware label_from_source, beam_decode in ocr, axis_factor wiring).
- **~16:17**: Queued `diag-mpl-v244.sh` (worktree, no P2D_ROOT). Ran in sequence after probe-base. +8.0 y within, +1.5 x within on mpl-val vs frozen. 22 y fixed, 12 x fixed. BROKEN: 15 charts; classified as 3 superscript (class 11), 7 colour-aware box crops/overgrows (class 12), 3 reader misreads, 1 fitter tiebreak, 1 border case.
- **~16:25**: Diag-probe-v244 ran: +3.9 y, +0.4 x within. Big wins: t1-two_log/y +40, /x +35; t1-pow10_edge/y +17.5. Regressions: t1-crowded_y/x -12.5, t1-tiny/x -7.5.
- **~16:28**: Flagged real-screenshot regression on 01-panel1/3 (year labels '2020..2024' cropped to '02'/'021'; fit log 145-487 px error). 03-women-men fixed (log -> linear, 2.11px).
- **~16:30**: Committed CASES.md class 12 extension with probe + real-screenshot evidence (09bb103). Made overlays for 9000016/21/24 (class 11) and 9000162/37/98/43 (class 12) + 01-panel1 (year labels). Visual confirmation: colour-aware label_from_source captures the tick-mark run as the "first glyph band" and widen step cannot bridge the 5-8 px gap to the real label.
- **~16:33**: Committed `remeasure.sh` (one-shot re-measurement) and CASES.md heading fix (418d604, d14c686).
- **~16:35**: Brainstormer landed three fixes in worktree: `_mask_tick_marks`, raw-ink along-axis extent, nice_step tolerance. I committed from their uncommitted state after they committed as 8bcd112.
- **~16:38**: Launched remeasure.sh v8bcd112; stale after brainstormer committed two more (d16bd92 axis-end multiplier scan, 3929f5c rotate tall crops). Killed and relaunched as v3929f5c.
- **~17:00**: Brainstormer landed three more: cd1956d (hyphens in multiplier scan), ba4b822 (widen `_mask_tick_marks` to max_w=6), 3c73e75 (dedup reads). HEAD at 3c73e75. Killed v3929f5c remeasure, launched v3c73e75.
- **~17:15**: Brainstormer's v5 ablation landed (both-axes 83.0, +15.5 vs base). My remeasure wedged - diag.py at 12 min elapsed, 0 overlays, GPU 90% full with 15+ competing processes, system load avg 20+. REPORT.md v5 ablation update committed by brainstormer (5e91191, 37c7ebe).
- **~17:57**: USAGE_MINDER PAUSE at 64% of 5-hour window. All my background tasks killed. State dumped to `curator-STATE.md` and this file. Idle.

# Diagnosis notes still open

- The real-screenshot v244-real.txt showed the 01-panel1 label_from_source returned 13-pixel-wide boxes CENTRED on each year label (true boxes ~26-30 px wide). After 3c73e75 the brainstormer verified it reads correctly, so the dedup + raw-ink fix did it.
- 02-microprocessor y labels still read as "0^k" because the image itself is cut mid-glyph; parse_value already handles this via "0^k" -> 10^k. Not a loss on the fit.
- 05-retail-sales still shows duplicate 2011/2016 reads (cosmetic, same text, same tick, same fit). The brainstormer's dedup is in refine_labels, not upstream in extract.
- Multiplier/offset: 6 of 7 mpl-val cases fixed post-cd1956d (hyphens). 3 misses: 9000079 ('1e-5' split with hyphen - partially addressed by cd1956d), 9000153 ('1e-6' leading '1' lost), 9000169 (loose piece reader confusion).

# Snippets to re-run after resume

Standard remeasure (git log -1 for the tag):

```sh
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml
nohup teams/t1-axis/remeasure.sh v$(git log -1 --format=%h) > /tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/remeasure4.log 2>&1 &
```

Then the waiter:

```sh
until grep -q "^DONE" /tmp/claude-1000/-home-drd-PROJECT-CLAUDE-PLOT2DATA/23ab78d4-5220-41dc-a4b1-aa1de0c3c1f6/scratchpad/remeasure4.log 2>/dev/null; do sleep 60; done; echo done
```

# What belongs in the final judge message

- Diagnosis: the nine classes from CASES.md, counts (y 47, x 32 failing axes; main sources: parser/fitter 16, reading/grouping 7, no-label-box 7.5 on y; reading/grouping 8, no-label-box 6, fitter 1.5 on x).
- Probe set: `data/t1-probe/`, 640 charts seeds 11,000,000..11,000,639, generator `p2d/synth/probe_t1.py`, baseline x 0.841/0.945 y 0.778/0.942; post-3c73e75 big wins on t1-two_log, t1-pow10_edge, t1-mult_sci, t1-offset, t1-rot90.
- Paths: `ml/teams/t1-axis/CASES.md`, `ml/teams/t1-axis/REPORT.md`, `ml/teams/t1-axis/NOTES.md`.
