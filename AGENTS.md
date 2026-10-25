# Project agent memory

plot2data-ml reads the numbers back out of an image of a chart, with a network trained on synthetic charts doing the perception.
It is its own lineage, split from `mlfisch3/plot2data` (the classical engine) and never merged back into it.

## Layout

- `ml/` - the learned pipeline in Python: synthetic data, PlotNet, decoding, tick reader, calibration, evaluation. `ml/README.md` is the design; `ml/RESULTS.md` the measured numbers.
- `src/`, `index.html` - the browser app inherited from the classical project (calibration markers, the three panels, CSV/XLSX export). It still runs the classical engine in `src/engine/`; the plan is to run the exported ONNX models in it via onnxruntime-web.
- `src/engine/`, `corpus/`, `ACCURACY.md`, `tools/` - the classical engine and its Chart.js corpus, kept as the baseline. `tools/run-classical.ts` runs it over any directory of charts for `ml/p2d/score_classical.py`.
- `android/`, `ANDROID.md` - the inherited WebView shell. Desktop comes first; its CI job runs on demand only, and its updater points at this repo.
- `docs/classical-engine-notes.md` - the classical engine's development notes: background, not rules.

## Running the ML side

The venv is `.venv/` at the repo root (`uv`, Python 3.12, torch with CUDA). From `ml/`:
`python -m pytest`, then the commands in `ml/README.md`. Data and runs live in `ml/data/` and `ml/runs/`, both ignored.

## Things that matter

- **Ground truth is exact or it is useless.** Pixel coordinates follow one convention everywhere in `ml/`: the centre of pixel column i is x = i. Targets are rasterised from vectors after the geometric augmentation, never warped as images. Check any generator change by overlaying the recorded geometry on the render (`out/viz`) before training on it.
- **Two errors, not one.** Report RMS over columns and error at turning points separately, and split "all" from "simple" charts (at most 3 series, fewer points than pixel columns): the validation set is deliberately harsh, and an average over it says little about a typical screenshot.
- **A marker series returns one point per drawn marker; names read off a chart never reach a number.** Both rules carry over from the classical project.
- **The machine is shared.** Other processes hold several cores; data loading, generation and evaluation compete with training for CPU, and two trainings on one GPU slow each other badly. Run one GPU job at a time, keep generators at `nice 19`, and set `OMP_NUM_THREADS=1` in workers.
- **`pkill -f` / `pgrep -f` match their own shell's command line.** Use a `[x]`-style pattern (`pgrep -f "[p]2d.train"`) and never put the target's name elsewhere in the same command.
