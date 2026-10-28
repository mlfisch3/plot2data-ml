"""Print the links of the first chains where the true series id changes (hops or fused ridges)."""
import numpy as np, cv2, json, sys, os
sys.path.insert(0, os.getcwd())
import p2d.extract as X
from p2d.data import H_LINE
seed, cache = int(sys.argv[1]), sys.argv[2]
nchains = int(sys.argv[3]) if len(sys.argv) > 3 else 4
z = np.load(f"{cache}/{seed:07d}.npz"); out = {k: z[k].astype(np.float32) for k in ("sem","heat","emb")}; M = z["M"]
inst = cv2.imread(f"data/mpl-val/{seed:07d}.inst.png", cv2.IMREAD_UNCHANGED)
H, W = out["heat"].shape[1:]
cinst = cv2.warpAffine(inst, M, (W, H), flags=cv2.INTER_NEAREST)
lh = out["heat"][H_LINE]; emb = out["emb"]
frame = X.plot_frame(out["heat"]); fx0, fy0, fx1, fy1 = frame
roi = np.zeros((H, W), bool); roi[max(0,int(fy0)-1):int(fy1)+3, max(0,int(fx0)-1):int(fx1)+3] = True
ink = (lh > 0.25) & roi
T = X.TRACE
runs = X.column_runs(ink, lh, emb, split_thr=T["split_thr"])
print("runs", len(runs), "cols", len(set(r.col for r in runs)))
def gid(r):
    v = cinst[max(0,r.a-1):r.b+2, r.col]; v = v[v>0]
    return int(np.bincount(v).argmax()) if len(v) else 0
chains = X.peel_chains(runs, gap_pen=T["gap_pen"], skip_pen=T["skip_pen"], emb_pen=T["emb_pen"], emb_max=T["emb_max"], max_skip=T["max_skip"])
for ci, ch in enumerate(chains[:nchains]):
    g = [gid(r) for r in ch]
    sw = [i for i in range(1, len(g)) if g[i] != g[i-1] and g[i] > 0 and g[i-1] > 0]
    print(f"chain {ci} len {len(ch)} cols {ch[0].col}-{ch[-1].col} switches {len(sw)}  gt ids: {np.unique(g).tolist()}")
    for i in sw[:14]:
        p, c = ch[i-1], ch[i]
        de = np.linalg.norm(p.e - c.e)
        gap = max(0, c.a - p.b - 1, p.a - c.b - 1)
        alt = [r for r in runs if r.col == c.col and gid(r) == g[i-1] and r is not c]
        alt_s = ", ".join(f"y={r.y:.1f} de={np.linalg.norm(p.e - r.e):.2f} h={r.b-r.a+1}" for r in alt)
        print(f"  col {p.col}->{c.col} gt {g[i-1]}->{g[i]}  prev y={p.y:.1f} h={p.b-p.a+1} m={p.m:.1f} | cur y={c.y:.1f} h={c.b-c.a+1} m={c.m:.1f} de={de:.2f} gap={gap}  alt: {alt_s}")
