# Round 4: benchmark expansion to 110 real-chart screenshots

Goal: grow `data/t5-real` (30) to 100+ published charts with ground truth so future rounds measure against a surface big enough to surface regressions early.

Result: `data/t5-real-ext` with 80 new charts, `data/t5-real-100` (combined, 110 charts, 237 series) as the new scoreboard set.

## Chart inventory

New charts live in `ml/data/t5-real-ext/`, one triple per chart: the publisher PNG, the data file (`<id>.data.csv`, verbatim where fetched, synthesised columns where rendered here), and `<id>.json` metadata (source URL, kind, truth where synthesised).

| source | kind | n  | one-line notes |
| ------ | ---- | -- | -------------- |
| FRED | `fred` | 30 | St. Louis Fed server-rendered PNGs: UNRATE/CPI/GDP/payrolls/yields/oil/NASDAQ/VIX/housing/credit cards, varied widths, dark theme, log axes, line-weight variants, multi-series (DGS10+DGS2, GDP+GDPC1, CPI+food, unemployment by race). |
| OWID | `owid` | 20 | Our World in Data grapher: co-emissions, death/birth/fertility rates, urban share, GDP log, cumulative CO2, GHG, electricity mix, renewables, maternal mortality, literacy. |
| NASA GISS | `giss` | 5  | graphs_v4 fixed PNG+CSV pairs: U.S. temp anomaly (two lines), hemispheric change (14 cols), land-only, seasonal cycle (dense), 3 latitude bands. |
| NOAA GML | `noaa`, `noaa2`, `noaa-growth` | 6  | CH4/N2O/SF6 monthly + trend, CO2 MLO trend, CH4/N2O annual growth. |
| World Bank | `inline` | 11 | Fetched via WB API, rendered here: USA GDP, top-5 GDP, population by country, inflation, life expectancy EU-5, forest share. Multi-series with markers, log scale, thin/thick lines. |
| BLS | `inline` | 8  | Fetched via BLS v2 API: unemployment rate (headline, women 20+, teens), labor force participation, CPI-U/food/energy, nonfarm payrolls. |

New ground-truth kinds added to `p2d.eval_t5real.load_truth`:
- `noaa2` for the `year,month,decimal,average,...,trend,...` schema (CH4/N2O/SF6 monthly).
- `noaa-annual`, `noaa-growth` for the annual mean / annual increase CSVs.
- `inline` for synthesised entries where `<id>.json` carries the `truth` array directly (name, x, y).

The classical t5-real loader still fetches to `data/t5-real/` through `teams/t5-robust/tools/fetch_real.py`; its 30 charts are untouched.

## Fetchers

- `ml/teams/round4-benchmark/tools/fetch_real_ext.py` - manifest + fetcher for the 61 publisher-rendered charts (FRED, OWID, GISS, NOAA). Same contract as `fetch_real.py`: writes `<id>.png`, `<id>.data.csv`, `<id>.json`. 7 initial misses on wrong NOAA/GISS URLs; retried with corrected paths.
- `ml/teams/round4-benchmark/tools/synth_real.py` - for sources that do not publish a canonical PNG for a convenient query (World Bank, BLS). Pulls the data via the public API, renders a chart with matplotlib in a varied style, embeds the plotted (x,y) tuples as GT.
- `ml/teams/round4-benchmark/tools/validate_gt.py` - iterates a `t5-real` directory, calls `load_truth` on each entry, flags unreadable PNGs, empty series, duplicated or unsorted x. 0 issues on the 80 new charts.
- `ml/teams/round4-benchmark/tools/scoreboard.py` - thin wrapper around `p2d.eval_t5real` that also prints a per-source table.

## Combined scoreboard (`data/t5-real-100`, 110 charts, 237 series)

Checkpoint: `runs/t5r2-clutter/best.pt` + OCR `runs/ocr1/best.pt` (current `main`).

### Aggregate

| metric                 | TTA shift | no TTA |
| ---------------------- | --------: | -----: |
| series                 |       237 |    237 |
| found (cov >= 80%)     |       63% |    64% |
| median rms             |     0.36% |  0.57% |
| median rms of found    |     0.28% |  0.54% |
| within 1%              |       48% |    45% |
| within 0.5%            |       41% |    38% |
| failed                 |        52 |     51 |

### Per source (TTA shift)

| source | N series | <0.5% | <1% | failed | median rms |
| ------ | -------: | ----: | --: | -----: | ---------: |
| bls    |        8 |   62% | 100% |    0% |      0.29% |
| fred   |       53 |   11% |  23% |   19% |      1.92% |
| giss   |       35 |    6% |   6% |   51% |      4.66% |
| noaa   |       12 |   67% |  75% |    0% |      0.06% |
| owid   |       96 |   51% |  56% |   24% |      0.19% |
| wb     |       33 |   82% |  85% |    3% |      0.15% |

### Original 30 vs new 80 (TTA shift)

| set   | N series | <0.5% | <1% | failed | median rms |
| ----- | -------: | ----: | --: | -----: | ---------: |
| orig  |       60 |   37% |  42% |   28% |      0.48% |
| ext   |      177 |   42% |  50% |   20% |      0.34% |

The ext set is slightly easier on average because the synthesised `bls` and `wb` charts are near-perfect; the publisher-rendered `fred` and `giss` groups within ext behave worse than orig.

## Failure patterns on the new benchmark

