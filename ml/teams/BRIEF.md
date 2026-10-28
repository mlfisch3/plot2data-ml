# The accuracy contest: brief for every team

Written Wed 28 Oct 2026.
Read this whole file before doing anything else, then your team's `ASSIGNMENT.md` next to it.

## Why this matters

plot2data-ml turns an image of a chart into the numbers that drew it.
Treat the task as if lives depend on the numbers being right: data locked in images of charts, in papers, reports and PDFs, must come back out with the greatest accuracy over the broadest range of charts.
"There is no way to do that" is not an acceptable finding.
When a limit shows up, find a way around it: a different representation, a transformation of the image, a second model fed by the first, an explicit measurement where learning is imprecise, a learned step where the explicit one is brittle, or several of these chained.
Ugly is fine.
A bigger model, a slower pipeline, or a second network is fine if the numbers get better.
Exotic for its own sake is not the goal: the measured quality of the extraction is.

## What exists

The learned pipeline lives in `ml/` and is described in `ml/README.md` (design) and `ml/RESULTS.md` (measured numbers as of v2).
Read both, then the code: it is about 4,500 lines of Python.

- `p2d/synth/`: synthetic chart generators with exact ground truth (matplotlib with house-style presets; Plotly through kaleido). `build.py` writes a dataset.
- `p2d/data.py`: dataset, augmentation, and target rasterisation (heat maps and embedding ids drawn from vectors after the geometric transform).
- `p2d/model.py`, `p2d/losses.py`, `p2d/train.py`: PlotNet (ResNet-34 U-Net, full-resolution stem, three heads: `sem` 7 classes, `heat` 6 maps, `emb` 8-d) and its training.
- `p2d/extract.py`: decoding of the network output into series, markers, ticks and the frame; refinement of lines, ticks and markers on the source pixels.
- `p2d/ocr.py`: the tick-label reader (a small CTC model) and `parse_value`; `p2d/dates.py`: date labels.
- `p2d/calibrate.py`: RANSAC plus least squares fit of tick values to tick positions, linear or log.
- `p2d/pipeline.py`: the whole thing on one image; `p2d/sampling.py`: uniform-step resampling.
- `p2d/metrics.py`, `p2d/evaluate.py`, `p2d/eval_corpus.py`, `p2d/eval_real.py`, `p2d/eval_calib.py`, `p2d/score_classical.py`: the scoreboard.
- `p2d/serve.py`: a local test page; `p2d/export.py`: ONNX export (the models are meant to run in a browser eventually, but accuracy comes first; do not let deployability stop an idea, just note the cost).
- `../src/engine/` is the classical, hand-written engine this project replaces; `../docs/classical-engine-notes.md` records what it learned. `../corpus/` is its Chart.js test set, `../examples/real/` real screenshots.

Checkpoints (shared, read-only for you): `runs/v3/best.pt` is the current network (trained on matplotlib v1 + v2 house styles + Plotly); `runs/ocr1/best.pt` the tick reader; `runs/v2/best.pt` the previous network.
Datasets (shared, read-only for you): `data/mpl-v1` (40k charts), `data/mpl-v2` (12k, house styles), `data/plotly-v1` (12k Plotly), `data/mpl-val` (1,000 validation charts, seeds 9,000,000+).
Each chart is a PNG plus a JSON of exact ground truth (plot area, ticks with value/position/text/bbox, series with the drawn polyline in pixels, markers, colour, line width, the data values) plus per-pixel class and instance maps.

