# t1-axis: the failure catalogue for calibration from the tick labels

Curator's file. Baseline is `runs/v3/best.pt` with the tick reader `runs/ocr1/best.pt`, measured in the frozen
worktree `/home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base` (commit 6b313e9) unless a line says "live tree".
Every number below is from `teams/t1-axis/diag.py` (per-tick diagnosis) and `reclass.py` (ink-based grouping
classes); its outputs live in `out/t1/diag-<set>/` (`summary.txt`, `diag.json`, `<seed>.png` overlays of every
failing chart with the text read in blue beside each predicted label box and the true label box in green).
Contact sheets of axis strips: `out/t1/sheets/`.

## How the loss splits (mpl-val, 200 charts)

Calibration within 0.5% of full scale / scale (linear or log) right:

| | x | y |
| --- | --- | --- |
| pipeline | 0.845 / 0.910 | 0.765 / 0.890 |
| true text on the predicted ticks (reading and grouping perfect, detection as is) | 0.925 / 0.935 | 0.835 / 0.910 |
| true ticks and texts through `parse_value` + `as_dates` + `fit_axis` (fitter alone) | 0.985 / 0.985 | 0.910 / 0.945 |
| `--oracle-ticks`, the standard command | 0.975 / 0.975 | 0.915 / 0.915 |

Per axis, of the 200: y fails 47 times (err 25, no fit 12, scale 10), x 32 times (err 14, no fit 16, scale 2).
The true text on the predicted ticks would fix 16 of the 47 and 16 of the 32; the rest need other boxes, other
ticks, or another fitter.

## The classes

Counts are failing axes by first cause on mpl-val; the mechanism is what the overlays and the per-tick records show.
"Probe" names the style of `p2d/synth/probe_t1.py` that reproduces it; the probe numbers are in the table at the end.

### 1. Two-label log axes decided linear (y: 10 axes, 5% of charts)

Examples: 9000015 ('1e1', '1e2'), 9000027 ('1e4', '1e5'), 9000044 ('1e0', '1e1'), 9000106, 9000154, 9000068 and
9000070 ('0.1', '1'), 9000150 ('1', '10'), 9000198 ('100', '1,000'), 9000061 ('10,000', '100,000').
Overlays: `out/t1/diag-mpl/9000015.png`, `out/t1/diag-mpl/9000068.png`.
Mechanism: both labels are read exactly; with two ticks, linear and log both fit, and `calibrate.fit_axis` breaks the
tie with `looks_log = "^" in text or (powers of ten and ratio >= 100)`, so a pair of consecutive decades goes linear.
This is the whole gap between `--oracle-ticks` (0.915) and 1.0 on y, less three multiplier charts.
Fix: '1eK' is log notation like '^'; two labels that are exact powers of ten one decade apart are a log axis (a
linear axis labelled only at 1 and 10 would have step 9, not a nice step).
Probe: `two_log` (plain '10', '100', the '1e1' form, and '10^k'), against `two_lin` as the control.

### 2. Leading glyph lost from the label box (y: 12 axes, x: 3)

Examples: '-20'->'20' (9000046), '-50.0'->'50.0' (9000063, 9000162), '-100'->'100' (9000077), '-4e+01'->'4e+01'
(9000160), '-100.0%'->'100.0%' (9000008, canvas scale 2.0), '1100'->'100' (9000066), '1e3'->'e3' (9000147),
'1.0e+01'->'0e+01' (9000085), '1000000'->'000000' (9000136); '300'->'00', '450'->'50' (9000093, labels on the
right, scale 0.54), '30'->'0' (9000143, scale 0.43), '20'->'0' (9000004).
Overlays: `out/t1/diag-mpl/9000093.png`, `out/t1/diag-mpl/9000143.png`, `out/t1/diag-mpl/9000160.png`;
full-resolution crops `out/t1/crops/cut-pair.png`.
Two mechanisms: (a) `extract.group_labels` drops any piece under 0.3 x the median piece area of the axis as a
"speck"; a minus sign or a thin leading '1' that comes apart from the digits is exactly such a piece, at any scale.
(b) Below canvas scale 0.6 the first glyph next to the tick mark is taken by the axis class in the sem map and the
box starts about 3 px into the text: y labels at scale < 0.5 have ink outside the box on the left in 11% of cases
(8% by more than 2 px); x labels 2%.
Fix: no area-only speck rule inside the label row; snap the box to the ink on the source image; pad the crop on the
leading side. A reader-side correction cannot recover ink that is outside the crop.
Probe: `neg_small` (minus signs), `units` and `sci_e` (leading '1' and '$'), `crowded_y`, `tiny`.

