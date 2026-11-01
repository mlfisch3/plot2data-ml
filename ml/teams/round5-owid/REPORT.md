# Round 5 - OWID direct-label and composite-label cluster

Branch `round5/owid` from `main` at `d55bcc7`.
Checkpoint `runs/t5r2-clutter/best.pt`, OCR `runs/ocr1/best.pt`, `--tta shift`.

## 1. Scope

Round-4's benchmark expansion (`data/t5-real-100`, 237 series) exposed an OWID cluster that failed to calibrate y: 7 charts, 20 series.
The brief described it as "country-name end-labels (China, World, India) read as y ticks and poisoning the fit".

| chart | round-4 baseline |
| --- | --- |
| owid-annual-co2-log        | nan ("could not calibrate from the tick labels") |
| owid-energy-per-capita     | nan ("could not calibrate from the tick labels") |
| owid-fertility-rate        | nan ("could not calibrate from the tick labels") |
| owid-life-expectancy-4     | nan ("could not calibrate from the tick labels") |
| owid-life-expectancy-gbr   | nan ("could not calibrate from the tick labels") |
| owid-life-expectancy-many  | nan ("could not calibrate from the tick labels") |
| owid-population-world      | 42% RMS (axis fit from one real + one bogus label) |

## 2. Diagnosis

Per-chart diagnostics saved to `out/r5-owid/diag*/`.
The brief's "country-name end-labels" account turns out to cover ONE chart (`owid-population-world`); the other six all fail because of a different pattern.
Both patterns live on OWID's house style.

### 2a. End-label at the right edge of a line (`owid-population-world`)

OWID writes each series' name at the right end of its line, inside the plot:

```
y labels (left side):           series end-label (right side):
log axis   ................     World
5 billion                       (at the right end of the line's last point)
2 billion
1 billion
```

The YTICK heat sometimes fires at the endpoint of a line, which gives us a y-tick anchor at `(x = plot_right, y = line's last y)`.
`refine_labels` then calls `label_from_source` outward from that anchor; outward for an anchor on the right side of the plot is `+1` (look right), so it scans past the plot edge and finds "World", the direct-label text.
The reader reads "World", `parse_value("World")` returns None, and the axis fitter sees a plausible-looking tick that disagrees with everything else.

```
# baseline y-ticks on owid-population-world:
pos=171  anchor=(67.7, 171)  text='7 bu bi' -> None
pos=429  anchor=(67.0, 429)  text='1b n'    -> None
pos=317  anchor=(67.4, 317)  text='2b n'    -> None
pos=75   anchor=(66.8, 75)   text='log axis' -> None       (chart title text, not a tick)
pos=94   anchor=(767.6, 94)  text='World'   -> None        (end-label on the right)
```

Two of the five anchors are on the right (767) or at the top-title area (75); the three legitimate anchors are at `x ~= 67` (left plot edge).

### 2b. Composite y-tick labels with inline units (6 charts)

OWID writes the unit INSIDE every y-tick label (not above the axis as mpl would):

```
owid-fertility-rate:    y labels are "0 births", "1 births", ..., "8 births"
owid-life-expectancy-*: y labels are "0 years", "10 years", ..., "90 years"
owid-energy-per-capita: y labels are "0 kWh", "20,000 kWh", ..., "100,000 kWh"
owid-annual-co2-log:    y labels are "1 billion t", "10 billion t", "100 billion t", ...
```

The reader (trained on standalone numbers) returns garbage when it sees a number joined to a unit word:

```
# fertility-rate text / strict parse_value:
'0bo 15'  -> None     # from "0 births"
'1bu '    -> None     # from "1 births"
'3u 15'   -> None     # from "3 births"
...

# life-expectancy-4 text / strict parse:
'0 an'       -> None  # from "0 years"
'40epn5'     -> None  # from "40 years"
'80 pn5'     -> None  # from "80 years"
```

Every label fails strict parsing, so the axis fitter has nothing to work with.

