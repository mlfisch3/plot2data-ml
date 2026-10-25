"""Score the classical engine's output (tools/run-classical.ts) with the same metric.

    python -m p2d.score_classical --data data/mpl-val --pred out/classical-val.json
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

from .evaluate import gt_value_to_px
from .extract import Extraction, Series
from .metrics import score, summarise_split


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--pred", required=True)
    a = ap.parse_args()
    pred = json.load(open(a.pred))
    rows = []
    errors = 0
    for sid, p in sorted(pred.items()):
        meta = json.load(open(os.path.join(a.data, f"{sid}.json")))
        ex = Extraction(M=np.eye(2, 3), plot_area=None)
        if "error" in p:
            errors += 1
        else:
            f = p["frame"]
            ex.plot_area = [f["x0"], f["y0"], f["x1"], f["y1"]]
            for s in p["series"]:
                pts = np.array(s["points"], float).reshape(-1, 2)
                px = np.column_stack([gt_value_to_px(meta, "x", pts[:, 0]), gt_value_to_px(meta, "y", pts[:, 1])])
                px = px[np.all(np.isfinite(px), axis=1)]
                if s["mode"] == "curve":
                    ex.series.append(Series(kind="line", line_px=px, markers_px=np.zeros((0, 2))))
                else:
                    ex.series.append(Series(kind="scatter", line_px=np.zeros((0, 2)), markers_px=px))
        # The classical engine works at source resolution: canvas scale 1.
        rows.append(score(meta, ex, canvas_scale=1.0))
    split = summarise_split(rows)
    s, simple = split["all"], split["simple"]
    print(f"engine errors: {errors}")
    print(f"{'metric':28s} {'all':>10s} {'simple':>10s}")
    for k in s:
        print(f"{k:28s} {float(s[k]):>10.4f} {float(simple.get(k, float('nan'))):>10.4f}")


if __name__ == "__main__":
    main()
