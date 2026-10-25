"""Random data for synthetic plots.

Every generator returns plain numpy arrays in data units. The shapes are chosen
to cover what turns up in the wild: smooth curves, random walks, seasonal sales
with spikes, spectra with narrow peaks, sparse polylines whose vertices are the
data, step functions, growth curves for log axes, and point clouds for scatter.
"""

from __future__ import annotations

import numpy as np


def _smooth_noise(rng: np.random.Generator, n: int, scale: float) -> np.ndarray:
    k = max(1, int(scale))
    raw = rng.normal(size=n + 2 * k)
    kernel = np.exp(-0.5 * (np.arange(-2 * k, 2 * k + 1) / k) ** 2)
    kernel /= kernel.sum()
    out = np.convolve(raw, kernel, mode="same")[k : k + n]
    return out / (out.std() + 1e-9)


def shape(rng: np.random.Generator, x01: np.ndarray, kind: str | None = None) -> tuple[str, np.ndarray]:
    """A unitless curve over x in [0, 1], roughly zero-mean and unit-scale."""
    n = len(x01)
    kinds = [
        "walk", "sines", "seasonal", "spectrum", "exp", "logistic", "poly",
        "damped", "noise", "steps", "trend_noise", "spiky_walk", "flat_then_busy",
    ]
    weights = np.array([12, 10, 8, 6, 5, 4, 5, 4, 3, 3, 8, 5, 4], dtype=float)
    if kind is None:
        kind = str(rng.choice(kinds, p=weights / weights.sum()))
    t = x01
    if kind == "walk":
        y = np.cumsum(rng.normal(size=n))
    elif kind == "sines":
        y = np.zeros(n)
        for _ in range(rng.integers(1, 4)):
            f = rng.uniform(0.3, 6) * rng.choice([1, 1, 3])
            y += rng.uniform(0.3, 1) * np.sin(2 * np.pi * f * t + rng.uniform(0, 6.3))
    elif kind == "seasonal":
        period = rng.uniform(0.02, 0.15)
        phase = rng.uniform(0, 1)
        saw = ((t + phase) / period) % 1.0
        spike = np.where(saw > 0.88, rng.uniform(1, 3), 0.0)
        y = rng.uniform(0.5, 3) * t + 0.3 * np.sin(2 * np.pi * t / period) * rng.uniform(0, 1) + spike * rng.uniform(0.2, 0.6)
        y += 0.1 * rng.normal(size=n)
    elif kind == "spectrum":
        y = 0.05 * _smooth_noise(rng, n, max(2, n / 50))
        for _ in range(rng.integers(1, 8)):
            c = rng.uniform(0.05, 0.95)
            w = rng.uniform(0.003, 0.05)
            y += rng.uniform(0.3, 3) * np.exp(-0.5 * ((t - c) / w) ** 2)
    elif kind == "exp":
        y = np.exp(rng.uniform(1, 5) * t * rng.choice([1, -1])) + 0.05 * rng.normal(size=n)
    elif kind == "logistic":
        y = 1 / (1 + np.exp(-(t - rng.uniform(0.2, 0.8)) * rng.uniform(5, 30)))
    elif kind == "poly":
        coeffs = rng.normal(size=rng.integers(2, 5))
        y = np.polyval(coeffs, 2 * t - 1)
    elif kind == "damped":
        y = np.exp(-rng.uniform(1, 6) * t) * np.cos(2 * np.pi * rng.uniform(2, 12) * t)
    elif kind == "noise":
        y = rng.normal(size=n)
    elif kind == "steps":
        k = rng.integers(2, 10)
        edges = np.sort(rng.uniform(0, 1, k))
        levels = rng.normal(size=k + 1)
        y = levels[np.searchsorted(edges, t)]
    elif kind == "trend_noise":
        y = rng.uniform(-2, 2) * t + rng.uniform(0.05, 0.5) * _smooth_noise(rng, n, rng.uniform(1, max(2, n / 20)))
    elif kind == "spiky_walk":
        y = np.cumsum(rng.normal(size=n)) * 0.3
        m = rng.random(n) < rng.uniform(0.02, 0.1)
        y = y + m * rng.normal(0, 3, size=n)
    elif kind == "flat_then_busy":
        c = rng.uniform(0.2, 0.8)
        w = rng.uniform(0.05, 0.25)
        env = np.exp(-0.5 * ((t - c) / w) ** 2)
        y = env * np.sin(2 * np.pi * rng.uniform(10, 40) * t) + 0.02 * rng.normal(size=n)
    else:
        raise ValueError(kind)
    y = np.asarray(y, dtype=float)
    span = y.max() - y.min()
    if span < 1e-9:
        y = y + 0.0
        span = 1.0
    return kind, (y - y.mean()) / span


def x_values(rng: np.random.Generator, n: int, log: bool) -> tuple[str, np.ndarray]:
    """X positions in data units, sorted, with a style of domain chosen at random."""
    if log:
        lo = rng.uniform(-3, 3)
        hi = lo + rng.uniform(1, 5)
        return "log", np.sort(10 ** np.linspace(lo, hi, n) * (1 + 0.0 * rng.random(n)))
    kind = str(rng.choice(["index", "range", "year", "neg", "small"], p=[0.2, 0.35, 0.25, 0.1, 0.1]))
    if kind == "index":
        start = rng.choice([0, 1])
        return kind, np.arange(n, dtype=float) + start
    if kind == "year":
        start = rng.integers(1900, 2020)
        span = rng.integers(5, 2030 - start + 1) if start < 2025 else 5
        return kind, np.linspace(start, start + span, n)
    if kind == "neg":
        a = rng.uniform(1, 100)
        return kind, np.linspace(-a, a * rng.uniform(0.2, 1.5), n)
    if kind == "small":
        return kind, np.linspace(0, 10.0 ** rng.integers(-4, 0) * rng.uniform(1, 9), n)
    start = 10.0 ** rng.uniform(-1, 4) * rng.choice([0, 1, 1])
    span = 10.0 ** rng.uniform(-1, 5)
    return kind, np.linspace(start, start + span, n)


def y_scale(rng: np.random.Generator, log: bool) -> tuple[float, float]:
    """(centre, span) for mapping a unit-scale curve into data units."""
    if log:
        return 0.0, 1.0
    kind = rng.choice(["unit", "pct", "big", "neg", "tiny", "mid"], p=[0.15, 0.15, 0.25, 0.15, 0.1, 0.2])
    if kind == "unit":
        return rng.uniform(0, 1), rng.uniform(0.2, 2)
    if kind == "pct":
        return rng.uniform(20, 70), rng.uniform(10, 60)
    if kind == "big":
        m = 10.0 ** rng.uniform(3, 9)
        return m * rng.uniform(0.5, 2), m * rng.uniform(0.2, 1.5)
    if kind == "neg":
        return rng.uniform(-50, 50), rng.uniform(10, 200)
    if kind == "tiny":
        m = 10.0 ** rng.uniform(-6, -2)
        return m * rng.uniform(0, 2), m
    m = 10.0 ** rng.uniform(0, 3)
    return m * rng.uniform(0, 3), m * rng.uniform(0.3, 2)