### 3. Ticks found but given no label box (y: 125 ticks, x: 114; first cause in 6 y and 5 x axes)

120 of the 239 are labels under 5 canvas px tall: charts 1,200 to 1,760 px wide with 7 to 9 pt text at 60 to 100
dpi, placed on the 768 x 512 canvas at scale 0.42 to 0.58. Examples: 9000084, 9000158, 9000103, 9000017, 9000061,
9000195. Overlay: `out/t1/diag-mpl/9000158.png`, sheet `out/t1/sheets/y-unclaimed.png`.
Mechanism: the sem mask does not fire on 3 to 5 px text, or the component fails `label_boxes`'s h >= 6 and w >= 6.
The reader reads source-resolution crops and would read these labels; it never sees them.
Fix: find the boxes at source resolution (ink components beside each tick in the label band, with the sem
probability as a prior at a low threshold), or run the sem head on the axis strips at native resolution.
Probe: `crowded_y`, `tiny` (the probe charts are small, so the canvas scale is high; the mpl-val cases are big charts
with small text, which `crowded_y` at 420 to 900 px wide covers only partly).

### 4. Multiplier or offset text not applied (y: 6 axes, every chart that prints one)

Examples: 9000051 ('1e6'), 9000079 ('1e-5'), 9000117, 9000127, 9000169 ('1e6'), 9000153 ('1e-6'); errors 95% to
1e6% of full scale. Overlays: `out/t1/diag-mpl/9000079.png`, crops `out/t1/crops/mult-pair.png`.
Mechanism: in 9000079, 9000117 and 9000127 the printed text gets no tick-label component at all (7 to 9 px tall at
the top of the axis); in 9000051 the loose piece reads '1e' (its '6' cut), in 9000153 'e-6' (its '1' cut, class 2);
so `pipeline.axis_factor` never gets a readable piece. The Chart.js corpus case `offset-annotation` is the other
form: its '1e6' touches the top label '8' and is merged into that label's box.
Fix: look for the offset text explicitly at the axis ends at source resolution, split it from the top label when it
touches, read it with a strict grammar.
Probe: `mult_sci` ('1e6', 'x10^-6'), `offset` ('+1.925e6').

### 5. The wrong piece taken as the label (x: 10 axes, y: 5)

(a) Tick-mark slivers: the tick-label class bleeds onto the outer end of a tick mark (direction out, length >= 5
px); the sliver is 2 to 8 px, starts 1 to 3 px away from the axis line so `group_labels`'s "touches the axis" test
misses it, it is the nearest piece to the tick in L1, and the real label in the next row fails `same_row`, so the
label box is the sliver, read as '1', '0' or ''. Examples: 9000003 (all three x ticks read '1'), 9000012, 9000067
(eight x ticks), 9000090, 9000102, 9000124, 9000139, 9000166, 9000186, 9000074. Crop: `out/t1/crops/9000003-x.ov.png`.
(b) Corners: the first x tick takes the bottom y label ('-50' for 1970 in 9000121), or a y tick takes an x label
(9000037 '0.0004', 9000157, 9000161 '0e+00', 9000132 '1988').
Fix: a piece must lie on the label side of the axis line and its extent along the axis must contain the tick
position; choose pieces in the axis-wide label band rather than nearest in L1; drop slivers thinner than half the
band's glyph height.
Probe: `nogrid_noticks` is the control (no tick marks at all); the sliver case is in every probe style with tick
length 3.5 or 5 (40% of the probe charts).

