# Team 1, "axis": calibration from the tick labels

Worktree: `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis`, branch `team/t1-axis`, seed base 11,000,000, run and data prefix `t1-`.

## Why this area

It is the single largest end-to-end loss.
With the true tick values supplied (`--oracle-ticks`) the pipeline finds about 81% of simple lines; with the labels read by the tick reader it finds 62%.
On the matplotlib validation set one axis in five or six misses 0.5% (`calib_x_within_0.5pct` 0.84, `calib_y_within_0.5pct` 0.79, v2), the scale (linear/log) is wrong on about 10% of axes, and an axis is not calibrated at all on 5 to 9%.
Tick recall drops from 95% (geometry) to 84% once a tick needs a readable label.
Every series on a chart is wrong when its axis is.

## Known failure modes

- Tick labels that are two pieces: a thin `1` lost from `10^3` (the real microprocessor chart reads `0^3`, `0^5`, `0^6`, `0^7`), minus signs, superscripts, `%` or unit suffixes dropped, the decimal point.
- Label-to-tick grouping (`extract.group_labels`): the nearest text component is not always the right one; labels of a crowded axis, rotated date labels, labels that sit between ticks (categorical/bar-style placement), multi-line labels.
- Multipliers and offsets printed at the end of an axis (`1e6`, `x10^3`, `+1.2e3`): read only when they stand apart; the Chart.js `offset-annotation` corpus case fails outright because its `1e6` touches the top label.
- Axes with only two readable labels (linear/log decided from the labels alone).
- The tick reader is 98.8% exact on crops of synthetic labels, but the crops it sees at test time come from the predicted label boxes, not the true ones.
- Date axes (`dates.py`): month names, `'21`, `Q1 2020`, quarter and week labels; dates only kick in when most labels are non-numeric.
- Axes with no tick marks and no gridlines: the learned label-to-tick offset is renderer specific (0.2% bias on `linear-single-nogrid`).

## Where to look first

`out/base/v3-e2e-ocr.txt` versus `out/base/v3-pixel.txt`; `p2d.eval_calib`; `evaluate --json` rows for the charts whose calibration is off; the overlays (`--viz`) draw the labels read.
`pipeline.read_ticks`, `pipeline.axis_factor`, `pipeline.as_dates`, `extract.group_labels`, `extract.label_boxes`, `ocr.crop`, `ocr.parse_value`, `calibrate.fit_axis`.

## Seeds of ideas (not a list to follow; beat it)

- Read each axis as a whole, not label by label: the printed values on one axis form an arithmetic (or geometric) progression with "nice" steps, so a joint decoding over the top-k readings of every label, scored by how well a single linear or log map explains them all, can fix a misread digit, a dropped minus sign, and decide linear versus log from two labels.
- A learned association: a per-pixel offset field from label ink to its tick, or an attention-style head, instead of nearest-along-the-axis.
- A stronger reader: more fonts, renderers, rotations, sub-pixel crops, superscripts; a reader that sees the whole axis strip at once and outputs the sequence of labels with their positions.
- A detector for the multiplier/offset text and for axis titles that contain units (`in millions`, `%`).
- Second opinions: run the reader on crops from the predicted boxes and from the sem mask components, keep the consistent one.
