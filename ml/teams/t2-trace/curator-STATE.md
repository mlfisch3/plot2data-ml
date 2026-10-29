## Identity

team=t2-trace
role=curator
agent id=replacement v2 (Opus 4.7, xhigh), resumed Wed 28 Oct 2026, 20:03 EDT after the 100-min pause reset
partner=brainstormer aefd0bb171b0e27ad (Opus 4.7 replacement)
state=DONE

## Final state

Branch team/t2-trace head: 563d02c (documentation only on top of 4ab8ee0 submission).
Submission commit: **4ab8ee0** - overlap-aware merge_fragments with Hungarian assignment (shipped by brainstormer at 17:04 EDT).
Documentation commits on top (no pushes): REPORT.md updates by brainstormer, CASES.md section 6 by me, NOTES.md running log.

Git clean, no uncommitted files.

## Measured deltas: v3 overlap-merge vs frozen 6b313e9

Headline geometry only:

| set | metric | frozen | v3 | delta |
| --- | --- | --- | --- | --- |
| mpl-val 200 all | line_found | 0.7570 | 0.7809 | +0.024 |
| mpl-val 200 simple | line_found | 0.8859 | 0.8993 | +0.013 |
| mpl-val 200 all | line_good_cov_mean | 0.5884 | 0.6052 | +0.017 |
| mpl-val 200 all | line_rms_median | 0.311 | 0.285 | -0.026 (improved) |
| plotly-v1 150 all | line_found | 0.8608 | 0.8770 | +0.016 |
| plotly-v1 150 simple | line_found | 0.9720 | 0.9626 | -0.009 (slight regression) |

Probe sweep (17 probes, 100-300 series each, line_found all / simple deltas):

Big wins: parallel +0.100/+0.119, shallowx +0.108/+0.109, legend +0.041/+0.042.
Solid wins: dotted +0.019, samecolour +0.013, step +0.011, cross +0.010, legocclude +0.007/+0.013.
Marginal: steep +0.004, thin +0.003, small +0.007, dense +0.007, clipped +0.004/+0.013, multi +0.002.
Neutral: markers 0.000.
Regressions: wide -0.008, area -0.005.

End-to-end with OCR (`live-overlap-merge-v3/val-e2e.txt`, `plotly-e2e.txt`):
- mpl-val 200 e2e: line_found all 0.5510, simple 0.6376 (d_simple +0.013 from geometry, propagates intact).
- plotly-v1 150 e2e: line_found all 0.7573, simple 0.7570 (d_simple -0.019, OCR calibration doubles the geometry regression on the 2 bad charts).
- Corpus 25: 25/25 found, median RMS 0.067%, tied with frozen.
- Real screenshots: usable.

Four regressions worth guarding against in a future pass (listed in CASES.md section 6 and REPORT.md):
1. parallel peak_err_median +0.153 (0.344 -> 0.498). Pick extremum-nearest piece for the merge, not median.
2. plotly simple -0.009 geometry / -0.019 e2e (2 of 79 charts). Raise min_q 0.3 -> 0.4 or require nov >= 50% min(A.n, B.n).
3. thin/wide line_rms_p90 blow-outs (+0.21, +0.27). Scale-aware gate on long-overlap rule.
4. area line_found -0.005. Minor; adjacent half-fill ridges.

## Artifacts

Code committed:
- ml/p2d/extract.py @ 4ab8ee0: overlap-aware merge_fragments + _join_cost + _end_slope + scipy import (brainstormer's).
- ml/p2d/extract.py @ 9be8e9c: 1e9 instead of np.inf in cost matrix for linear_sum_assignment (crash guard).
- ml/p2d/synth/probe_t2.py: 17 probe cases (shallowx and legocclude added this session).
- ml/teams/t2-trace/tools/compare_runs.py: side-by-side evaluate output comparison.
- ml/teams/t2-trace/tools/ (10 scripts, see curator-SCRATCH.md).

Analyses in ml/out/t2c/:
- dedupe-paths-analysis.txt, dedupe-upper-bound.txt, merge-oracle.txt, merge-rescue-detail.txt, overlap-stats.txt, val-regressions.txt (v1/v2/v3), inspect-val-v2.{json,txt}, summarize-val.txt.
- live-overlap-merge-v3/: 17 probe-set *-refine.txt, val-refine.txt, plotly-refine.txt, val-e2e.txt, plotly-e2e.txt, corpus.txt, real.txt, extract.py.snapshot, commit.txt. Each matched 1-1 with its frozen counterpart out/t2c/v3-*-refine.txt.

## Final deliverables

- ml/teams/t2-trace/REPORT.md head 73ba6a7 (brainstormer's).
- ml/teams/t2-trace/CASES.md head 185fd5c (section 6 added by me).
- ml/teams/t2-trace/NOTES.md head 563d02c (my running log).

## Hypotheses still open (for a next round)

1. Peak-at-turning-point regression on parallel: the merge picks the join point by overlap median; picking by nearest-to-extremum would preserve peaks. Not shipped.
2. Ghost-ghost on plotly simple: 2 of 79 charts regress. A min_q bump or nov-fraction gate on long-overlap would guard it.
3. The chain-oracle ceiling (0.86 cov / 0.91 found on mpl-val subset) is +0.05 found over v3. The next lever is a true cluster-fix (merge same-ridge clusters BEFORE chaining), not just merge after chaining.
4. drop_duplicates ceiling: +17 of 112 lost rescuable (+0.037 found) if envelope dedupe is replaced by chain-q scoring. Would need per-chain q and per-column agreement thresholds that this session did not have time to tune.

## Pause/resume protocol

usage_minder reports 11% at the start of session; now well under 40% threshold. All deliverables committed. No in-flight bg jobs.
