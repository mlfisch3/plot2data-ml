# Round 6 - Noisy single-line split into twin series

Branch: `round6/noisy-line`.
Checkpoint `runs/t5r2-clutter/best.pt`, OCR `runs/ocr1/best.pt`, `--tta shift`.

## The failure

The user tested the extractor on a real Excel-rendered chart (a very noisy sinusoid, Excel-default dark-grey line with Y gridlines) and got two series back instead of one.
`/home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/test_plot.png` (2722 x 1138) with truth in `ml/test_data.csv` (932 points, X in [0.002, 1.866], Y in [-7.5, 296.0]).

Baseline (main at `c17d9fa`):

```
series_1 color=(81,81,81)   2252 points
series_2 color=(196,196,196) 2142 points   <- a twin along the SAME curve
```

Both traced essentially the same sinusoid (smoothed Pearson r = 0.997 over the shared cols).

## Diagnosis

The split is produced in `extract()` in `ml/p2d/extract.py`.
Within one embedding cluster (`k=0`, 29588 pixels of the dark line) `peel_chains` yields two long chains at mostly overlapping x-columns: cols 80-1539 n=1460 (the dark primary) and cols 154-1542 n=633 (the twin).
A thick stroke plus noise leaves enough leftover column runs after the first greedy chain for a second chain to form through the same curve, drifting 1-13 px off at any given column but tracking its wiggles everywhere.
`merge_fragments` leaves them separate (same cluster can legitimately be a split curve), and `drop_duplicates`'s local-envelope test misses the twin: at `window=4, tol=3.0`, only 60.8% of the shorter chain's cols sit inside the longer's envelope (below the 70% duplicate threshold).

Per-column `|y_fringe - y_main|` is median 7.6 px, p99 22.4 px.
That is wider than a stroke, so no local test with a sensible tolerance catches it.
The global signature is Pearson correlation of smoothed trajectories: 0.997.

The two chains then become two series through `_make_series`, which paints the chain pixels back onto the source image and takes the median RGB.
The primary chain lands on the dark line body (81,81,81) and the twin lands on the anti-aliased edge (196,196,196).

Evidence (per-stage spies on the test image):

```
cluster_embeddings: 3 clusters, k=0 holds 29588 of 38552 pixels
frags_after_merge[0]: ks=[0] n=1460 cols=[80,1539]  y=[136,585]   <- primary
frags_after_merge[1]: ks=[0] n=633  cols=[154,1542] y=[141,592]   <- twin
drop_duplicates: 11 fragments go in, both of these come out.
                 shared cols 845, smoothed Pearson r = 0.997.
```

## Fix

`ml/p2d/extract.py :: drop_duplicates` and new `_parallel_curve` helper.

After the existing local-envelope test, if the shorter chain still covers >= 70% of its cols against the longer, run a global check: smoothed Pearson correlation of y-trajectories at matched cols must be >= 0.99, AND median absolute smoothed-y difference must be <= 2.5% of the longer chain's y-range.
Both gates must hold.
Two chains with the same shape at well-separated y-levels (common on multi-series matplotlib) sit at correlation 1 but tens of pixels apart; the proximity gate rules them out.
Two chains at r = 0.98 (close but not identical) also stay apart, so adjacent legitimate series are not pulled in.

The function also keeps a `shields` list: every chain that lost its duel against a kept chain still shields later ghosts.
Without it, dropping the twin from `kept` would let short fragments previously shadowed by the twin's wide y-envelope leak through as spurious series (the twin is a 450-px-tall umbrella on the test chart).

Rejected alternatives:

- Greyscale-colour merging (option B in the brief): would regress charts that deliberately use different greys for different series.
- Retrain the embedding (C): round-7+ territory.
- Loosen envelope tol/window: either misses this case (too tight) or merges legitimate adjacent series (too loose).
- First attempt - correlation-only gate at r >= 0.95: on mpl-val --limit 200 this regressed line_found by 12 pp (56 series dropped as false duplicates). Correlation 1 fits two parallel series of the same shape at different y-levels; the proximity gate is required.

## Before / after on the user's chart

| | before (main `c17d9fa`) | after (`round6/noisy-line`) |
| --- | --- | --- |
| series returned | 2 | **1** |
| points returned | 2252 + 2142 | 2252 |
| RMS vs truth (Y units) | 5.39 | **3.62** |
| Relative RMS (RMS / Y-range) | 1.78% | **1.19%** |

RMS computed by resampling truth and extracted on a common x-grid at step 0.002.
Overlay-before and overlay-after at `ml/teams/round6-noisy-line/overlay-{before,after}.png`.

## Tests

