"""For each chain of a chart: its true series, and why it ended (the candidates it refused at its last column)."""
import numpy as np, cv2, sys, os, json
sys.path.insert(0, os.getcwd())
import p2d.extract as X
from p2d.data import H_LINE, apply
from p2d.evaluate import draw
seed, cache = int(sys.argv[1]), sys.argv[2]
data = sys.argv[3] if len(sys.argv) > 3 else "data/mpl-val"
z = np.load(f"{cache}/{seed:07d}.npz"); out = {k: z[k].astype(np.float32) for k in ("sem","heat","emb")}; M = z["M"]
inst = cv2.imread(f"{data}/{seed:07d}.inst.png", cv2.IMREAD_UNCHANGED)
meta = json.load(open(f"{data}/{seed:07d}.json"))
H, W = out["heat"].shape[1:]
cinst = cv2.warpAffine(inst, M, (W, H), flags=cv2.INTER_NEAREST)
lh = out["heat"][H_LINE]; emb = out["emb"]
frame = X.plot_frame(out["heat"]); fx0, fy0, fx1, fy1 = frame
roi = np.zeros((H, W), bool); roi[max(0,int(fy0)-1):int(fy1)+3, max(0,int(fx0)-1):int(fx1)+3] = True
ink = (lh > 0.25) & roi
T = X.TRACE
runs = X.column_runs(ink, lh, emb, split_thr=T["split_thr"])
chains = X.peel_chains(runs, gap_pen=T["gap_pen"], skip_pen=T["skip_pen"], emb_pen=T["emb_pen"], emb_max=T["emb_max"], track_max=T["track_max"], share_pen=T["share_pen"], max_skip=T["max_skip"])
def gid(i):
    v = cinst[max(0, runs.a[i]-1):runs.b[i]+2, runs.col[i]]; v = v[v > 0]
    return int(np.bincount(v).argmax()) if len(v) else 0
print(f"{seed}: {len(meta['series'])} series, kinds {[s['kind'] for s in meta['series']]}, lw {[round(s['linewidth_px'],1) for s in meta['series']]}, ls {[s['linestyle'] for s in meta['series']]}")
pa = apply(M, [[meta['plot_area'][0], meta['plot_area'][1]], [meta['plot_area'][2], meta['plot_area'][3]]])
print(f"plot canvas x {pa[0,0]:.0f}-{pa[1,0]:.0f} y {pa[0,1]:.0f}-{pa[1,1]:.0f}")
owner = np.full(len(runs), -1)
for ci, ch in enumerate(chains): owner[ch] = ci
for ci, ch in enumerate(chains):
    g = np.array([gid(i) for i in ch]); vals, cnt = np.unique(g[g > 0], return_counts=True)
    dom = int(vals[cnt.argmax()]) if len(vals) else 0; pur = cnt.max()/cnt.sum() if len(vals) else 0
    last = ch[-1]; c = runs.col[last]
    # candidates in the next 12 columns
    cand = np.nonzero((runs.col > c) & (runs.col <= c + T["max_skip"]))[0]
    msg = []
    for k in cand:
        if gid(k) != dom: continue
        gap = max(0, runs.a[k] - runs.b[last] - 1, runs.a[last] - runs.b[k] - 1)
        skip = runs.col[k] - c - 1
        de = np.linalg.norm(runs.e[last] - runs.e[k])
        gmax = 2.0 + skip * (2.0 + max(runs.b[last]-runs.a[last]+1, runs.b[k]-runs.a[k]+1))
        msg.append(f"col+{skip+1} y={runs.y[k]:.0f} de={de:.1f}{'!' if de > T['emb_max'] else ''} gap={gap}{'!' if gap > gmax else ''} owner={owner[k]}")
        if len(msg) >= 3: break
    hs = runs.b[ch] - runs.a[ch] + 1
    print(f"chain {ci:2d} cols {runs.col[ch[0]]:4d}-{c:4d} n={len(ch):4d} gt s{dom-1} pur {pur:.2f} y_end={runs.y[last]:.0f} h_end={hs[-1]} h_med={np.median(hs):.0f} | next same-series runs: " + "; ".join(msg))
# draw chains on the canvas
img = cv2.imread(f"{data}/{seed:07d}.png")[..., ::-1].copy()
cimg = cv2.warpAffine(img, M, (W, H))
vis = (cimg.astype(np.float32) * 0.4 + 255 * 0.6).astype(np.uint8)
rng = np.random.default_rng(1)
for ci, ch in enumerate(chains):
    colr = tuple(int(v) for v in rng.integers(0, 200, 3))
    pts = np.column_stack([runs.col[ch], runs.y[ch]])
    cv2.polylines(vis, [np.round(pts * 4).astype(np.int32)], False, colr, 1, cv2.LINE_AA, shift=2)
    cv2.putText(vis, str(ci), (int(pts[0,0]), int(pts[0,1])), cv2.FONT_HERSHEY_SIMPLEX, 0.35, colr, 1)
os.makedirs("out/t2-chains", exist_ok=True)
cv2.imwrite(f"out/t2-chains/{seed}.png", vis[..., ::-1])
