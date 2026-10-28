"""Score the real benchmark through any copy of the p2d package.

Lets us measure the real-chart benchmark against the frozen baseline code (6b313e9)
even though `eval_t5real.py` lives only on team/t5-robust. P2D_ROOT selects the
package to load; the loader (truth parsing, scoring) and the data (data/t5-real)
stay the live tree's. Replaces the predecessor's `python -m p2d.eval_t5real` from
the base worktree, which failed with "attempted relative import with no known
parent package" because eval_t5real.py was not in that worktree.

    P2D_ROOT=/path/to/base/ml python teams/t5-robust/tools/real_bench_pkg.py \
      --ckpt /path/to/runs/v3/best.pt --ocr /path/to/runs/ocr1/best.pt \
      --data data/t5-real --out out/t5/real-bench-base --json out/t5/real-bench-base.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ML = os.path.abspath(os.path.join(HERE, "..", "..", ".."))  # the team worktree's ml/

# The p2d package to score through: baseline (/.../base/ml) or the live tree's (default).
P2D_ROOT = os.environ.get("P2D_ROOT") or ML
sys.path.insert(0, P2D_ROOT)

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from p2d.evaluate import draw, load_net  # noqa: E402
from p2d.ocr import load_reader  # noqa: E402
from p2d.pipeline import run  # noqa: E402


def _load_loader():
    """Load `load_truth` and `score_chart` from the live tree's eval_t5real.py as a plain module."""
    path = os.path.join(ML, "p2d", "eval_t5real.py")
    spec = importlib.util.spec_from_file_location("_t5real_loader", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # The file has relative imports at module level; strip them before exec, then rebind what the loader uses.
    src = open(path).read()
    src = src.replace("from .evaluate import draw, load_net", "")
    src = src.replace("from .ocr import load_reader", "")
    src = src.replace("from .pipeline import run", "")
    exec(compile(src, path, "exec"), mod.__dict__)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--ocr", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=None, help="directory for per-chart overlays")
    ap.add_argument("--json", default=None, help="per-chart rows JSON")
    a = ap.parse_args()
    loader = _load_loader()
    net = load_net(a.ckpt)
    reader = load_reader(a.ocr)
    if a.out:
        os.makedirs(a.out, exist_ok=True)
    allrows, per_chart = [], []
    for f in sorted(os.listdir(a.data)):
        if not f.endswith(".json"):
            continue
        meta = json.load(open(os.path.join(a.data, f)))
        cid = meta["id"]
        img = cv2.imread(os.path.join(a.data, cid + ".png"))[..., ::-1].copy()
        truth = loader.load_truth(meta, os.path.join(a.data, cid + ".data.csv"))
        res = run(net, reader, img)
        rows = loader.score_chart(meta, truth, res)
        xs_ = res.xfit.scale if res.xfit else "-"
        ys_ = res.yfit.scale if res.yfit else "-"
        warn_tag = ("  WARN " + "; ".join(res.warnings)) if getattr(res, "warnings", None) else ""
        row_s = "  ".join(f"{r['rms_pct']:.2f}% cov {r['cover']:.0%}" for r in rows)
        print(f"{cid:26s} found {len(res.series)}/{len(truth)}  scales {xs_}/{ys_}  {row_s}{warn_tag}", flush=True)
        allrows += rows
        per_chart.append({"id": cid, "found": len(res.series), "truth": len(truth), "rows": rows,
                          "warnings": list(getattr(res, "warnings", []) or []), "xscale": xs_, "yscale": ys_})
        if a.out:
            cv2.imwrite(os.path.join(a.out, cid + ".png"), draw(img, res.ex)[..., ::-1])
    v = np.array([r["rms_pct"] for r in allrows], float)
    cov = np.array([r["cover"] for r in allrows], float)
    good = np.isfinite(v) & (cov >= 0.8)
    print(f"series {len(v)}  found (cover >= 80%) {good.mean():.0%}  median rms {np.nanmedian(v):.2f}%  "
          f"median rms of found {np.median(v[good]) if good.any() else float('nan'):.2f}%  "
          f"within 1% {np.mean(np.nan_to_num(v, nan=1e9) < 1):.0%}  "
          f"within 0.5% {np.mean(np.nan_to_num(v, nan=1e9) < 0.5):.0%}  failed {np.isnan(v).sum()}")
    if a.json:
        json.dump({"p2d_root": P2D_ROOT, "ckpt": a.ckpt, "per_chart": per_chart}, open(a.json, "w"), default=float, indent=1)


if __name__ == "__main__":
    main()