Baseline outputs of v2 and (as soon as they finish, within the hour) v3 are in `out/base/` (a symlink to the main checkout's `ml/out/`): `v3-pixel.txt`, `v3-e2e-ocr.txt`, `v3-plotly-e2e.txt`, `v3-corpus.txt`, `v3-real.txt`, with overlays under `out/base/corpus-viz-v3/` and `out/base/real-v3/`.
If `out/base/v3-e2e-ocr.txt` does not exist yet, start from the v2 files and the tables in `RESULTS.md`; the numbers are close.

## The scoreboard

All errors are a percentage of the plot's full height; 0.1% is a tenth of a percent of full scale.
"Simple" charts have at most three series and fewer data points than pixel columns; "all" includes up to six overlapping series of up to 2,500 points.
A chart is judged on these, in this order of weight:

1. End to end on `data/mpl-val` (200 charts): `line_found`, `line_good_cov_mean`, `line_rms_median_pct`, `peak_err_median_pct`, `marker_recall` / `marker_precision`, `calib_x_within_0.5pct` / `calib_y_within_0.5pct`.
2. End to end on the 150 held-out Plotly charts (`data/plotly-v1`, the first 150; nothing after them is held out).
3. The Chart.js corpus (`eval_corpus`): per-series RMS against published data, a renderer no network has trained on.
4. The real screenshots (`eval_real`): series counts and calibration error at hand-measured anchors.
5. Geometry only (`evaluate --refine`, true tick values): where the pixels are measured, independent of label reading.

The exact commands, run from your worktree's `ml/` directory with the venv active (`source ../.venv/bin/activate`):

```sh
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --ocr runs/ocr1/best.pt      # 1
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/plotly-v1 --limit 150 --ocr runs/ocr1/best.pt   # 2
python -m p2d.eval_corpus --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --viz out/corpus-viz             # 3
python -m p2d.eval_real --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --out out/real                     # 4
python -m p2d.evaluate --ckpt runs/v3/best.pt --data data/mpl-val --limit 200 --refine                    # 5
python -m p2d.evaluate ... --oracle-ticks     # end to end with true tick values: isolates calibration from geometry
python -m p2d.evaluate ... --viz out/viz --json out/rows.json   # overlays and per-chart rows, for finding the worst cases
python -m p2d.eval_calib --ckpt runs/v3/best.pt --ocr runs/ocr1/best.pt --data data/mpl-val --limit 100   # calibration only, per axis
```

Rules of the scoreboard:

- Never modify `data/mpl-val`, the first 150 of `data/plotly-v1`, `../corpus/`, `../examples/real/`, or the metric definitions in `metrics.py`. If a metric is misleading, say so in your report and add a new one beside it.
- Never train on them either. New synthetic data uses seeds at or above your team's seed base (in your assignment); `mpl-val` is seeds 9,000,000 to 9,000,999.
- Report before/after on the full standard commands above (200 / 150 charts), from the same checkpoint for "before" (`runs/v3/best.pt` unless your change is a new network).
- `--limit 60` runs are fine while iterating; the report needs the full runs.
- A gain on your probe set that does not show on the scoreboard is a finding, not a win; a gain on the scoreboard that costs a regression elsewhere must be reported with the regression.

## Rules of the machine

The machine is shared with other people's jobs and with nine other agents.
16 cores, 47 GB RAM, one RTX 3080 with 16 GB, of which other processes hold several GB.

- Work only in your team's worktree (the path is in your assignment). Never edit, build, or run anything in `/home/drd/PROJECT/CLAUDE/PLOT2DATA` itself; it is the main checkout and the baseline.
- Run everything heavy under `nice -n 19`, with `OMP_NUM_THREADS=2`. Generators: at most 3 workers. Training: `--workers 6`.
- GPU inference (evaluation) may run at any time, one process per agent at a time.
- GPU training is serialised through a lock: `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock nice -n 19 python -m p2d.train ...`. You will wait for the lock while another team trains; plan for it. Keep trainings short: fine-tune from `runs/v3/best.pt` with `--init`, 2,000 to 4,000 iterations (about 30 to 60 minutes each), `--eval-every 1000`. A training that needs the full 16,000 iterations must be justified in your notes and started only once.
- Name runs `runs/tN-<what>` and datasets `data/tN-<what>` (N is your team number). `runs/` and `data/` are shared directories, so a wrong name overwrites someone else's work.
- `pkill -f` and `pgrep -f` match their own shell's command line: use a `[p]attern` and never name the target elsewhere in the same command.
- Commit to your team branch as you go (`git add -A && git commit`), small commits with plain messages, no co-author lines of any kind. Do not push; the judge merges.
- `python -m pytest` in `ml/` must pass on your branch at the end; add tests for what you build.
- Web research is allowed and encouraged (WebSearch / WebFetch): papers, library documentation, other chart-extraction systems (ChartOCR, ChartDete, DePlot, UniChart, Pix2Struct, LineFormer, the ICDAR/ICPR CHART-Infographics competitions, WebPlotDigitizer, Engauge).

## The pair

Each team is two agents on one worktree and one branch.

**The brainstormer** owns the idea and the implementation.
It reads the design and the code, researches, lists candidate improvements for the team's area with a guess of the gain of each, picks the one or two with the biggest expected impact on the scoreboard, implements them, measures, iterates, and writes the report.
It may ignore every weakness but one if it has a real way around that one.
It is allowed to work from assumptions about what the failures are, and should ask the curator to check them.

**The curator** owns the evidence.
It finds the failing cases for the team's area in the standard sets (overlays, per-chart rows, the worst charts), works out concretely what makes them hard (which pixels, which labels, which structure), builds a probe set of synthetic charts with ground truth that provoke exactly that failure reliably (new generator variants or hand-written matplotlib / Plotly scripts; generated with the team's seed base), measures the baseline on it, and tells the brainstormer, in concrete terms and early, what the challenge really is.
It generates images on request, tests the brainstormer's hypotheses, re-measures the brainstormer's changes on the probe set, and keeps `CASES.md` current.

