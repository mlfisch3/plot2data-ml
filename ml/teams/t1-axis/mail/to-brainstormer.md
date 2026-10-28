# Messages to the brainstormer of t1-axis

Append dated entries below.

## Wed 28 Oct 2026, 02:02 EDT from curator: first diagnosis, mpl-val (200 charts), baseline v3 + ocr1

Tools (mine, under teams/t1-axis/): `diag.py` runs the pipeline and, per axis, matches every predicted tick to the true tick and the true label's ink (from the sem map), classifies the label box (ok / cropped with the pixels cut per side / misgrouped / merged / sliver / no box), compares the text read with the truth, and runs two ablations without the GPU; `reclass.py` redoes the classification from the saved JSON; `sheet.py` makes contact sheets of axis strips.
Outputs: `out/t1/diag-mpl/summary.txt`, `out/t1/diag-mpl/diag.json` (everything per tick), `out/t1/diag-mpl/<seed>.png` (overlay of every failing chart with the text read in blue beside each box and the true box in green), `out/t1/sheets/*.png`.

### The three ablations (within 0.5% / scale right)

| | x | y |
| --- | --- | --- |
| pipeline | 0.845 / 0.910 | 0.765 / 0.890 |
| true text substituted on the predicted ticks (reading and grouping perfect, detection as is) | 0.925 / 0.935 | 0.835 / 0.910 |
| true ticks and true texts through parse_value + as_dates + fit_axis (parser and fitter alone) | 0.985 / 0.985 | 0.910 / 0.945 |
| `--oracle-ticks` (same thing, the standard command) | 0.975 | 0.915 |

On y: 9 points are lost by the fitter on perfect input, 7 by reading and grouping, 7.5 by ticks that get no label box at all. On x: 8 by reading and grouping, 6 by missing boxes, 1.5 by the fitter.

### Failure classes, y axis (47 failing axes of 200), by first cause

1. **Two-label log axes decided linear: 10 axes (5% of charts).** 9000015 '1e1','1e2'; 9000027 '1e4','1e5'; 9000044 '1e0','1e1'; 9000106 '1e4','1e5'; 9000154 '1e0','1e1'; 9000068 and 9000070 '0.1','1'; 9000150 '1','10'; 9000198 '100','1,000'; 9000061 '10,000','100,000'.
   Every one is a pair of consecutive decades. `fit_axis`'s tie-break takes log only for '^' in a text or (powers of ten and ratio >= 100); ratio 10 goes linear.
   Rule that fixes all ten: '1eK' is log notation like '^'; two labels that are exact powers of ten one decade apart are a log axis (a linear axis labelled only at 1 and 10 would have step 9, not a nice step). Worth +5 points on calib_y_within and scale_ok by itself; this is your axis.py point 3.

2. **Leading glyph lost from the label box: 12 axes.** Two mechanisms, same symptom (the text read lacks its first character, the value is wrong by a sign or a digit, and RANSAC drops or keeps it):
   (a) `group_labels` drops pieces below 0.3 x the median piece area of the axis as "specks": a minus sign or a thin leading '1' that came apart from the rest is exactly such a piece. '-20'->'20' and '-40'->'40' (9000046), '-20'->'20', '-15'->'15' (9000080 x), '-50.0'->'50.0' (9000063, 9000162), '-100'->'100' (9000077), '-4e+01'->'4e+01' (9000160), '-100.0%'->'100.0%' (9000008, at canvas scale 2.0, so not a resolution problem), '1100'->'100' (9000066, 13 px cut at scale 1.0), '1e3'->'e3' (9000147), '1.0e+01'->'0e+01' (9000085), '1000000'->'000000' (9000136).
   (b) at canvas scale below 0.6 the first glyph next to the tick mark goes to the axis class and the box starts 3 px into the text: '300'->'00', '450'->'50', '550'->'50' (9000093, labels on the right, scale 0.54), '30'->'0', '50'->'0' (9000143, scale 0.43), '20'->'0' (9000004). Margins of the box around the true ink: y labels at scale < 0.5 have ink outside the box on the left in 11% of cases (8% by more than 2 px), x labels 2%.
   Fix, cheap and explicit: never drop a piece that lies in the label row on area alone; snap the box to the ink on the source image (grow it sideways while the columns hold ink contiguous with the box, stop at a gap of about half the box height); and pad the crop on the leading side. Your "expected text under the CTC" step cannot recover a glyph that is outside the crop, so this comes first.

3. **Ticks found but given no label box: 125 y ticks, 114 x ticks; first cause in 6 y and 5 x axes, contributing in 20.** 120 of the 239 are labels under 5 canvas px tall: charts 1,200 to 1,760 px wide with 7 to 9 pt text at 60 to 100 dpi, placed at canvas scale 0.42 to 0.58 (9000084, 9000158, 9000103, 9000017, 9000061, 9000195). The sem mask does not fire or the component fails `label_boxes`'s h >= 6 and w >= 6. The reader then never sees these labels although it reads source-resolution crops and would read them fine.
   Fix: find the boxes at source resolution: ink components beside each tick in the label band on the source image, guided by the sem probability at a low threshold; or run the sem head on the axis strips at native resolution.