### 6. Rotated x labels (x: 7 axes)

Examples: 9000067, 9000069, 9000082, 9000091, 9000100, 9000131, 9000189 (90 degrees: '100'->'10', '2006'->'50');
9000014 (45 degrees: pieces come apart, '872.25'->'5'). Sheet: `out/t1/sheets/x-rotated.png`.
Mechanism: the boxes are right; the reader reads a horizontal crop of vertical text.
Fix: de-rotate the crop (90 degrees from the box shape, 45 from the ink's principal axis).
Probe: `rot30`, `rot45`, `rot90`.

### 7. Misreads on correctly boxed labels (y: 16 of 816 labels, x: 32 of 850, most of the x ones rotated)

y: '10^3'->'10^5', '10^4'->'1,985', '50%'->'500%', '50.0'->'500', '14000000'->'140000001', '0.75'->'0.0.75',
'4e+01'->'e+01', '5.7e+01'->'2'. First cause in 4 y axes.
Fix: top-k readings scored against the axis's progression (the brainstormer's joint decode).

### 8. Tick position on small charts (y: 3 axes, "unexplained")

9000090, 9000091, 9000199: every label right; the fit misses 0.5% because the ticks are 0.5 to 1.6 px off on plots
100 to 200 px tall. Geometry, outside this team's area.

### 9. Linear axis with a misplaced last label read as log (real chart 03)

The women/men chart draws '2021' at equal spacing after 1970..2010 (where 2020 would be). Linear has 5 inliers
with 2021 a 5 px outlier; log, slightly concave, absorbs the misplacement and gets 6, so the count picks log.
Reproduced on the CPU with the base tree's `fit_axis` from the hand-measured anchors.
Fix: labels in arithmetic progression are a linear axis even when log explains one more tick; log needs labels in
geometric progression.

### 10. Dates

No date axis failed on mpl-val (`date_not_used` 0 of 24). Probe `dates` adds the forms mpl-val does not have
(bare month names across a year wrap, "Jan '21", 'Q1 2020', 'Mar 12'), to guard against regressions.

## The probe set

`data/t1-probe`: 640 charts, seeds 11,000,000 to 11,000,639, 16 styles interleaved by seed (so `--limit N` covers
every style evenly), generator `p2d/synth/probe_t1.py`, ground truth checked by overlaying the recorded geometry on
the renders (`out/t1/gtviz/`). `meta["probe"]` is the style, `meta["probe_axis"]` the axis the style is about.
One or two simple series per chart, so every chart is "simple" for the scoreboard.

Standard command (baseline, from the frozen tree):

```sh
cd /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/base/ml && source ../.venv/bin/activate
python -m p2d.evaluate --ckpt runs/v3/best.pt --data /home/drd/PROJECT/CLAUDE/PLOT2DATA-teams/t1-axis/ml/data/t1-probe --limit 640 --ocr runs/ocr1/best.pt
```

Per-style numbers from the frozen base (within 0.5% / scale right; n = 40 per style), filled from
`out/t1/diag-probe-base/summary.txt`:

| style             | x within | x scale | y within | y scale |
| ----------------- | -------- | ------- | -------- | ------- |
| t1-crowded_y      | 1.00     | 1.00    | 1.00     | 1.00    |
| t1-dates          | 0.20     | 0.65    | 0.95     | 1.00    |
| t1-mult_sci       | 1.00     | 1.00    | 0.10     | 1.00    |
| t1-neg_small      | 1.00     | 1.00    | 1.00     | 1.00    |
| t1-nogrid_noticks | 0.97     | 0.97    | 0.88     | 0.97    |
| t1-offset         | 1.00     | 1.00    | 0.00     | 1.00    |
| t1-pow10_edge     | 0.88     | 0.93    | 0.40     | 0.53    |
| t1-right_axis     | 0.97     | 1.00    | 0.93     | 1.00    |
| t1-rot30          | 0.97     | 1.00    | 0.97     | 1.00    |
| t1-rot45          | 0.88     | 1.00    | 0.95     | 1.00    |
| t1-rot90          | 0.00     | 0.95    | 0.97     | 1.00    |
| t1-sci_e          | 1.00     | 1.00    | 0.97     | 1.00    |
| t1-tiny           | 0.97     | 1.00    | 0.78     | 1.00    |
| t1-two_lin        | 0.97     | 0.97    | 1.00     | 1.00    |
| t1-two_log        | 0.65     | 0.65    | 0.57     | 0.57    |
| t1-units          | 0.97     | 1.00    | 0.97     | 1.00    |
| **overall**       | **0.841**| **0.945**| **0.778**| **0.942**|

