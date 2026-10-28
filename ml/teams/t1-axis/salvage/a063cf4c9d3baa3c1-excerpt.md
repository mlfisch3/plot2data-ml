# Salvage from predecessor curator a063cf4c9d3baa3c1 (Fable 5.1)

Spawned about Wed 28 Oct 2026, 02:00 EDT; cut off by usage limit at about 02:30 EDT.
Nearly everything was committed by the predecessor itself. This file records the
few findings whose numbers were in the predecessor's logs but not in a committed
file.

## Reader alone on TRUE label boxes, mpl-val (last line of the completed run)

`teams/t1-axis/test_reader.py` printed, before being cut off while writing to
`out/t1/reader-mpl-base.txt` (file now holds the tee garbage of a resumed run,
so the number is only in the JSONL):

```
TOTAL                      n= 1916  exact 0.990  value ok 0.972  cut_by_image 0
TOTAL/rot                  n=   40  exact 0.225  value ok 0.225  cut_by_image 0
all/x                      n=  959  exact 0.985  value ok 0.986  cut_by_image 10
all/x/rot                  n=   40  exact 0.225  value ok 0.225  cut_by_image 0
all/y                      n=  957  exact 0.995  value ok 0.958  cut_by_image 4
```

Reading: given the TRUE label box on mpl-val, the tick reader is 99% exact and
97.2% value-correct, but it reads a horizontal crop of a rotated label as
"wrong" four times out of five (22.5% exact on 40 rotated labels). All the
value-only drops are the % sign dropped on y, and %-style vs 1,000,000-style
confusion on long numeric labels. Rotated labels need a de-rotated crop.

The equivalent run on `data/t1-probe` crashed in `parse_value` with an
OverflowError on a text like 'e+01' (10 ** int('e+01') is bogus); fix the
offending parse to return None on an unparseable exponent before using this
script on the probe. The reader-probe baseline is not measured yet.

## Running state killed on takeover

The predecessor's `diag-probe-base.sh` had been running for 14 hours in a wait
loop (its `pgrep -f "[t]1-axis/diag.py"` matched its own parent shell because
the pattern string literally appears in the eval that spawned it). PIDs 829511
and 829508 killed by the Opus 4.7 replacement at 16:07 EDT; nothing was lost
(the inner python had never actually started). Rule: a pgrep pattern must not
appear in any ancestor shell's command line; use a wait on a sentinel file
instead.

## Brainstormer's uncommitted state

As of pause the brainstormer (a33a9de7fe0759d04) had modified
`p2d/eval_calib.py`, `p2d/extract.py`, `p2d/ocr.py`, `p2d/pipeline.py` and
added `p2d/axis.py` and `tests/test_axis.py`. All uncommitted. The curator left
these untouched so the brainstormer's replacement can pick up where it left
off.
