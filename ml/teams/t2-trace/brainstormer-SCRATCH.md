# t2-trace brainstormer scratch

Chronological, warts and all.

## Replacement spin-up (Wed 28 Oct 2026 ~16:05 EDT)

- Inherited the predecessor's committed state: probe generator, diagnostics, failure catalogue, baselines on 17 probe sets. Direction-head scaffolding and a joint whole-ridge-graph tracker were UNCOMMITTED but in the working tree.
- First measurement of the uncommitted tracker on the first 20 charts of data/t2-cross: regression. found 1.000 -> 0.896, rms_p90 0.37% -> 12.3%. The joint tracker regresses on simple crossings. Rolled back and preserved at commit 9b97b78 "wip(t2): checkpoint predecessor's uncommitted tracker rewrite and tests".

## Diagnosis (16:15-16:30 EDT)

- Curator's inspect-val-v2.json showed 207 refused junctions between pieces of one true series in mpl-val, 83% OVERLAPPING with p50=374 cols p90=636 cols; 96% ygap-within-rule; only 3% in `dx in [1, 60]` where the frozen merge rule even looks.
- Key insight: the dominant failure is "two whole chains that span the same column range because a cluster boundary ran down the middle of a continuous ridge" - NOT an "end of A meets start of B" case.
- Decided to pivot from the predecessor's whole-ridge tracker (big, risky) to overlap-aware merge_fragments (small, local).

## First attempt (16:30-16:45 EDT, "v1")

Rule: median diff <= 2.0, p90 <= 6.0, emb_tol = 4.0.
Result on mpl-val 200: found 0.7570 -> 0.7332 (-0.024). Spurious merges in multi-series charts: a 400-col overlap can have median diff <= 2 by accident where two different series run close in that region but diverge at ends.
Only 2 of 42 rescuable same-series pairs recovered (curator's simulation).

## Second attempt (16:45-16:55 EDT, "v2")

MAD-based rule: median absolute deviation <= 1.5, drift <= 3.0, |median| <= 10.0.
Reasoning: same-series split has NEARLY CONSTANT y gap; crossing has gap varying across the overlap.
Result: found 0.7267. Worse. Reason: the no-overlap branch was simultaneously using slope extrapolation at every dx, which rejected endpoints at sine extrema that the frozen rule accepted.

## Third attempt (16:55-17:05 EDT, "v3", shipped)

Fixed the no-overlap branch: use the frozen rule EXACTLY for `dx in [1, 60]` and only use slope extrapolation for `dx > 60`.
Long overlap rule: ks-disjoint (different clusters) + both chains have q >= 0.3 and >= 50 columns + `|median| <= 6, MAD <= 1.2, drift <= 2.5`.
Result on mpl-val 200: found 0.7570 -> 0.7809 (+0.024). Shipped as 4ab8ee0.

## Dedupe experiments (17:05-17:20 EDT)

- dedupe-v1 (envelope removed, per-column interp, support sort): pred counts exploded (6 -> 22 on 9000037 and others); no change to found.
- dedupe-v2 (envelope kept but window 4 -> 1, tol 3.0 -> 2.5, support sort): similar explosion. Found: +0.002, not a win.
- dedupe-v3 (compromise window=2, tol=3.0, support sort): killed before completion. 
- Conclusion (confirmed by curator): dedupe is a red herring on mpl-val. The "ghost outranks real" case curator identified in shallowx is rare on broader val. Rolled back drop_duplicates to the frozen version.

## Plotly simple regression analysis (not fixed)

Charts 500106 and 500111 lost found (3-series each; cov went 0.77/0.82 -> 0 for one series; pred count 3 -> 4-5).
Hypothesis: overlap-merge joined TWO GHOSTS of a real series into one bigger ghost that survived drop_duplicates. Guard would be: raise min_q from 0.3 to 0.4 or require nov >= 50% of min(A.n, B.n).
Not fixed because it's 2 charts out of 79 and the mpl-val gain dominates the plotly simple loss.

## Gotchas

- scipy.optimize.linear_sum_assignment behaves oddly with np.inf in the cost matrix on some versions. Changed to 1e9. (Commit 9be8e9c.)
- Hungarian uses a 2n x 2n matrix with no_join cost on identity blocks of the "ghost" cols/rows. ri, cj where i < n and j < n and C[i,j] < no_join tells you the live edges.
- The predecessor's direction head is in the model but no checkpoint has those weights. evaluate.load_net correctly sets dir_head=False when weights are absent. Dormant otherwise.
- The committed drop_duplicates MUST stay as frozen for the v3 numbers to hold. I verified by re-running mpl-val 200 after revert.
- My no_join = 5.0 means cost < 5 joins, >= 5 does not. The gap case cost is 0.03 * (gap + dx) + de so a 60-col gap with zero gap-pixels and de=1 costs 1.8 + 1 = 2.8; well under 5. The overlap case cost is bigger: a 400-col overlap with med=2, MAD=0.3, drift=0.5, de=1 costs 2 + 0.6 + 0.25 + 1 + 0.2 = 4.05. Just under 5. The threshold is tight on purpose.
- Tests of _join_cost and merge_fragments use fragments with slopes 0.1 and 0.4. Early tests had bad fixtures (f1.y at col 100 was 10 not 20 when the line is y = 10 + 0.1 col). Fixed by making y_at_c0 explicit.
