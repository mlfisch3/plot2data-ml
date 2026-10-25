"""Choosing the output sampling of a traced curve.

The default is a uniform step in x (uniform in log x on a log axis), and its
size is set by the finest feature on the curve: the coarsest step whose linear
reconstruction stays within the trace's own uncertainty everywhere. A flat
curve gets few points; one sharp spike anywhere forces a step fine enough to
keep that spike, and that step is then used for the whole curve.

The user may override it with an explicit step or count.
"""

from __future__ import annotations

import numpy as np


def reconstruction_error(x: np.ndarray, y: np.ndarray, step: float) -> float:
    """Worst |y - linear interpolation through uniform samples at `step`|."""
    g = np.arange(x[0], x[-1] + step * 0.5, step)
    if len(g) < 2:
        return float(np.max(np.abs(y - np.interp(x, [x[0], x[-1]], [y[0], y[-1]]))))
    gy = np.interp(g, x, y)
    return float(np.max(np.abs(np.interp(x, g, gy) - y)))


def auto_step(x: np.ndarray, y: np.ndarray, tol: float, min_step: float | None = None) -> float:
    """The largest uniform step whose reconstruction error is within `tol` (same units as y).

    `x` must be sorted and roughly one sample per pixel column, so the finest
    meaningful step is the column spacing; the search is a bisection over the
    step, which is close enough to monotone for this purpose, refined by a scan.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    if len(x) < 3:
        return float(x[-1] - x[0]) if len(x) == 2 else 1.0
    base = min_step if min_step is not None else float(np.median(np.diff(x)))
    span = x[-1] - x[0]
    lo, hi = base, span / 2
    if reconstruction_error(x, y, hi) <= tol:
        return hi
    for _ in range(40):
        mid = np.sqrt(lo * hi)
        if reconstruction_error(x, y, mid) <= tol:
            lo = mid
        else:
            hi = mid
        if hi / lo < 1.02:
            break
    # Errors are not strictly monotone in the step (a lucky phase can land on a
    # peak); back off until every step at or below the answer is also safe.
    s = lo
    while s > base and any(reconstruction_error(x, y, s * f) > tol for f in (0.9, 0.95)):
        s *= 0.9
    return max(s, base)


def resample(x: np.ndarray, y: np.ndarray, step: float | None = None, count: int | None = None,
             log: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """Uniform samples of the trace, by step (in x units, or decades on a log axis) or by count."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    o = np.argsort(x)
    x, y = x[o], y[o]
    t = np.log10(x) if log else x
    if count is not None:
        g = np.linspace(t[0], t[-1], max(2, count))
    else:
        g = np.arange(t[0], t[-1] + step * 1e-9, step)
    gy = np.interp(g, t, y)
    return (10 ** g if log else g), gy
