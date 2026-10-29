"""Before/after tables over the probe suite from the evaluate outputs and the diagnosis summaries.

    python teams/t4-markers/tools/suite_table.py v3 step1 [step2 ...] [--sets "dense row ..."]

Reads out/t4/eval-<set>-<tag>.txt (marker_recall, marker_precision, marker_err_median_pct, all / simple) and, when
present, out/t4/diag-<set>-<tag>/summary.json (recall_capped, err_drawn_median_pct, fn_by_stage, fp_by_cause).
Prints Markdown.
"""

from __future__ import annotations

import argparse
import json
import os

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "..", "out", "t4")
SETS = ["dense", "row", "labels", "shapes", "hollow", "multi", "lines", "val", "plotly"]
KEYS = ["marker_recall", "marker_precision", "marker_err_median_pct", "line_found", "line_rms_median_pct"]


def read_eval(path):
    if not os.path.exists(path):
        return None
    out = {}
    for line in open(path):
        parts = line.split()
        if len(parts) == 3 and parts[0] in KEYS + ["images"]:
            try:
                out[parts[0]] = (float(parts[1]), float(parts[2]))
            except ValueError:
                pass
    return out or None


def read_diag(path):
    p = os.path.join(path, "summary.json")
    return json.load(open(p)) if os.path.exists(p) else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tags", nargs="+")
    ap.add_argument("--sets", default=None)
    a = ap.parse_args()
    sets = a.sets.split() if a.sets else SETS
    print("| set | tag | n gt / returned | recall all (simple) | precision all (simple) | err median % all (simple) | err vs drawn % | recall capped | FN stages | FP causes |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for s in sets:
        for t in a.tags:
            e = read_eval(os.path.join(OUT, f"eval-{s}-{t}.txt"))
            d = read_diag(os.path.join(OUT, f"diag-{s}-{t}"))
            if e is None and d is None:
                continue
            cells = [s, t]
            if d:
                cells.append(f"{d['n_gt']} / {d['n_pred']}")
            else:
                cells.append("")
            if e:
                r, p, m = e.get("marker_recall", (float("nan"),) * 2), e.get("marker_precision", (float("nan"),) * 2), e.get("marker_err_median_pct", (float("nan"),) * 2)
                cells += [f"{r[0]:.3f} ({r[1]:.3f})", f"{p[0]:.3f} ({p[1]:.3f})", f"{m[0]:.3f} ({m[1]:.3f})"]
            else:
                cells += ["", "", ""]
            if d:
                ed = d.get("err_drawn_median_pct")
                cells.append(f"{ed:.3f}" if ed is not None else "")
                cells.append(f"{d.get('recall_capped', float('nan')):.3f}")
                fn = d.get("fn_by_stage", {})
                fp = d.get("fp_by_cause", {})
                cells.append(" ".join(f"{k} {v}" for k, v in sorted(fn.items(), key=lambda kv: -kv[1])[:4]))
                cells.append(" ".join(f"{k} {v}" for k, v in sorted(fp.items(), key=lambda kv: -kv[1])[:4]))
            else:
                cells += ["", "", "", ""]
            print("| " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
