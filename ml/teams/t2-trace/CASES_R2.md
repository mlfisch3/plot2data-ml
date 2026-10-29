# t2-trace round 2 failure catalogue

Curator's record of what survived, what regressed, and what still bleeds after integration into `121ed4d` (`runs/t5-chartjs/best.pt` + `runs/ocr1/best.pt` + `--tta shift`).
Round-1 catalogue in `CASES.md`.
Measurements under `ml/out/t2r2/`: integrated model with `--refine --tta shift` on each round-1 probe set.
Round-2 probe generator at `p2d/synth/probe_t2.py` (new case `ghostpair`), seed base >= 12,170,000.

## 1. Starting point: integrated 121ed4d

Headline on `plotly-v1 150` end-to-end with the integrated pipeline (`--tta shift --ocr`):

| metric (all / simple) | base v3 | T5 V2 iso | integrated 121ed4d |
| --- | --- | --- | --- |
| line_found | 0.754 / 0.776 | 0.799 / 0.897 | **0.825 / 0.925** |
| line_rms_median_pct | 0.250 / 0.184 | 0.230 / 0.159 | **0.206 / 0.145** |
| peak_err_median_pct | 1.34 / 0.42 | 1.08 / 0.31 | **1.01 / 0.27** |
| marker_recall | 0.418 / 0.762 | 0.414 / 0.824 | 0.403 / 0.824 |
| marker_precision | 0.772 / 0.783 | 0.869 / 0.913 | 0.795 / 0.912 |
| frame_found | 0.940 / 0.924 | 0.940 / 0.924 | 0.947 / 0.924 |
| calib_x_within_0.5 | 0.947 | 0.960 | 0.993 |
| calib_y_within_0.5 | 0.860 | 0.893 | 0.887 |

Integration numbers reproduced on `team/t2-trace-r2` at 121ed4d: `plotly-v1 e2e` line_found 0.8252 / 0.9252 (matches integration-report to 4 decimals), confirming the baseline on this worktree is byte-identical to the integrator's.

The round-1 submission's **-0.019 plotly simple e2e regression** vs frozen v3 is NOT present in the integrated model: the integrated plotly simple is 0.9252, vs frozen v3 0.776 and T5V2 0.897. The t5 base reshaped the ridge enough that the ghost+ghost merge pattern no longer costs on this set; the +0.030 win over T5V2 on plotly simple line_found suggests round-1's merge-fragments rewrite is NET POSITIVE on plotly simple in the integrated model (where it was NEGATIVE on top of frozen v3).

## 2. Residual losses

Three residuals from the integration report (sorted by size):

- **mpl-val line_found behind T1 isolated by 2.6 pp** (0.6616 vs 0.6876). Mechanism: T1's gained calibration is partly lost when combined with t3's source-pixel measurement and t5's TTA shift (coverage threshold hits a calibration jitter). Any merge-side change we make shows at most 0.015 of this gap (round-1's mpl-val simple e2e +0.013 was from the merge fix alone).
- **Plotly marker_recall `all` -1.6 pp vs base** (0.418 -> 0.403): 309-series set, well within noise. Not merge-fragments territory.
- **Corpus median +0.02 pp (0.067 -> 0.087%)**: t3's source-pixel measurement adds a small bias on easy single-solid charts. Trade for 61.222 -> 0.214% worst case. Not merge-fragments territory.

The only residual the overlap-merge rewrite can plausibly reclaim is **the plotly simple geometry/e2e drop** that round-1 explicitly flagged. In integration it is already recovered (0.925 simple), but the two offending seeds (500106, 500111) may still fail; the brainstormer's `min_q 0.3 -> 0.4` plus `nov >= 0.5 * min(A.n, B.n)` guard is defensive protection against the ghost+ghost pattern.

## 3. Round-1 probe re-measurement on 121ed4d

Measured with `--refine --tta shift` on `runs/t5-chartjs/best.pt`. Numbers written to `ml/out/t2r2/int-<probe>-refine.txt`.
Deltas vs round-1 submission (`v3/best.pt --refine` on `v3-overlap-merge`, from `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/live-overlap-merge-v3/`).
Deltas vs frozen baseline (`v3/best.pt --refine`, from `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t2-trace/ml/out/t2c/v3-*-refine.txt`).