Each style has an axis under test (`meta["probe_axis"]`); the other axis stays near 1.00 by design. The targets are
`t1-rot90` (0.00) and `t1-dates` (0.20) on x; `t1-offset` (0.00), `t1-mult_sci` (0.10), `t1-pow10_edge` (0.40) and
`t1-two_log` (0.57) on y. These mirror the mpl-val classes: rot90 is class 6, dates class 10, offset and mult_sci
class 4, pow10_edge class 1 variant, two_log class 1.

The ablations (true text on predicted ticks / true ticks through parser+fitter) say where the gap goes:

| set                | pipeline x | true text x | true ticks x | pipeline y | true text y | true ticks y |
| ------------------ | ---------- | ----------- | ------------ | ---------- | ----------- | ------------ |
| mpl-val (200)      | 0.845      | 0.925       | 0.985        | 0.765      | 0.835       | 0.910        |
| plotly-v1 (150)    | 0.947      | 0.960       | 0.980        | 0.840      | 0.913       | 0.973        |
| t1-probe (640)     | 0.841      | 0.944       | 0.955        | 0.778      | 0.803       | 0.830        |

On the probe the fitter/parser leaves y stuck at 0.830 even with true ticks and true texts, because 77 of 142
failing y axes are "multiplier_missed" (every t1-offset and most of t1-mult_sci): the probe forces the multiplier
to be applied, and if the fitter does not get it, the error is 10^6. The multiplier/offset path is the biggest
single lever on the probe set.

## 11. Superscript taken as the whole label (added by the colour-aware boxes)

Introduced by commit 244ce7b (brainstormer's `label_from_source` rewrite); not present in the frozen base.
`out/t1/boxes-mpl-new.txt` shows the new boxes next to the true ink: on seeds 9000016 (`10^-1`, `10^0`, `10^1`),
9000021 (`1e2`, `1e3`, `1e4`), 9000024 (`10^3`, `10^4`), 9000039 (log x) and 9000074 (y log, `1e2..1e5`), the box
is 1 to 3 pixels wide and sits at the row range of the tick MARK rather than the label row range. Example from
9000016 x: tick at (250, 680); returned box (250, 680, 252, 689); true label ink at (227, 698, 271, 722).

Reason, as of 244ce7b's `_label_band`, confirmed by the per-tick overlay (`out/t1/crops/9000016-xticks-truebox.png`
and `9000074-xticks-truebox.png`): matplotlib's `10^k` ticks on these charts are 7 to 10 px long with a 5 to 8 px
gap to the label text; the tick-mark run is 1 to 2 columns wide, so the `line` test in `_label_band` does not fire
(a tick mark is a thin vertical streak, not a horizontal line across the window), the tick mark is taken as the
first glyph band (h_est about 10, w about 2), and `gap_max = max(1, int(0.3 * h_est))` is 3, too small to bridge
the 5 to 8 px gap to the real label. The colour re-filter then uses the tick mark's colour (black), so the
re-band is the same tick mark. The brainstormer's prototype is "find the strongest ink block in the window and
include smaller blocks within about 1.8x its height that center over the tick": a two-pass that would skip the
thin tick-mark run and take the main label block instead.

Impact on the pipeline is bounded by whether class 1 (two-label log) still fires: if both labels are correct text
read from the thin box, calibration still works; if the digit is cut, every `10^k` becomes 10 and the axis fits
as linear. On mpl-val this hit 9000015, 9000027, 9000044, 9000106, 9000154 before the rewrite (class 1); the new
rewrite would do the same by returning only the superscript. Probe: `t1-pow10_edge/x` 0.88 within is partly this.

