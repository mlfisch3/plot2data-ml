"""Scoreboard ceilings: the median per-series RMS if one class of columns were exact.

    python teams/t3-precision/scripts/oracle.py out/t3/diag-base.pkl
"""
import pickle
import sys

import numpy as np

charts = pickle.load(open(sys.argv[1], "rb"))


def med_rms(sel_simple, fix):
    rms, pk = [], []
    for c in charts:
        if sel_simple and not (c["n_series"] <= 3 and c["density"] <= 0.5):
            continue
        for ln in c.get("lines", []):
            if not ln.get("matched") or "cols" not in ln or not len(ln["cols"]["x"]):
                continue
            cc = ln["cols"]
            err = (cc["ref"] - cc["gt"]).astype(float)
            ok = np.isfinite(err)
            m = fix(cc, ln, c) & ok
            err = err.copy()
            err[m] = 0.0
            if ok.any():
                rms.append(100 * np.sqrt(np.mean((err[ok] / c["ph"]) ** 2)))
    return np.median(rms)


fixes = [
    ("as is", lambda cc, ln, c: np.zeros(len(cc["x"]), bool)),
    ("columns within 1 of a vertex exact", lambda cc, ln, c: cc["dvert"] <= 1),
    ("within 3 of a vertex exact", lambda cc, ln, c: cc["dvert"] <= 3),
    ("within 8 of a vertex exact", lambda cc, ln, c: cc["dvert"] <= 8),
    ("|slope| > 4 exact", lambda cc, ln, c: np.abs(cc["slope"]) > 4),
    ("|slope| > 2 exact", lambda cc, ln, c: np.abs(cc["slope"]) > 2),
    ("net-kept columns exact", lambda cc, ln, c: np.abs(cc["ref"] - cc["raw"]) < 1e-4),
    ("gross columns (|err| > max(3, 2 lw)) exact", lambda cc, ln, c: np.abs(cc["ref"] - cc["gt"]) > np.maximum(3.0, 2.0 * ln["lw"])),
    ("|err| > 1 px exact", lambda cc, ln, c: np.abs(cc["ref"] - cc["gt"]) > 1.0),
    ("|err| > 0.5 px exact", lambda cc, ln, c: np.abs(cc["ref"] - cc["gt"]) > 0.5),
    ("|err| > 0.25 px exact", lambda cc, ln, c: np.abs(cc["ref"] - cc["gt"]) > 0.25),
]
print(f"{'oracle':48s} {'simple':>8s} {'all':>8s}   (median per-series RMS, % ph)")
for name, f in fixes:
    print(f"{name:48s} {med_rms(True, f):8.3f} {med_rms(False, f):8.3f}")