| probe | frozen v3 | round-1 fix | integrated 121ed4d | d_int-vs-r1 | d_int-vs-frozen |
| --- | --- | --- | --- | --- | --- |
| cross | 0.9167 | 0.9267 | _(pending)_ | | |
| samecolour | 0.9000 | 0.9125 | _(pending)_ | | |
| parallel | 0.7100 | 0.8100 | _(pending)_ | | |
| shallowx | 0.7576 | 0.8658 | _(pending)_ | | |
| legocclude | 0.8179 | 0.8247 | _(pending)_ | | |
| legend | 0.8560 | 0.8971 | _(pending)_ | | |
| dotted | 0.8714 | 0.8905 | _(pending)_ | | |
| steep | 0.8872 | 0.8910 | _(pending)_ | | |
| thin | 0.8533 | 0.8567 | _(pending)_ | | |
| small | 0.7000 | 0.7067 | _(pending)_ | | |
| dense | 0.9118 | 0.9191 | _(pending)_ | | |
| area | 0.5600 | 0.5550 | _(pending)_ | | |
| step | 0.8385 | 0.8490 | _(pending)_ | | |
| clipped | 0.8016 | 0.8054 | _(pending)_ | | |
| multi | 0.6550 | 0.6567 | _(pending)_ | | |
| markers | 0.9167 | 0.9167 | _(pending)_ | | |
| wide | 0.8722 | 0.8647 | _(pending)_ | | |
| **ghostpair (new)** | n/a | n/a | _(pending)_ | | |

## 4. Round-2 probe: `ghostpair`

Target: provoke the long-overlap ghost+ghost pattern that drove round-1's plotly simple -0.019 e2e regression (seeds 500106, 500111 in plotly-v1), on seeds >= 12,170,000 under the shared probe harness.

Mechanism: when a line is drawn thick (3-5 px source stroke) on a presentation-sized canvas, matplotlib's anti-aliased renderer draws paired "flank" ridges either side of the stroke centreline that are picked up by the network as weak clusters (q 0.3 to 0.5). Both flank clusters span the same column range as the real line, with a near-constant y gap of 2-5 px. The round-1 overlap-aware `merge_fragments` sees `|median| < 6`, `MAD < 1.2`, `drift < 2.5` across the overlap and joins the two flank clusters into one longer chain that passes `drop_duplicates`.

Spec (committed to `p2d/synth/probe_t2.py`, case index 17, seed base 12,170,000):

- 1-3 series per chart, each spanning most of x range (n = 80..260).
- Thick strokes: `lw` 3-5 (matplotlib points) at dpi 100-120, so canvas-pixel stroke 4-8 px.
- Wide figures: `wpx` 900..1400, aspect 0.4..0.6 (presentation-shape).
- Smooth shapes (sines, trend_noise, poly, logistic, walk).
- Mix of solid, dashed, dashdot (matches 500106/500111 line styles).
- Plotly-presentation palette shifted into the probe colour pool so some charts have same-family colours (blue vs cyan, orange vs red) to raise the chance a ghost cluster of series A overlaps the real of series B.
- `ylim` padded 30% so each series fills the middle of the plot (ghost flanks sit inside the plot area, not clipped).

Verification: 100 charts generated at seeds 12,170,000..12,170,099 in `data/t2-ghostpair/`.
Composite overlays and per-chart stage attribution to follow.

## 5. What the integrated model does with each round-1 failure case

(Will be filled after the probe batch finishes. Expected pattern given the plotly-v1 e2e result:)

- **C1 (series cut into long non-overlapping pieces)**: likely still improved; the t5 base trained on more styles so clusters may already span further, but the overlap-aware merge compounds the gain.
- **C2 (hopping at a crossing)**: unchanged by the merge fix; marginal win if any.
- **C3 (steep interruption)**: the long-gap slope-aware branch still applies. T5's TTA shift averages ridge y which may stabilise the slope estimate.
- **C4 (dense/steep one-value-per-column)**: representation-side; nothing in r2 addresses it.
- **C5 (spurious lines, ghosts, fragments)**: the ghostpair angle targets this. If `min_q 0.4` + nov guard holds, worst-case fragment counts should drop on `multi`, `wide`, `clipped`.

Thu 29 Oct 2026, 01:40 EDT (skeleton; pending-marked rows fill as the probe batch completes).