## 12. Colour-aware box crops the leading "0." / overgrows into a neighbour (added by 244ce7b)

Introduced by the same `label_from_source` rewrite. From `compare-mpl-v244.txt`, 15 charts broke; 7 of them are
this class. Three charts (9000016/21/24) are the superscript (class 11); the rest split as follows (seed, axis,
true -> read):

- **"0." stripped**: `9000162 x` (0.030/0.040/0.020/0.010/0.000 -> 6/8/4/2/0, ALL ticks; the leading "0." is
  dropped from every label on the axis, so an axis of "zero point something" reads as its last digit alone).
  `9000186 y` ("0.0" -> "5", one tick). The thin dot of "." may be deciding the colour of the first-glyph run,
  so after the colour re-filter the main digit at a slightly different hue is excluded; or the box starts after
  the "." column.
- **Overgrown**: `9000098 x` ("105.0" -> "00000", the box captured the neighbour tick's leading digits).
  `9000014 y` ("25/75" -> "-51/151", similar). `9000037 y` ("200,000/400,000/600,000" -> "4/4/200,000", groups
  collapsed in box space). `9000136 y` (every tick on an axis of 0..5e6 reads as 2-3 digits with duplicates:
  "800/5000/2000/80/80/8000"). Here the box widened past the end of one label into the next, or merged two.
- **"-" added**: `9000043 y` ("10^3/10^4" -> "-10^3/-10^4"). The box widened leftward past the first glyph into
  a line pixel (axis spine or gridline), which the reader took as a minus sign.

Mechanism, best guess: the colour re-filter sets the ink mask to `(off < 0.35) & (t > 0.2)`. For a label whose
first ink run is a thin feature (a period, a comma, a decimal point, a tick-mark pixel included by accident),
the "colour" is that feature's rendering; antialiased pixels of the main digits in a slightly different blend
are then excluded. Conversely, when the first ink run is the main glyph of a horizontally-placed label and
other labels of the same colour are close by (crowded axes, small label gaps), the along-axis `_runs` with gap
tolerance can bridge into the next label.

Fix candidates (all for the brainstormer): (a) use the DARKEST pixel of the band, not the median of the brightest
first-glyph set, to define the label colour; (b) require the "colour" step to find at least two independent
clusters of ink along the axis before re-filtering, so a lone decimal point does not define it; (c) after the
re-filter, re-run the main glyph detection on the uncoloured ink too and take the UNION (not replacement) of the
two bands. The 7 regressions here plus the 3 class-11 superscripts bound the price of 244ce7b's rewrite at 10
charts on mpl-val, against 34 fixed (22 y + 12 x); the colour-aware path is a net +24 before any of these fixes.

On the probe set the same mechanism costs 22 x charts (all "cropped" first-cause, concentrated in `t1-crowded_y`
`t1-tiny` `t1-mult_sci` `t1-neg_small` `t1-rot45` `t1-sci_e` `t1-dates`) and 4 y charts (11000203, 11000228,
11000494, 11000575) against gains of 25 x + 29 y.

On the real screenshots (`v244-real.txt`) the mechanism breaks the year labels of `01-panel1.png` and
`01-panel3.png`: the pipeline reads x as `['02', '02', '202', '202', '02', '02', '02', '021', '02', '021']` and
fits the axis as log with 145 and 487 pixel error; v3 base read these as `['2024','2023','2020','2021','2022']`
and fit as linear with 1 pixel error. Overlay in `out/t1/crops/01-panel1-x-v244.png`: the computed boxes are
~13 pixels wide centred on each year label, so the reader sees two middle digits only. The pipeline also hands
refine_labels a tick list with the SAME (pos, anchor_y) duplicated several times (upstream of refine, in
`extract.group_labels` on the sem components), so each year is boxed and read twice. On the win side the same
commit **fixes** `03-women-men-percent.png`: v3 fit x as log (CASES class 9, 145px error); v244's
arithmetic-progression tiebreak takes linear with 2.11px error.