Both should converge quickly (within the first hour) on what the team is going after, then feed each other: the curator's diagnoses shape the idea, the brainstormer's hypotheses direct the curator's experiments.

How to talk to each other:

- `SendMessage` to your partner's agent id. The judge (the main session) sends each of you the partner's id right after you start; until it arrives, use the mailbox.
- The mailbox, always: `ml/teams/tN/mail/to-brainstormer.md` and `ml/teams/tN/mail/to-curator.md`. Append a dated entry (`## <time> from <role>`) with what you found, what you want, and paths. Read your own file at the start of every work step; the other agent cannot interrupt you, so checking is on you.
- Long things (tables, lists of charts, scripts) go in files under `ml/teams/tN/` or `ml/out/`, with the path in the message.

## Deliverables, in your team's directory `ml/teams/tN/`

- `NOTES.md`: a running log, dated entries, what you tried and what it did. Both agents write to it.
- `CASES.md` (curator): the failure catalogue: for each kind of failure, example chart ids and paths to overlays, the concrete diagnosis, the probe set that reproduces it, and the baseline numbers on it.
- `REPORT.md` (brainstormer, with the curator's sections): the submission. Structure:
  1. **Claim**: one paragraph: what changed and the measured gain, with the numbers.
  2. **Scoreboard**: before/after tables on the standard commands (and the probe set).
  3. **Diagnosis**: what the failures actually are, from `CASES.md`.
  4. **Ideas considered**: the ranked list with expected gains, and why this one.
  5. **Implementation**: files, how it works, cost (inference time, model size, training needed).
  6. **Generality and regressions**: what else moved, on every standard set.
  7. **What did not work**, with numbers; negative results are wanted.
  8. **Next steps**: what you would do with another day.
- The code on your branch, tests passing, committed.
- The probe set under `data/tN-...` and the generator for it on the branch.

Aim to have a first `REPORT.md` with measured numbers within about four hours of wall time, then keep improving and update it; the judge reads the report when it stops changing.
An implemented, measured gain beats a larger idea on paper.
Keep the report honest: the judge will re-run your commands.

## Judging

The judge integrates the submissions that move the scoreboard the most, possibly several together if they combine.
In order:

1. Measured improvement on the standard scoreboard, weighted as above; accuracy over speed, but a dramatic speed-up with no loss also counts.
2. Generality: the gain holds across the matplotlib, Plotly, Chart.js and real sets, not only the probe set.
3. No unreported regressions.
4. Honesty and clarity of the report.
5. Only then simplicity of the implementation.

## Seeds of ideas (from the project owner; use, ignore, or improve)

- Transformations of the image under which the data becomes regular and everything else becomes irregular, or the reverse, before any network sees it: colour and saturation (chart furniture is almost always achromatic, data almost always coloured), paper-versus-ink distances, sharpening, Hough-like or log-polar spaces, exploiting that the axes are exactly perpendicular and the gridlines exactly equally spaced.
- An early categorisation or routing step (what kind of chart, which renderer, where the plot panel is) that makes the later stages' job narrower.
- Breaking the image up: tiles at native resolution instead of one down-scaled canvas, a crop per series, a crop per axis.
- Chaining: one model turns raw pixels into features a second model or an explicit algorithm can use well; siphoning part of the problem off to an explicit computation that is exact where the network is only approximate (and the reverse).
- Several hypotheses carried forward and resolved by a global consistency check at the end (the tick labels on an axis form a progression; a series is a function of x; the frame, ticks and gridlines agree on one affine map).
- Multiple hypotheses of the same thing from different sources (network at two scales, flipped input, the classical engine), fused.