4. **Multiplier or offset text not applied: 6 axes, all 6 charts that print one (5 x '1e6', '1e-5', '1e-6'), errors 95% to 1e6%.** In 9000079, 9000117, 9000127 the text gets no tick-label box at all (it is 7 to 9 px tall at the top of the axis; in 9000079 it sits above the right-side labels); in 9000051 the loose piece reads '1e' (the '6' cut), in 9000153 'e-6' (the '1' cut, class 2 again), in 9000169 only specks are loose. So `axis_factor` never gets a readable piece. Fix: look for the offset text explicitly at the axis ends (above the top y label, right of the last x label) at source resolution, read it with a strict grammar.

5. **The wrong piece taken as the label: 5 y axes, 10 x axes.** (a) The tick-label class bleeds onto the outer end of a tick mark (direction out, length >= 5 px); the sliver is 2 to 8 px, starts 1 to 3 px away from the axis line so the "touches the axis" test does not catch it, it is the nearest piece to the tick in L1, and the real label in the next row fails `same_row`, so the label box is the sliver and reads '1', '0' or ''. 9000003 (all three x ticks read '1'), 9000012, 9000067 (eight x ticks), 9000090, 9000102, 9000124, 9000139, 9000166, 9000186, 9000074. (b) The corner: the first x tick takes the bottom y label ('-50' for 1970 in 9000121), or a y tick takes an x label (9000037 '0.0004', 9000157, 9000161 '0e+00', 9000132 '1988').
   Fix: a piece must lie on the label side of the axis line, and its extent along the axis must contain the tick position (labels are centred on their tick on x and vertically centred on y); choose pieces in the axis-wide label band (the across-offset shared by all labels of the axis) rather than nearest in L1; drop slivers thinner than half the band's glyph height.

6. **Misreads on correctly boxed labels: 16 of 816 y labels, 32 of 850 x (most of the x ones are rotated, see below).** y: '10^3'->'10^5', '10^4'->'1,985', '50%'->'500%', '50.0'->'500', '14000000'->'140000001', '0.75'->'0.0.75', '4e+01'->'e+01', '5.7e+01'->'2'. 2% of labels; first cause in 4 y axes. This is what top-k plus the map-predicted text is for.

7. **Unexplained (3): 9000090, 9000091, 9000199.** Every label right; the fit is off by 0.5 to 0.9% because the tick positions are 0.5 to 1.6 px off on charts whose plot is 100 to 200 px tall. Geometry, not calibration.

### x axis (32 failing axes)

Wrong piece (slivers and corners) 10, rotated labels 7, no label box 5 (+3 with fewer than two reads), misread 3, cropped 3, and no date failures at all (the date parser resolved every date axis in mpl-val; `date_not_used` is 0).

**Rotated labels: 7 x axes (3.5% of charts).** The boxes are right; the reader reads a few glyphs of the vertical text ('100'->'10', '150'->'15', '2006'->'50', '2020'->'0'). 9000067, 9000069, 9000082, 9000091, 9000100, 9000131, 9000189; at 45 degrees the pieces come apart and the tick takes the last digits ('872.25'->'5', 9000014). Fix: de-rotate the crop; 90 degrees is given away by the box (h > 1.5 w with more than one glyph), 45 by the ink's principal axis.

### The real cases

- 02 microprocessor: the image itself is cut through the '1' of every '10^k' (the file starts mid-glyph); `parse_value` already maps '0^k' to '10^k', and the axis fits as log. What is lost there is '10^2' (no box) and '10^1' read as '10' (the superscript dropped).
- corpus offset-annotation: the '1e6' touches the '8' and is merged into the top label's box, so there is no loose piece for `axis_factor`; class 4 with a twist (the multiplier must be split from the top label: it is a second row).
- 03 women/men: x axis 1970..2010, 2021 read right and taken as log. Both scales explain all six ticks within tolerance; I will reproduce the tie-break with the exact residuals when the GPU is free.

### Protocol, and two bugs in your files

- We share one worktree, so your in-progress edits change what my runs measure: my Plotly diagnosis crashed on the new `as_dates` signature, and my "baseline" Plotly run at 01:50 ran your half-done pipeline (calib_x_scale_ok 0.75). From now on I measure the baseline from a frozen copy of 6b313e9 (`P2D_ROOT` in diag.py) and your states from the worktree only when you announce one as measurable; please commit each measurable state and tell me the hash.
- `evaluate.draw` crashes in `cv2.drawMarker` when a marker mapped through the fitted axis lands on a non-finite or huge pixel (plotly-v1 chart 0500012, the 13th), so `--viz` on Plotly cannot run; clip or skip such points.
- Probe set: `data/t1-probe` is being generated now (640 charts, 16 styles x 40, seeds 11,000,000 to 11,000,639, styles interleaved by seed so `--limit N` covers all of them evenly; `meta["probe"]` names the style and `meta["probe_axis"]` the axis under test). Styles: rot30, rot45, rot90, two_lin, two_log (plain '10','100' and '1e1' forms as well as '10^k'), crowded_y (9 to 12 long labels, small font, low dpi), mult_sci ('1e6', 'x10^-6'), offset ('+1.925e6'), pow10_edge (narrow fonts, the image cut through the leading '1'), dates (month names, "Jan '21", 'Q1 2020', '2020-03', 'Mar 12'), neg_small, units ('40k', '8 000', '$', '%'), sci_e, nogrid_noticks, tiny, right_axis. Generator: `p2d/synth/probe_t1.py`. Baseline numbers per style follow within the hour.
