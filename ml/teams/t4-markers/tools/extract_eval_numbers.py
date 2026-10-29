"""Extract the headline evaluate numbers from one or more eval-<set>-<tag>.txt files.

Prints a table in the shape of CASES_R2.md section 10.

    python teams/t4-markers/tools/extract_eval_numbers.py <tag> [<tag> ...]

For each tag it reads out/t4r2/eval-<k>-<tag>.txt for every k in
(dense row labels shapes hollow multi lines val plotly) and prints the four
headline markers metrics (recall all/simple, precision all/simple, error
all/simple) and the line metrics (line_found, rms, peak_err).
"""

import re
import sys
import pathlib

SETS = ["dense", "row", "labels", "shapes", "hollow", "multi", "lines", "val", "plotly"]
PATS = {
    "line_found": r"line_found\s+(\S+)\s+(\S+)",
    "line_rms_median_pct": r"line_rms_median_pct\s+(\S+)\s+(\S+)",
    "peak_err_median_pct": r"peak_err_median_pct\s+(\S+)\s+(\S+)",
    "marker_recall": r"marker_recall\s+(\S+)\s+(\S+)",
    "marker_precision": r"marker_precision\s+(\S+)\s+(\S+)",
    "marker_err_median_pct": r"marker_err_median_pct\s+(\S+)\s+(\S+)",
    "frame_found": r"frame_found\s+(\S+)",
    "calib_x_within_0.5": r"calib_x_within_0\.5\s+(\S+)",
    "calib_y_within_0.5": r"calib_y_within_0\.5\s+(\S+)",
}


def parse(path):
    out = {}
    try:
        text = pathlib.Path(path).read_text()
    except FileNotFoundError:
        return out
    for k, pat in PATS.items():
        m = re.search(pat, text)
        if m:
            out[k] = m.groups()
    return out


def main():
    tags = sys.argv[1:]
    if not tags:
        tags = ["int"]
    root = pathlib.Path("out/t4r2")
    for tag in tags:
        print(f"=== {tag} ===")
        for k in SETS:
            p = root / f"eval-{k}-{tag}.txt"
            vals = parse(p)
            if not vals:
                print(f"{k:>8}: (not found at {p})")
                continue
            mr = vals.get("marker_recall", ("-", "-"))
            mp = vals.get("marker_precision", ("-", "-"))
            me = vals.get("marker_err_median_pct", ("-", "-"))
            lr = vals.get("line_rms_median_pct", ("-", "-"))
            print(f"{k:>8}: recall {mr[0]}/{mr[1]}  prec {mp[0]}/{mp[1]}  err {me[0]}/{me[1]}  line_rms {lr[0]}/{lr[1]}")


if __name__ == "__main__":
    main()
