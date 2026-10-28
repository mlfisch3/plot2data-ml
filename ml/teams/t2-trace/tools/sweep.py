"""Sweep tracker parameters on cached network outputs, and diagnose hops.

    python teams/t2-trace/tools/sweep.py --ckpt runs/v3/best.pt --data data/mpl-val --limit 60 --cache /tmp/.../cache60
        [--set emb_max=1.5 emb_pen=2.0] [--hops]

Caches sem/heat/emb per chart (float16) so later runs need no GPU. Scores with the standard metric
after refine_lines/refine_markers. --hops prints, per final line, the GT series it runs on per column
(the warped instance map at the trace) and the number of switches.
"""
from __future__ import annotations
import argparse, glob, json, math, os, sys, time
import numpy as np, cv2
sys.path.insert(0, os.getcwd())
import p2d.extract as X
from p2d.extract import extract, refine_lines, refine_markers, run_net, inv_affine
from p2d.data import apply
from p2d.metrics import score, summarise_split, LINE_KINDS, gt_curve


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt"); ap.add_argument("--data", required=True); ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--cache", required=True); ap.add_argument("--set", nargs="*", default=[])
    ap.add_argument("--hops", action="store_true"); ap.add_argument("--ids", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    for kv in a.set:
        k, v = kv.split("="); X.TRACE[k] = type(X.TRACE[k])(float(v)) if not isinstance(X.TRACE[k], int) else int(float(v))
    os.makedirs(a.cache, exist_ok=True)
    files = sorted(glob.glob(os.path.join(a.data, "*.json")))[:a.limit]
    ids = set(int(i) for i in a.ids.split(",")) if a.ids else None
    net = None
    rows = []; t_ex = 0.0
    for f in files:
        meta = json.load(open(f))
        if ids and meta["seed"] not in ids: continue
        img = cv2.imread(f[:-5] + ".png")[..., ::-1].copy()
        cf = os.path.join(a.cache, os.path.basename(f)[:-5] + ".npz")
        if os.path.exists(cf):
            z = np.load(cf); out = {k: z[k].astype(np.float32) for k in ("sem", "heat", "emb")}; M = z["M"]
        else:
            if net is None:
                from p2d.evaluate import load_net
                net = load_net(a.ckpt)
            out, M = run_net(net, img)
            np.savez(cf, sem=out["sem"].astype(np.float16), heat=out["heat"].astype(np.float16), emb=out["emb"].astype(np.float16), M=M)
        t0 = time.time()
        ex = extract(out, M, img)
        ex = refine_markers(img, refine_lines(img, ex))
        t_ex += time.time() - t0
        r = score(meta, ex, canvas_scale=math.hypot(M[0, 0], M[1, 0]))
        rows.append(r)
        if a.hops:
            inst = cv2.imread(f[:-5] + ".inst.png", cv2.IMREAD_UNCHANGED)
            H, W = inst.shape
            print(f"== {meta['seed']} n_series={len(meta['series'])} preds={len([s for s in ex.series if s.kind=='line'])} "
                  f"cov={[round(c,2) for c in r['line_cov']]} good={[round(c,2) for c in r['line_good']]}")
            for k, s in enumerate(ex.series):
                if s.kind != "line": continue
                lp = s.line_px
                xi = np.clip(np.round(lp[:, 0]).astype(int), 0, W - 1); yi = np.clip(np.round(lp[:, 1]).astype(int), 0, H - 1)
                # instance within +-2 rows
                lab = np.zeros(len(xi), int)
                for d in range(-2, 3):
                    v = inst[np.clip(yi + d, 0, H - 1), xi]
                    lab = np.where((lab == 0) & (v > 0), v, lab)
                runs = []
                cur, n = lab[0], 0
                for v in lab:
                    if v == cur: n += 1
                    else:
                        runs.append((int(cur), n)); cur, n = v, 1
                runs.append((int(cur), n))
                sw = sum(1 for (v, n) in runs if v > 0 and n >= 5) - 1
                print(f"  pred{k} cols={len(lp)} x=[{lp[0,0]:.0f},{lp[-1,0]:.0f}] on GT: " + " ".join(f"s{v-1 if v>0 else '-'}x{n}" for v, n in runs if n >= 5)
                      + (f"  <-- {sw} switches" if sw > 0 else ""))
    split = summarise_split(rows)
    s, simple = split["all"], split["simple"]
    print(f"params {X.TRACE}  extract time {t_ex/len(rows):.2f}s/chart")
    for k in ("line_found", "line_cov_mean", "line_good_cov_mean", "line_rms_median_pct", "line_rms_p90_pct", "peak_err_median_pct", "marker_recall", "marker_precision"):
        print(f"{k:28s} {s.get(k, float('nan')):10.4f} {simple.get(k, float('nan')):10.4f}")
    if a.json:
        json.dump({"summary": s, "rows": rows}, open(a.json, "w"), default=float)


if __name__ == "__main__":
    main()
