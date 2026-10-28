# Salvage from brainstormer a21fb6c74947efb61 (Fable 5.1, 02:00-02:30 EDT)

Session hit the 5-hour limit near the end of debugging the new marker tests. The committed state (af04090) has 11 passing tests; the untracked `ml/p2d/zoom.py` is the predecessor's work-in-progress on candidate step 1 of its ranked list (a higher-scale tiled second pass for marker peaks against overlap).

## What landed on the branch

- `ml/p2d/markers.py` (555 lines): source-pixel ink weight, mixture-of-Gaussians centres per peak, size via isolated blobs plus `size_at` for touching, Agg-snap convention via circular statistics on the fractional centres, triangle-apex orientation that applies the bbox-centre offset, dashed-line veto on blob elongation, per-marker line-stroke veto on `size_at`, `attach_loose` that re-homes label-minus-one peaks by colour.
- `ml/p2d/extract.py` kept the loose peaks (label -1 or singleton clusters) on `ex.loose_markers` so they can be reclaimed in refinement; `refine_markers` is now a one-line delegate to `markers.refine_markers`.
- 11 marker tests in `ml/tests/test_markers.py` cover ink_weight, mixture split/merge, size_at, triangle apex, frac cluster, snapped series end-to-end, triangles get mpl bbox centre, dash veto, loose attach.

## What did not land

- `ml/p2d/zoom.py` (105 lines, untracked): tiled higher-scale pass for marker peaks. `zoom_scale` picks a scale from source-pixel marker size, `zoomed_marker_peaks` runs network tiles over the plot area and merges peaks across tiles. Not wired into `extract.py` or `pipeline.py`. The predecessor intended to validate the tile pass against measured gain before integration; nothing says it does yet.
- After-measurement of af04090 on any standard or probe set.
- Fine-tuning (candidate 5) and research on CenterNet-style instance heads (candidate 6).

## Predecessor's intent (from the NOTES 02:07 entry)

Candidates ranked 1 to 6; it chose to implement 2+3 first (deterministic, no GPU contention), then validate 1 (zoom), then 4 (merge split peaks), then 5 (fine-tune). The committed af04090 covers 2 (size-adaptive centre + snap convention) and 3 (dash veto / line-stroke veto / glyph test), plus parts of 4 (merge inside mixture, attach loose).

## Replacement plan

Measure af04090 on every set first, then decide whether zoom.py is needed given what the pixel-side work already won.
