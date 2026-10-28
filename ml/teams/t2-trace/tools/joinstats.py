"""Statistics of candidate joins between chains: same series or not, versus embedding and geometric misses."""
import numpy as np, cv2, sys, os, glob, json
sys.path.insert(0, os.getcwd())
import p2d.extract as X
from p2d.data import H_LINE
cache, data, limit = sys.argv[1], sys.argv[2], int(sys.argv[3])
rows = []
for f in sorted(glob.glob(os.path.join(data, "*.json")))[:limit]:
    seed = json.load(open(f))["seed"]
    cf = f"{cache}/{seed:07d}.npz"
    if not os.path.exists(cf): continue
    z = np.load(cf); out = {k: z[k].astype(np.float32) for k in ("sem","heat","emb")}; M = z["M"]
    inst = cv2.imread(f[:-5] + ".inst.png", cv2.IMREAD_UNCHANGED)
    H, W = out["heat"].shape[1:]
    cinst = cv2.warpAffine(inst, M, (W, H), flags=cv2.INTER_NEAREST)
    lh = out["heat"][H_LINE]; emb = out["emb"]
    frame = X.plot_frame(out["heat"])
    if frame is None: continue
    fx0, fy0, fx1, fy1 = frame
    roi = np.zeros((H, W), bool); roi[max(0,int(fy0)-1):int(fy1)+3, max(0,int(fx0)-1):int(fx1)+3] = True
    ink = (lh > 0.25) & roi
    runs = X.column_runs(ink, lh, emb)
    chains = X.peel_chains(runs)
    frags = []
    for ch in chains:
        g = []
        for i in ch:
            v = cinst[max(0, runs.a[i]-1):runs.b[i]+2, runs.col[i]]; v = v[v > 0]
            g.append(int(np.bincount(v).argmax()) if len(v) else 0)
        g = np.array(g); vals, cnt = np.unique(g[g > 0], return_counts=True)
        if not len(vals): continue
        dom, pur = int(vals[cnt.argmax()]), cnt.max() / cnt.sum()
        if pur < 0.85: continue
        cols = runs.col[ch].astype(float); ys = runs.y[ch]
        frags.append({"cols": cols, "ys": ys, "embs": runs.e[ch], "gt": dom, "n": len(cols)})
    for A in frags:
        for B in frags:
            if A is B: continue
            dx = B["cols"][0] - A["cols"][-1]
            if dx > 120 or dx < -8 or B["cols"][-1] <= A["cols"][-1]: continue
            end = 10
            de = float(np.linalg.norm(A["embs"][-end:].mean(0) - B["embs"][:end].mean(0)))
            de3 = float(np.linalg.norm(A["embs"][-3:].mean(0) - B["embs"][:3].mean(0)))
            if dx > 0:
                sA = X._end_slope(A["cols"], A["ys"], min(end, len(A["cols"])), False)
                sB = X._end_slope(B["cols"], B["ys"], min(end, len(B["cols"])), True)
                ga = abs(A["ys"][-1] + sA * dx - B["ys"][0]); gb = abs(B["ys"][0] - sB * dx - A["ys"][-1])
                geo = min(ga, gb); geo2 = max(ga, gb)
                g0 = abs(A["ys"][-1] - B["ys"][0])
                sl = min(abs(sA), abs(sB))
            else:
                ov = A["cols"] >= B["cols"][0]
                geo = geo2 = g0 = float(np.abs(A["ys"][ov] - np.interp(A["cols"][ov], B["cols"], B["ys"])).max()); sl = 0
            rows.append((seed, A["gt"] == B["gt"], dx, de, de3, geo, geo2, g0, sl, A["n"], B["n"]))
r = np.array(rows, float)
same = r[:, 1] > 0.5
print(f"pairs {len(r)} same {same.sum()} diff {(~same).sum()}")
for name, col in (("de(10)", 3), ("de(3)", 4), ("geo_min", 5), ("geo_max", 6), ("y0 miss", 7)):
    v = r[:, col]
    print(f"{name:8s} same: p50 {np.median(v[same]):.2f} p75 {np.quantile(v[same],.75):.2f} p90 {np.quantile(v[same],.9):.2f} p95 {np.quantile(v[same],.95):.2f} | diff: p10 {np.quantile(v[~same],.1):.2f} p25 {np.quantile(v[~same],.25):.2f} p50 {np.median(v[~same]):.2f}")
# by dx bucket
for lo, hi in ((-8, 0), (1, 5), (6, 15), (16, 40), (41, 120)):
    sel = (r[:, 2] >= lo) & (r[:, 2] <= hi)
    s2, d2 = sel & same, sel & ~same
    if s2.sum() < 3: continue
    print(f"dx {lo}..{hi}: same {s2.sum()} diff {d2.sum()} | geo_min same p50 {np.median(r[s2,5]):.1f} p90 {np.quantile(r[s2,5],.9):.1f} diff p10 {np.quantile(r[d2,5],.1):.1f} p50 {np.median(r[d2,5]):.1f} | de same p50 {np.median(r[s2,3]):.2f} p90 {np.quantile(r[s2,3],.9):.2f} diff p10 {np.quantile(r[d2,3],.1):.2f} p50 {np.median(r[d2,3]):.2f}")
np.save("out/t2-joinstats.npy", r)
