"""Axis calibration: pixel position <-> value, from ticks whose labels were read.

A least-squares fit over every tick that agrees, not two chosen ticks: real
charts round their printed values, and one misread label must not move the
axis. Agreement is judged in pixels, by RANSAC over pairs of ticks. Linear and
log are both fitted and the one that explains more ticks wins.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

import numpy as np


@dataclass
class AxisFit:
    scale: str  # "linear" | "log"
    a: float  # value-space = a + b * pos  (value-space is log10(value) on a log axis)
    b: float
    inliers: int
    used: int
    resid_px: float
    warnings: list[str]

    def to_value(self, pos):
        t = self.a + self.b * np.asarray(pos, float)
        return 10 ** t if self.scale == "log" else t

    def to_pos(self, value):
        v = np.asarray(value, float)
        t = np.log10(np.where(v > 0, v, np.nan)) if self.scale == "log" else v
        return (t - self.a) / self.b


def _ransac(pos: np.ndarray, t: np.ndarray, tol_px: float) -> tuple[float, float, np.ndarray] | None:
    n = len(pos)
    best = None
    for i, j in itertools.combinations(range(n), 2):
        if abs(pos[i] - pos[j]) < 3 or t[i] == t[j]:
            continue
        b = (t[j] - t[i]) / (pos[j] - pos[i])
        a = t[i] - b * pos[i]
        err = np.abs((t - a) / b - pos)
        inl = err <= tol_px
        key = (inl.sum(), -err[inl].sum())
        if best is None or key > best[0]:
            best = (key, inl)
    if best is None:
        return None
    inl = best[1]
    A = np.column_stack([np.ones(inl.sum()), pos[inl]])
    (a, b), *_ = np.linalg.lstsq(A, t[inl], rcond=None)
    return float(a), float(b), inl


def fit_axis(pos, values, texts=None, tol_px: float = 3.0, hint: str | None = None) -> AxisFit | None:
    pos = np.asarray(pos, float)
    vals = np.asarray(values, float)
    ok = np.isfinite(pos) & np.isfinite(vals)
    pos, vals = pos[ok], vals[ok]
    texts = [t for t, k in zip(texts or [""] * len(ok), ok) if k]
    if len(pos) < 2:
        return None
    cands = []
    lin = _ransac(pos, vals, tol_px)
    if lin:
        cands.append(("linear", lin))
    pos_ok = vals > 0
    # A log axis spans at least a decade, or says so on its labels: over a narrow range (years
    # 1970 to 2021) a log fit bends just enough to take in a misplaced label and would win.
    says_log = hint == "log" or any("^" in t for t in (texts or []))
    if pos_ok.sum() >= 2 and (says_log or vals[pos_ok].max() / vals[pos_ok].min() >= 10):
        # A log axis is fitted on the positive labels; a stray "0" misread is just an outlier.
        lg = _ransac(pos[pos_ok], np.log10(vals[pos_ok]), tol_px)
        if lg:
            a_, b_, inl_ = lg
            inl = np.zeros(len(pos), bool)
            inl[np.nonzero(pos_ok)[0]] = inl_
            cands.append(("log", (a_, b_, inl)))
    if not cands:
        return None

    def resid(scale, a, b, inl):
        with np.errstate(invalid="ignore", divide="ignore"):
            t = np.log10(np.where(vals > 0, vals, np.nan)) if scale == "log" else vals
        return float(np.sqrt(np.mean(((t[inl] - a) / b - pos[inl]) ** 2)))

    warnings: list[str] = []
    scored = [(scale, a, b, inl, int(inl.sum()), resid(scale, a, b, inl)) for scale, (a, b, inl) in cands]
    scored.sort(key=lambda s: (-s[4], s[5]))
    best = scored[0]
    if len(scored) == 2 and scored[0][4] == scored[1][4]:
        # Both explain every tick, as any two ticks do: decide on the labels.
        pow10 = all(v > 0 and abs(math.log10(v) - round(math.log10(v))) < 1e-9 for v in vals)
        ratio = vals.max() / vals.min() if np.all(vals > 0) else 0
        looks_log = hint == "log" or any("^" in t for t in texts) or (pow10 and ratio >= 100)
        if scored[0][4] <= 2 or abs(scored[0][5] - scored[1][5]) < 0.3:
            best = next(s for s in scored if s[0] == ("log" if looks_log else "linear"))
            if scored[0][4] <= 2:
                warnings.append("only two ticks read: linear/log decided from the labels")
    scale, a, b, inl, n_in, r = best
    if n_in < len(pos):
        warnings.append(f"{len(pos) - n_in} tick label(s) disagreed with the rest and were ignored")
    return AxisFit(scale=scale, a=a, b=b, inliers=n_in, used=len(pos), resid_px=r, warnings=warnings)
