# t5-robust brainstormer scratch (chronological)

## Wed 28 Oct 2026, 16:09 EDT - takeover

Opus 4.7 replacement spawning for Fable 5.1 agent a2b7d3fe8c41cce03 that was cut off at ~02:30 EDT. Branch head a7aed7d, clean tree. Predecessor's five implementation commits (72d21cf, 259b09d, 36638e3, 804b155, 0b9ec67) plus curator infrastructure (23a5b7d probe gens + chartjs renderer, 7bd1c75 tests, 19e6132 row-compare tool, a7aed7d FRED chart window) all intact.

## 16:20 EDT - plan

Running zoom-eval.sh on `runs/t5-zoom/best.pt` across all four scoreboard sets + mpl-val pixel-refine. In parallel reading everything the predecessor left. The t5-zoom training finished at 04:19 EDT (3000 iters, val loss 2.97 -> 2.49). TTA module in place but off; need to sweep.

Decision: measure zoom first, then TTA sweep. Keep the pipeline changes they introduced.

## 16:28 EDT - zoom numbers land

mpl-val: line_rms_median 0.293 (vs a7aed7d+v3 0.299). Modest. Marker_recall 0.540 vs 0.531.
plotly: 0.229 flat.
Corpus: median 0.080 but log-y 1/1 (was 3/1!) and log-log 1/1 (was 24/1!!). The zoom finetune cured native-mode ghosting that `_mostly(..., sem[GRID])` could not catch at native scale.
Real: all 7 reads consistent with a7aed7d.
Pixel-only mpl-val: line_rms 0.216 (vs base 0.311, -30%); frame_found 0.98.

Verdict: zoom helps. Submit with it.

## 16:29 EDT - TTA sweep

Launched 3 configs x 4 sets. Corpus first (fast).

TTA shift on corpus: **offset-annotation 61.22% -> 0.020%** - the box IS detected and axis_factor DID receive it, but at native-scale 14x20 the OCR fails to match `_MULT`. The 0.5-px shift pass produces a slightly larger connected component (dilation + shift combines), the OCR crop widens, "1e6" matches. Clean mechanism.

Scale alone or shift+scale: no fix on offset-annotation (scale dilutes the shift pass's probability lift). shift alone is the winner.

Corpus median 0.080 -> 0.072 under shift, worst 61.22 -> 0.58. The ghost series stay 1/1.

Killed scale and shift+scale on mpl-val to save GPU; launched plotly tta=shift standalone.

## 16:38 EDT - mpl-val TTA shift lands

line_rms_median 0.293 (zoom) -> 0.280 (zoom+shift). marker_precision 0.544 -> 0.719 (!). frame_err_median 1.08 -> 0.96. TTA shift kills marginal false-positive markers via averaging.

## 16:40 EDT - plotly TTA shift lands

line_found 0.780 -> 0.790. line_rms_median 0.229 -> 0.234 (slight uptick but p90 improves). marker_precision 0.738 -> 0.852. calib_y_within_0.5pct 0.887 -> 0.893.

Submission ingredients fixed: t5-zoom + a7aed7d code + --tta shift.

## 16:40 EDT - REPORT.md v1 committed (a9658fb)

Full ablation on mpl-val (section 5.1), scoreboard tables (section 2), decoding mechanism explained in section 7. Submission sentence: "native pass gives data-accuracy gain, zoom-crop training fixes the native-pass gridline-ghost regression, --tta shift fixes the native-pass OCR-threshold regression."

Sent main message with claim and verification commands.

## 16:42 EDT - coordinator accepts, suggests more

"Keep improving... frame_err_p90 regression tail is worth looking at."

Tried a corner-peak confidence floor in plot_frame (reject frames with top peak < 0.5). Measured on mpl-val: no-op. The regression tail is driven by STRONGLY-fired corner peaks placed in wrong positions on frameless styles, not weak-peak frames. Reverted.

## 16:54 EDT - curator caught chartjs-val numbers from queue8

Chart.js-val submission numbers: line_rms_median 0.343 -> 0.299 (-13%), peak_err -22-34%, marker_precision +6pp, frame_err_median -42%. Only regression is frame_found 3pp (and the frame-independent refine picks up the slack). So chartjs-val is a WIN, not a probe regression as I had briefly feared.

Updated REPORT.md section 6 (chartjs-val probe) and section 8 (replaced corner-peak floor with tick-anchor-hull next-step). Committed as bd6a491.

Sent 2nd main message with the honest reverted-floor result.

## 16:55 EDT - coordinator ACCEPTS bd6a491

"Accepting bd6a491 as the t5 submission. Stand there." Suggests OPTIONAL V2 on `team/t5-robust-chartjs` attacking Chart.js in training. Hold chroma/ink for after the contest.

## 16:55 EDT - V2 branch and launch

Branched `team/t5-robust-chartjs` off bd6a491. Wrote REPORT_V2.md skeleton. Launched chartjs training (init from runs/t5-zoom/best.pt, 4 data roots including t5-chartjs, 3000 iters, --zoom 0.35). Through flock lock.

Expected 90-150 min. GPU is heavily contended (11+ teams running evals in parallel). First iter JSON will appear at it=1000.

## 17:00 EDT - sent main the plan

V1 untouched, V2 is OPTIONAL deeper submission. If V2 wins all four scoreboard sets, becomes the submission. If V2 misses on any, V1 stands.

## 17:12 EDT - freeing GPU

Killed the floor-plotly leg of my earlier frame-floor-eval sweep (`pkill -f "[t]5-zoom.*floor-plotly"`); the floor change is already reverted and this leg was only going to produce confirmatory data. The GPU slot now helps the training.

## 17:56 EDT - training at 61 min CPU, still no iter=1000

GPU at 100% utilisation, 15 GB memory used. t5-zoom hit it=1000 at 93 min CPU time last night; mine is slower under heavier contention. Re-armed Monitor on the training log with a tighter filter (`"it":` entries only). Waiting.

## 17:57 EDT - USAGE_MINDER PAUSE at 64%

Writing this state and SCRATCH, stopping monitors, idling. V2 training continues in the background on its own.

## open thoughts for the resumer

- If V2's val loss at it=1000 is NOT improving over t5-zoom's final 2.49, the mix is too matplotlib-heavy and the chartjs effect gets drowned; consider training for 2k more iters from the already-trained V2 ckpt, with chartjs oversampled (concat the chartjs path 2x in the --data list). This is a cheap second shot if the first V2 numbers disappoint.
- The curator may also have launched queue9 and later probe sweeps while I was busy - watch to-brainstormer.md on resume.
- If V2 does win, remember to send a SECOND main message with the V2 numbers and the branch team/t5-robust-chartjs REPORT_V2.md path. The coordinator's phrase was "deeper second submission".
- Do NOT commit anything to `team/t5-robust`. The V1 submission is sealed.