Patterns new in Round 4, not visible on the 30-chart orig set, from the TTA shift log at `teams/round4-benchmark/results/t5r100-tta-shift.log`:

1. **FRED y-axis fails to calibrate**: `fred-dgs10-daily`, `-dgs2-2010`, `-dgs30-full`, `-drccl-cards`, `-fedfunds-small`, `-mortgage-tiny`, `-oil-full`, `-sp500`, `-sp500-5y`, `-sp500-small`. FRED labels y-axis values with light grey text on light grey gridlines, with trailing zeros stripped. The current OCR+calibration gives up with "y axis: could not calibrate from the tick labels". 10 of 30 FRED charts fail outright this way.
2. **"Only two ticks read: linear/log decided from the labels"**: FRED small-font charts (`-dexuseu`, `-dpoilbrent`, `-houst-thick`, `-sp500` family). Two-tick calibration lets the scale pass, but residual RMS is 2 to 400% depending on how close the two reads were to the true tick positions.
3. **OWID "y axis: could not calibrate"**: `owid-annual-co2-log`, `-fertility-rate`, `-life-expectancy-4`, `-life-expectancy-gbr`, `-life-expectancy-many`, `-energy-per-capita`, `-population-world`. OWID's end-labels (country name at line end) seem to be eaten by OCR as y-tick labels and poison the calibration.
4. **Y-axis scale factor misread**: `owid-military`, `-cumulative-co2`, `-co-emissions-per-capita`, `-co2-per-capita`, `owid-energy-mix` all show ~50 to 120% RMS. OWID chart labels include "1 billion", "10 million" scale hints and SI-prefix suffixes that the current scale-factor reader turns into the wrong decade.
5. **FRED `1e3` / `1e4` units mis-scaled**: `fred-dgs10-dgs2` -> 32,752% RMS. "y axis: values scaled by the printed '1e3'" fired but was applied in the wrong direction (division instead of multiplication, or applied twice).
6. **GISS multi-column CSV, few lines drawn**: `giss-hemispheric` (14 cols, 4 drawn), `giss-lat-bands` (14 cols, 3 drawn). Scorer counts the 10 or 11 non-drawn columns as `nan%` failures. GT quality issue: the CSV is used verbatim but the chart draws a subset. Fix is either per-chart `cols` whitelist in the metadata, or an unmatched-is-not-failure change to `score_chart`.
7. **giss-seasonal dense overplot**: 143 monthly curves on one axes, extractor finds 53 fragments, scorer collapses to 0% coverage. Legitimately out of scope for the current pipeline.
8. **NOAA chart window vs CSV window**: `noaa-ch4-monthly`, `-n2o-monthly`, `-sf6-monthly` all show cov 15 to 17%. The chart PNG covers the last 10 years, the CSV serves the full record. Scorer's low coverage pulls these out of the "found" bucket; add a per-entry `window` option in the metadata to clip the CSV to what the png shows.

Patterns already present on orig and worsened on ext:
- Right-side y-axis labels (several FRED configs). The pipeline reads them but calibrates on them inconsistently.
- Multi-series charts with crossing lines (fred-cpi-cpifood, fred-dgs10-dgs2, wb-gdp-5): series assignment picks a far-away match for the second series when the two are close in colour family.

## Pointers for Round 5

Highest-leverage targets, in rough order of their fail count on the expanded set:

- **FRED y-axis calibration failure (10 charts, 10 series lost)**. Dedicated train subset of FRED-style labels. The OCR reads "4.00", "4.50" fine but calibration rejects them because the printed scale is "4.0", "4.5" and the delta between reads is interpreted as 0.5 ticks of 0.01, triggering the disagreement filter.
- **OWID end-labels poisoning y calibration (7 charts, 20 series lost)**. Either suppress end-labels in the OCR mask, or ignore any OCR text whose x position is within K pixels of the plotted line's rightmost point.
- **Scale-factor units in OWID titles (5 charts, high-RMS not failures)**. The current parser catches `1e1` but misses "$ billion", "million people", "tonnes" etc.
- **GT quality for multi-column GISS CSVs**. Add a `cols` whitelist to the GISS entries. Alternatively relax `score_chart` to not penalise unmatched truth series.
- **NOAA chart-window vs CSV-window mismatch**. Add a `window: {t0, t1}` field to NOAA entries, clip truth at load time.

## Reproducing

Prerequisites: venv (`uv`, Python 3.12, torch+cuda) in `.venv/` at the repo root; `runs/t5r2-clutter/best.pt` and `runs/ocr1/best.pt` present.

```
cd ml
source ../../PLOT2DATA/.venv/bin/activate

# fetch publisher-rendered charts (needs net)
python teams/round4-benchmark/tools/fetch_real_ext.py --out data/t5-real-ext

# synthesise WB and BLS charts (needs net)
python teams/round4-benchmark/tools/synth_real.py --out data/t5-real-ext

# combined view
mkdir -p data/t5-real-100
for f in data/t5-real/* data/t5-real-ext/*; do
  ln -sf "../$(basename $(dirname $f))/$(basename $f)" "data/t5-real-100/$(basename $f)"
done

# score
OMP_NUM_THREADS=1 flock /tmp/gpu.lock python -m p2d.eval_t5real \
    --ckpt runs/t5r2-clutter/best.pt --ocr runs/ocr1/best.pt \
    --data data/t5-real-100 --tta shift \
    --json teams/round4-benchmark/results/t5r100-tta-shift.json
```

## Branch

`round4/benchmark` from `main @1832ce4`.
