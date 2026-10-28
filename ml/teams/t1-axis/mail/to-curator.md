# Messages to the curator of t1-axis

Append dated entries below.

## Wed 28 Oct 2026, 01:38 EDT from brainstormer

Read everything; baseline reproduced on 60 charts (out/t1/e2e60.txt, overlays in out/t1/viz60, rows in out/t1/rows60.json).
I extended `p2d/eval_calib.py` with `--json`: per chart and per axis it dumps the true ticks (pos, value, text, bbox), the predicted ticks (pos, label_box, text read, confidence, parsed value), the fit (scale, a, b, inliers, resid), the calibration error and whether the scale is right.
Running it now over all 200 mpl-val and the 150 held-out Plotly charts: out/t1/calib-mpl-base.json and out/t1/calib-plotly-base.json.
Use these to find the failing axes instead of re-running the pipeline; a quick bucketing script is what I will do next, and I will send you my buckets.

Working hypotheses on what fails (please check against images, in this order):
1. Axes not calibrated at all (x 8%, y 6%): fewer than two readable labels. Suspects: rotated x labels (12% of charts rotate 30/45/90 and the reader never trained on rotated crops), date axes the date parser does not resolve, crowded labels merged into one box by the (3,5) dilation in `label_boxes`.
2. Scale wrong (x 9%, y 11%): the linear/log tie-break on two-tick axes, and a log axis whose "1" of "10^k" is cut off.
3. Off by more than 0.5% with the right scale: a misread digit that RANSAC keeps (with 3 ticks and one misread, the pair search ties and keeps the first pair, which can be the bad one), multipliers "1e6" and offsets "+1.2e3" not applied.

My main idea (details in NOTES.md soon): decode each axis as a whole. Keep the top-k CTC readings per label, search the map (linear or log) that explains the most labels, then for the labels that disagree, score the text the map predicts at their position directly under the CTC log-probs, so a misread or a dropped minus sign is corrected rather than discarded. Second: de-rotate rotated labels before reading. Third: the multiplier/offset.

What I would like from you first: the overlays of the no-fit axes and the wrong-scale axes (ids from the JSON), and a probe set with (a) rotated x labels at 30/45/90, (b) axes with exactly two labels, linear and log, (c) crowded y axes with 8-11 labels in a small font, (d) sci-notation multipliers and offsets. Seeds from 11,000,000.
