"""Round-4 combined scoreboard: run the current-main checkpoint over any
subset (`--data t5-real`, `--data t5-real-ext`, `--data t5-real-100`) and
print one table.

    python ml/teams/round4-benchmark/tools/scoreboard.py --data data/t5-real-100
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ML = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def source_of(cid: str) -> str:
    for pre in ("fred", "owid", "giss", "noaa", "wb", "bls"):
        if cid.startswith(pre + "-"):
            return pre
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="path relative to ml/ (e.g. data/t5-real-100)")
    ap.add_argument("--ckpt", default="runs/t5r2-clutter/best.pt")
    ap.add_argument("--ocr", default="runs/ocr1/best.pt")
    ap.add_argument("--tta", default="shift")
    ap.add_argument("--out", default=None, help="json output path (relative to ml/)")
    a = ap.parse_args()
    cmd = ["python", "-m", "p2d.eval_t5real",
           "--ckpt", a.ckpt, "--ocr", a.ocr, "--data", a.data, "--tta", a.tta]
    out = a.out
    if out:
        cmd += ["--json", out]
    env = dict(os.environ, OMP_NUM_THREADS="1")
    r = subprocess.run(cmd, cwd=ML, env=env, text=True, capture_output=True)
    print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        sys.exit(r.returncode)
    if out:
        rows = json.load(open(os.path.join(ML, out)))
        by = {}
        for row in rows:
            src = source_of(row["id"])
            for r2 in row["rows"]:
                v = r2["rms_pct"]
                b = by.setdefault(src, {"n": 0, "ok": 0, "half": 0, "one": 0, "fail": 0, "rms": []})
                b["n"] += 1
                if v != v:  # NaN
                    b["fail"] += 1
                    continue
                b["rms"].append(v)
                if v < 0.5:
                    b["half"] += 1
                if v < 1.0:
                    b["one"] += 1
                b["ok"] += 1
        print()
        print(f"{'source':8s}  {'series':>7s}  {'<0.5%':>6s}  {'<1%':>6s}  {'fail':>5s}  {'med rms':>8s}")
        for src in sorted(by):
            b = by[src]
            import statistics
            med = statistics.median(b["rms"]) if b["rms"] else float("nan")
            print(f"{src:8s}  {b['n']:>7d}  {b['half']/b['n']:>6.0%}  {b['one']/b['n']:>6.0%}  "
                  f"{b['fail']:>5d}  {med:>7.2f}%")


if __name__ == "__main__":
    main()
