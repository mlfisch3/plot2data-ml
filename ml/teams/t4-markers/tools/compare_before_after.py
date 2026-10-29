"""Compare before/after measurements of the round-2 probes and standard sets.

    python teams/t4-markers/tools/compare_before_after.py <before_tag> <after_tag>

Reads out/t4r2/eval-<k>-<tag>.txt for every k in SETS and prints a Markdown
table of the deltas: recall (all / simple), precision (all / simple),
err_median_pct (all / simple).
"""

import re
import sys
import pathlib

SETS = ["val", "plotly", "linemk", "dense", "row", "shapes", "hollow", "labels", "multi", "lines"]
METRICS = {
    "marker_recall": "recall",
    "marker_precision": "prec",
    "marker_err_median_pct": "err%",
}


def parse(path):
    out = {}
    try:
        text = pathlib.Path(path).read_text()
    except FileNotFoundError:
        return out
    for key in METRICS:
        m = re.search(rf"{key}\s+(\S+)\s+(\S+)", text)
        if m:
            out[key] = (float(m.group(1)), float(m.group(2)))
    return out


def main():
    if len(sys.argv) < 3:
        print("usage: compare_before_after.py <before_tag> <after_tag>")
        sys.exit(2)
    before_tag, after_tag = sys.argv[1], sys.argv[2]
    root = pathlib.Path("out/t4r2")
    rows = []
    for k in SETS:
        before = parse(root / f"eval-{k}-{before_tag}.txt")
        after = parse(root / f"eval-{k}-{after_tag}.txt")
        if not before or not after:
            continue
        for metric_key, metric_label in METRICS.items():
            if metric_key not in before or metric_key not in after:
                continue
            ba, bs = before[metric_key]
            aa, bss = after[metric_key]
            delta_a = aa - ba
            delta_s = bss - bs
            rows.append((k, metric_label, ba, bs, aa, bss, delta_a, delta_s))

    print(f"| set | metric | {before_tag} all / simple | {after_tag} all / simple | delta all / simple |")
    print("| --- | --- | --- | --- | --- |")
    for k, m, ba, bs, aa, bss, da, ds in rows:
        if m == "err%":
            print(f"| {k} | {m} | {ba:.3f} / {bs:.3f} | {aa:.3f} / {bss:.3f} | {da:+.3f} / {ds:+.3f} |")
        else:
            print(f"| {k} | {m} | {ba:.3f} / {bs:.3f} | {aa:.3f} / {bss:.3f} | {da:+.3f} / {ds:+.3f} |")


if __name__ == "__main__":
    main()