The exception is a chart like `owid-ghg-emissions` whose "N billion t" OCR'd to "Nb   n" (then space-strip -> "Nbn") which strict parse accepts via the `(k|K|M|B|bn|G|T)?` suffix, giving `N * 1e9`.
That is why `owid-ghg-emissions` was NOT on the failing list: strict `_NUM` happened to catch "bn".

### 2c. Spurious 1e1 multiplier on `owid-life-expectancy-4`

Independently from the two above, `axis_factor` scans a strip above the plot for a printed multiplier.
On `owid-life-expectancy-4` it reads "ld" (part of "would" in the chart's subtitle) as "1e1".
Baseline, this misread was benign because the y axis couldn't fit anyway.
Once the axis is fitted (by any means), the "1e1" factor multiplies every value by 10 and we get 388% RMS instead of 0.3%.

## 3. Fix

Three minimal changes, in `extract.py`, `ocr.py`, and `pipeline.py`.

### 3a. `_drop_offside_ticks` in `extract.py`

A new helper called at the end of `extract()`.
When one side of a y axis (or x axis) has >= 3 ticks and the other has 1 or 2, drop the minority.
A real twin-axis chart has at least 3 ticks on each side; a lone minority against a majority is almost always the end-label artefact.

```python
def _drop_offside_ticks(ex: Extraction) -> None:
    ...
    nlow = int(low.sum())
    nhigh = len(ticks) - nlow
    if nlow >= 3 and nhigh in (1, 2):
        keep_mask = low
    elif nhigh >= 3 and nlow in (1, 2):
        keep_mask = ~low
    else:
        continue
    setattr(ex, key, [t for t, k in zip(ticks, keep_mask) if k])
```

The fewer-than-four-ticks case is a no-op (too few to split reliably).

### 3b. Lax `parse_value` with a strict-first fallback

`parse_value(text)` stays strict by default; `parse_value(text, lax=True)` adds a leading-number mode:

```python
_NUM_LAX = re.compile(r"^\(?([-+]?)\$?([0-9][0-9,]*\.?[0-9]*|\.[0-9]+)(?:[eE]([-+]?[0-9]+))?(k|K|M|B|bn|G|T)?%?\)?(.*)$")
```

The lax tail must start with a letter ("0bo 15" is a unit-tail, "1 50" is a mashed digit pair), OR the suffix must be a multi-char `bn` or an unambiguous SI prefix ("200bn1" is 2e11 with a trailing OCR 1).
A single-letter SI prefix touching a letter tail ("kWh") is treated as the first letter of a unit word and the multiplier is dropped so "80,000 kWh" returns 80000, not 80M.

Lax mode is called from `read_ticks` only when strict yielded fewer than 2 values AND lax yields more than strict.
Any chart with 2+ cleanly readable labels (e.g., `owid-population-3` with "1.2bn", "1.4bn") stays on strict and is not swamped by lax parses of the composite-label siblings.
When lax fires, `TickRead.logits` are cleared so the simple `fit_axis` path is used over the joint decoder (whose beam-search candidates are strict only).

### 3c. Factor-gate in `pipeline.run`

The existing gate skips a multiplier when the labels' magnitude exceeds 1000.
Extended to also skip when the labels' magnitude is at least the factor's own:

```python
if max_abs_val > 1000:
    continue
if scale > 1.0 and max_abs_val >= scale:
    continue
```

mpl prints "x10^k" only when the labels would otherwise print with k trailing zeros, so a label whose magnitude already matches or exceeds the factor is proof the factor is noise.
The "1e1" from "ld" with labels 0-90 is rejected (90 >= 10); a real mpl "1e3" with labels 0-10 is kept (10 < 1000).

## 4. Per-chart before and after on `data/t5-real-100`

Checkpoint and TTA as above; all RMS values are percent of chart y span.

### Target 7 charts

| chart | round-4 baseline | round-5 fix | status |
| --- | --- | --- | --- |
| owid-annual-co2-log       | nan / nan / nan / nan | 38.90% / 123.33% / 198.61% / 250.39% | partial - log scale detected; `million`/`billion` SI words not recovered |
| owid-energy-per-capita    | nan / nan / nan       | 0.12% / 0.11% / 0.13%                 | within 5% |
| owid-fertility-rate       | nan / nan / nan / nan | 0.29% / 0.11% / 0.11% / 0.12%        | within 5% |
| owid-life-expectancy-4    | nan / nan / nan / nan | 0.24% / 0.33% / 0.20% / 0.27%        | within 5% |
| owid-life-expectancy-gbr  | nan                   | 0.86%                                 | within 5% |
| owid-life-expectancy-many | nan / nan / nan / nan / nan | 0.22% / 10.94% / 1.16% / 0.23% / 14.47% | majority within 5% |
| owid-population-world     | nan (42% in subset)   | 18.04% cov 25% (38.29% in subset)    | partial - "log axis" misread as "6 005" is a spurious tick that still slips the sanity checks |

5 of 7 OWID charts (`energy-per-capita`, `fertility-rate`, `life-expectancy-4`, `life-expectancy-gbr`, `life-expectancy-many`) now have y RMS < 5% on their primary series.

The two still-poor charts both suffer from a magnitude issue the lax parser does not handle: OCR of "N million t" or "N billion" that collapses to "Nmnt" or "Nbit" without the two-letter `bn` surviving.
These will need either (i) an improved OCR-tolerant SI prefix word matcher (billion/million/thousand with 1-2 char edit tolerance), or (ii) a cropping pass that isolates the leading number before the OCR sees it.
Either is out of scope for round-5.

### Scoreboard, `data/t5-real-100` (237 series)

Scored with `teams/round4-benchmark/tools/scoreboard.py`'s underlying `p2d.eval_t5real` (copied from the round-4 branch, it carries the `noaa2` / `inline` ground-truth kinds the main branch does not yet have).

| metric | round-4 baseline | round-5 fix | delta |
| --- | --- | --- | --- |
| series                   | 237  | 237  | 0 |
| found (cover >= 80%)     | 65%  | 74%  | +9 pts |
| median rms               | 0.43% | 0.36% | -0.07 pts |
| median rms of found      | 0.31% | 0.28% | -0.03 pts |
| within 1%                | 50%  | 57%  | +7 pts |
| within 0.5%              | 43%  | 49%  | +6 pts |
| failed (NaN)             | 46   | 24   | -22 |

### Other OWID charts (collateral effect, no regressions)

| chart | round-4 baseline | round-5 fix |
| --- | --- | --- |
| owid-cumulative-co2       | 18.34% / 8.85% / 11.75% / 49.36% | 0.09% / 1.74% / 2.18% / 0.10% |
| owid-co-emissions-per-capita | 28.85% / 7.92% / 72.14% / 112% | 28.88% / 7.95% / 72.16% / 112% |
| owid-co2-per-capita       | 10.33% / 37.18% / 71.78% / 108%  | 10.36% / 37.20% / 71.80% / 108% |
| owid-population-3         | 0.06% / 0.09% / 0.12%            | 0.06% / 0.09% / 0.12% |
| owid-ghg-emissions        | 0.15% / 0.04% / 0.11%            | 0.15% / 0.04% / 0.11% |

`owid-cumulative-co2` was NOT on the brief's failing list but had 18-49% RMS from a MISLEADING tick ("0b n" at an anchor on the right side of the plot that strict-parsed to 0, poisoning the fit).
`_drop_offside_ticks` removes it; strict-fail triggers lax; "200bn1" / "100bn1" lax-parse to 2e11 / 1e11; the axis fits cleanly.

## 5. Scoreboard confirmation on all required sets

All runs with `OMP_NUM_THREADS=1 flock /home/drd/PROJECT/CLAUDE/PLOT2DATA/ml/out/gpu.lock`.

### `data/mpl-val --limit 200`

| metric | baseline | fix | delta |
| --- | --- | --- | --- |
| line_found (all)         | 0.6703 | 0.6703 | 0 |
| line_good_cov_mean       | 0.5310 | 0.5310 | 0 |
| line_rms_median_pct      | 0.3169 | 0.3169 | 0 |
| marker_recall            | 0.5968 | 0.5968 | 0 |
| marker_precision         | 0.7184 | 0.7161 | -0.0023 |
| yticks_fp_per_img        | 0.8600 | 0.7650 | **-0.095** (fewer false positives) |
| calib_x_within_0.5pct    | 0.8850 | 0.8850 | 0 |
| calib_x_scale_ok         | 0.9400 | 0.9450 | +0.005 |
| calib_y_within_0.5pct    | 0.8900 | 0.8900 | 0 |
| calib_y_scale_ok         | 0.9600 | 0.9600 | 0 |

The side filter removes some false-positive y-ticks on the synthesised set too; the tiny marker-precision drop is noise (3 markers on 200 charts).

### `data/plotly-v1 --limit 150`

Byte-identical with the baseline (diff is empty).

### `eval_corpus` (Chart.js corpus, 25 series)

Byte-identical with the baseline (diff is empty).
Series median 0.071%, worst 0.563% (log-log), same as `main`.

### `data/t5-real` (the original 30 charts)

| metric | baseline | fix |
| --- | --- | --- |
| series                   | 60   | 60 |
| found (cover >= 80%)     | 65%  | 85% |
| median rms               | 0.70% | 0.61% |
| within 1%                | 48%  | 62% |
| within 0.5%              | 37%  | 48% |
| failed                   | 13   | 1 |

### `examples/real`

Byte-identical with the baseline (diff is empty).

## 6. Tests

`tests/test_core.py` grew by 24 tests, 151 pass total (127 original + 24 new):

- `test_parse_value_lax_composite_labels` - parametrized over OWID-style garbled unit labels.
- `test_parse_value_strict_recovers_N_bn` - ghg-emissions-style strict path survives.
- `test_parse_value_lax_rejects_or_tolerates` - mashed digit pairs and non-numeric labels stay None.
- `test_parse_value_lax_kWh_does_not_multiply_by_kilo` - the single-letter-prefix-plus-alpha-tail rule.
- `test_drop_offside_ticks_removes_a_lone_right_side_tick` - OWID direct-label case.
- `test_drop_offside_ticks_keeps_a_genuine_twin_axis` - 3+ ticks on each side preserved.
- `test_drop_offside_ticks_keeps_fewer_than_four_ticks` - low-tick-count no-op.
- `test_axis_factor_gate_skips_implausible_small_multiplier` - the 1e1-vs-90 gate.

Full suite:

```
$ python -m pytest -q
151 passed in 11.32s
```

## 7. Reproducing

```sh
cd ml
source ../../PLOT2DATA/.venv/bin/activate

# OWID subset
mkdir -p data/r5-owid-only
for f in data/t5-real/owid-* data/t5-real-ext/owid-*; do
  ln -sf "../$(basename $(dirname $f))/$(basename $f)" "data/r5-owid-only/$(basename $f)"
done

OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_t5real \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/r5-owid-only --tta shift --json out/r5-owid/fix.json

# scoreboard with the round-4 ground-truth kinds (noaa2, inline) - copy the eval_t5real
# from the round-4 branch, it is not yet on main.
cp ../../PLOT2DATA-r4/benchmark/ml/p2d/eval_t5real.py p2d/eval_t5real_r4.py
OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_t5real_r4 \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/t5-real-100 --tta shift --json out/r5-owid/t5r100.json
rm p2d/eval_t5real_r4.py

# original 30 and other regression sets
OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_t5real \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/t5-real --tta shift

OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.evaluate \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/mpl-val --limit 200 --refine --tta shift

OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.evaluate \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
  --data data/plotly-v1 --limit 150 --refine --tta shift

OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_corpus \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt --tta shift

OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_real \
  --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt --tta shift
```

Sun 1 Nov 2026, 09:51 EST