`ml/tests/test_trace.py` gained 7 tests (15 total pass in that file):

- `test_drop_duplicates_catches_parallel_twin_noisy_trace` - two noisy sinusoids one offset by 4 px merge to 1.
- `test_drop_duplicates_keeps_two_truly_separate_series` - same column range but y 200 px apart, both survive.
- `test_drop_duplicates_keeps_disjoint_segments` - two segments at non-overlapping x stay apart even with similar shapes.
- `test_parallel_curve_rejects_short_overlap` - with <20 shared points the gate stays closed.
- `test_parallel_curve_detects_same_curve_at_offset` - two noisy copies of the same sin shifted 5 px flag parallel.
- `test_parallel_curve_rejects_different_curves` - two sinusoids at different phase stay apart.
- `test_parallel_curve_rejects_same_shape_far_apart` - two identically-shaped sinusoids 200 px apart in y stay apart (proximity gate).

Full suite:

```
185 passed in 13.39s   (178 original + 7 new)
```

## Standard scoreboard - no regression

Checkpoint `runs/t5r2-clutter/best.pt`, OCR `runs/ocr1/best.pt`, `--tta shift`, run under `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`.
Each row is the "all" metric.
Baseline is current `main` at `c17d9fa` (same code except for `drop_duplicates`).

### `data/mpl-val --limit 200 --refine`

| metric | baseline | fix | delta |
| --- | --- | --- | --- |
| line_found              | 0.6920 | 0.6920 | 0 |
| line_cov_mean           | 0.6292 | 0.6292 | 0 |
| line_rms_median_pct     | 0.3257 | 0.3257 | 0 |
| line_rms_p90_pct        | 2.6518 | 2.7843 | +0.13 |
| peak_err_median_pct     | 1.5218 | 1.5386 | +0.02 |
| marker_recall           | 0.6057 | 0.6057 | 0 |
| xticks_fp_per_img       | 0.6100 | 0.6100 | 0 |
| yticks_fp_per_img       | 0.5950 | 0.5950 | 0 |
| calib_x_within_0.5pct   | 0.9050 | 0.9050 | 0 |
| calib_y_within_0.5pct   | 0.8950 | 0.8950 | 0 |

Per-row diff: 1 series changed matching (9000130: series 0 cov 0.98 -> 0.0 but series 2 cov 0.0 -> 1.00, net zero on `line_found`, improvement in matched cov).
Zero series dropped as false duplicates.

### `data/plotly-v1 --limit 150 --refine`

Byte-identical with the baseline (`diff` is empty).

### `eval_corpus` (Chart.js corpus, 25 series)

Byte-identical with the baseline (`diff` is empty).
`series 25  median 0.071%  worst 0.563%  failed 0` - unchanged.

### `data/t5-real-100` (`eval_t5real`, 110 charts, 237 series)

| metric | baseline | fix |
| --- | --- | --- |
| series                 | 237 | 237 |
| found (cover >= 80%)   | 76% | 76% |
| median rms             | 0.31% | 0.30% |
| median rms of found    | 0.28% | 0.28% |
| within 1%              | 62% | 62% |
| within 0.5%            | 53% | 53% |
| failed (NaN)           | 24  | 25 (+1) |

Nine charts return fewer predicted series (duplicate pruning): `fred-cpi-two` 5->4, `fred-dcoilwti-dcoilbrent` 4->3, `fred-dgs10-dgs2` 5->4, `giss-global-mean` 5->4, `giss-land-only` 6->5, `giss-seasonal` 53->44, `noaa-n2o-monthly` 6->5, `wb-gdp-5` 6->5, `wb-inflation-emerging` 4->3.
One chart (`fred-cpi-cpifood`) regressed its second series to NaN, offsetting the `giss-land-only` first-series RMS improvement (4.91% -> 3.60%); net on the aggregate is -0.01 pp median rms and +1 failed, while `found` and `within-N%` are all unchanged.

## Reproducing

```sh
cd ml
source ../../PLOT2DATA/.venv/bin/activate

# User's chart
flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.pipeline \
  /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/test_plot.png \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt --tta shift \
  --csv out/r6/test_fix.csv --overlay out/r6/test_fix_overlay.png

# Scoreboard
OMP_NUM_THREADS=1 flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/mpl-val --limit 200 --refine --tta shift

OMP_NUM_THREADS=1 flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.evaluate \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/plotly-v1 --limit 150 --refine --tta shift

OMP_NUM_THREADS=1 flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.eval_corpus \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt --tta shift

OMP_NUM_THREADS=1 flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock python -m p2d.eval_t5real \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/t5-real-100 --tta shift
```

Mon 2 Nov 2026, 17:27 EST
