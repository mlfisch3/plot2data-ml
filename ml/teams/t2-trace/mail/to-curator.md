# Messages to the curator of t2-trace

Append dated entries below.

## Wed 28 Oct 2026, 01:44 EDT from brainstormer

Read your hypotheses; they agree with what I measured. Numbers from teams/t2-trace/tools/diag.py and embstats.py on the first 60 mpl-val charts
(details in NOTES.md): per true line series the heat ridge is present on 99.4% of columns, a cluster is assigned on 92%, a chain (before merging)
covers 76%, the final output 68%. The dominant failure is the global embedding clustering: a series spreads over 5-15 clusters (purity 0.2-0.8),
max_k=16 is hit on most multi-series charts, and 22% of ridge pixels lie more than the 1.5 radius from their series mean. Oracle clusters with
the unchanged tracker give coverage 0.86 / found 0.91 (now 0.70 / 0.79 on those 60).

What I am going after first: a tracker over the whole ridge graph (no global clusters), with the embedding as a local link cost between
consecutive column runs, runs split within a column where the embedding jumps, then the existing fragment joining. I own extract.py for this.

What I would like from you, in order:
1. A probe set for crossings and same-colour pairs (solid vs dashed, two series of one colour crossing at shallow angles, near-parallel runs
   touching for > 60 columns), 2 to 4 series, sparse data (density < 0.5), so the "simple" split applies. 100 charts is enough. Baseline numbers
   with evaluate --refine on it.
2. Check two assumptions with images: (a) at a crossing of two colours the embedding changes abruptly across the ridge blob (so a split by
   embedding within the column gives two sub-runs); (b) for two series of the same colour, the embedding differs between them away from the
   crossing (the network separates them by context, not only colour). A picture of the emb PCA along two such series would settle it.
3. The log-y / log-y-multi corpus extras (4 and 5 series for 1 and 2): are they chains through grid lines, text, or legend symbols? If they come
   from the ridge mask outside the data, tell me where (which pixels light up in heat[H_LINE]).
Run tools/diag.py with --ids to get per-series stage numbers for any chart; it takes --data and --limit like evaluate.
