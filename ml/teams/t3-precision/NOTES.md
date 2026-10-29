# t3-precision notes

Dated entries, newest last. Both agents write here.

## Thu 29 Oct 2026 - brainstormer: round-2 kickoff

Angle: **C**, joint affine `mark = a + b * pos_net` fit in `refine_ticks` (shift-only for N <= 4 marks, slope-identifiable affine for N >= 5 with the `1 / sqrt(N)` window on `|b - 1|`).

Rationale from the brief's four targets:
- **A** (narrow-peaks / narrow-small): at integration narrow-peaks is parity, narrow-small is 0.109 vs 0.066 (+0.043 pp). A perfect fix moves corpus median by ~0.01 pp. Below the diminishing-returns threshold. Deferred.
- **B** (apex-both-sides regression): already resolved - integrator took `8053952` which pre-dates the regressing commit. No action.
- **C** (joint tick fit): current xticks_err_median 0.24 - 0.27 px, calib_x_within_0.5 0.905 / calib_y 0.895. Joint fit targets the `0.3 px floor` the round-1 report flagged.
- **D** (native-res tick measurement): `_pick_line` already reads source pixels. The drift the affine fit corrects is at the network side.
- **E** (frame corner p90): 14 - > 13 px at integration; substantive port overlapping team 5's frame code; defer.

Implementation (`f8b1b1b`):
- `_affine_from_marks(pos_net, marks, weights, slope_tol, resid_tol)`: iteratively reweighted LSQ with 2.5 * MAD outlier rejection.
- Slope window `max(0.004, min(0.015, 0.015 * sqrt(5 / N)))`.
- Guards: residual MAD < 0.35 px, max implied correction > min_shift (0.45 px), spread of inliers < max_spread (0.45 px).
- Shift-only fallback (slope locked to 1) when `|b - 1|` leaves window, when `_shift_only` branch is explicitly asked for (N < 5), or when the IRLS cannot pin the slope.

Tests (`f8b1b1b`): 6 new in `tests/test_core.py`. 116 pytest tests passing.

Diagnostic script `p2d.eval_ticks_r2` (`6d04060`): compares none / shift / affine on the same per-chart marks (one network pass per chart), bucketed by factor.

Pending measurements:
- `data/t3-ticks-r2` (1,000-chart probe, generator at `9daca35`, `79fad60`): running on GPU.
- Chart.js corpus, mpl-val 200, plotly-v1 150 with the new refine_ticks: queued on GPU behind ticks probe.

