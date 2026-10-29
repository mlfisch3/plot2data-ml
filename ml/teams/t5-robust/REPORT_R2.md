# t5-robust R2 V3: clutter-aware training

Round-2 fine-tune on top of round-1's integrated V2 checkpoint (`runs/t5-chartjs/best.pt`).
Angle A: a measured regression in V2 - clutter probe +35% rms and +10 px frame_err_median vs V1 - was traced to the sem head confusing outside-chart text and ink with DATA/GRID/TICK_LABEL. V3 adds synthetic cluttered-page samples (chart embedded in a toolbar/sidebar/text page, chart ink keeps its real sem, surrounding stays BG) to the training mix.

## 1. Verdict

TBD after measurement.

## 2. Training

- Branch: `team/t5-robust-r2`
- Init from `runs/t5-chartjs/best.pt` (V2, round-1 integrated base).
- Added data: `data/t5r2-clutter` (3000 mpl, seeds 15,100,000+) and `data/t5r2-clutter-plotly` (1000 plotly, seeds 15,200,000+), both from `probe_t5.make(..., factor='clutter', ...)`. 4000 clutter samples total, 5.6% of a 71,385-sample mix.
- Hyperparams: 3000 iters, batch 8, lr 3e-4 cosine (half of V2's 6e-4, chosen as a gentle fine-tune since the V2 ckpt is already well converged), workers 6, zoom 0.35, encoder resnet34.
- Script: `ml/out/t5r2/train-r2.sh`. Run folder `runs/t5r2-clutter/`. Checkpoint `runs/t5r2-clutter/best.pt`.
- Runtime remains native pass + `--tta shift`.

## 3. Scoreboard

Measured on `--tta shift` with `runs/t5r2-clutter/best.pt` + `runs/ocr1/best.pt`.
V2 numbers come from `REPORT_V2.md` sections 3.1-3.8; base from `v3/best.pt` on the frozen base tree.

### 3.1 Clutter probe (`data/t5-clutter`, 100 mpl charts in cluttered pages)

TBD.

### 3.2 Other image-factor probes (`data/t5-{blur,dark,half,up2x,jpeg50,jpeg30,skew1,dpr1,dpr2,dpr3}`)

TBD.

### 3.3 End-to-end, mpl-val 200, plotly-v1 150, chartjs-val 100

TBD.

### 3.4 Chart.js corpus (`eval_corpus`)

TBD.

### 3.5 Real-chart benchmarks (`data/t5-real`, 30 charts) and examples/real

TBD.

## 4. Verification commands

From `ml/`, with `../.venv/bin/activate`, through `flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`:

- `bash out/t5r2/eval-r2.sh runs/t5r2-clutter/best.pt r2`
- `python -m pytest tests/test_core.py` (expect 110 passed on `team/t5-robust-r2`)

## 5. Status

- Clutter dataset generated: TBD files in `data/t5r2-clutter`, TBD in `data/t5r2-clutter-plotly`.
- Training run `runs/t5r2-clutter/`: TBD iters.
- Measurement complete: TBD.
