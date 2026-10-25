"""Date tick labels: reading them, and making them for synthetic charts.

A date axis is calibrated like any other once each label is a number. Labels
are turned into days since 1970-01-01 (matplotlib's own date unit), so the
fitted mapping is linear in time. Labels that leave out the year ("Jan", "Feb")
are completed from their neighbours: months run forwards along the axis, and a
wrap from December to January is a new year.
"""

from __future__ import annotations

import datetime as dt
import re

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
EPOCH = dt.date(1970, 1, 1)


def days(y: int, m: int = 1, d: int = 1) -> float:
    return float((dt.date(y, m, d) - EPOCH).days)


def _year(s: str) -> int:
    y = int(s)
    if len(s) == 2:
        y += 2000 if y < 50 else 1900
    return y


def parse_date(text: str) -> tuple[int | None, int | None, int | None, str] | None:
    """(year, month, day, kind) or None. A missing part is None."""
    t = text.strip().lower().replace("’", "'")
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", t)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None, "iso"
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", t)
    if m:
        return int(m.group(2)), int(m.group(1)), None, "m/y"
    # A two-digit year needs its apostrophe ("Mar '12"): "Mar 12" is the twelfth of March.
    m = re.fullmatch(_MON + r"(?:\s*'(\d{2})|\s+(\d{4}))?", t)
    if m:
        mon = MONTHS.index(m.group(1)[:3]) + 1
        ys = m.group(2) or m.group(3)
        return (_year(ys) if ys else None), mon, None, "mon"
    m = re.fullmatch(r"(\d{1,2})\s+" + _MON + r"(?:\s+(\d{4}))?", t)
    if m:
        mon = MONTHS.index(m.group(2)[:3]) + 1
        return (int(m.group(3)) if m.group(3) else None), mon, int(m.group(1)), "d mon"
    m = re.fullmatch(_MON + r"\s+(\d{1,2}),?(?:\s+(\d{4}))?", t)
    if m:
        mon = MONTHS.index(m.group(1)[:3]) + 1
        return (int(m.group(3)) if m.group(3) else None), mon, int(m.group(2)), "mon d"
    m = re.fullmatch(r"q([1-4])\s*'?(\d{2}|\d{4})", t)
    if m:
        return _year(m.group(2)), 3 * (int(m.group(1)) - 1) + 1, None, "quarter"
    return None


def resolve(texts_in_axis_order: list[str]) -> list[float | None]:
    """Labels along an axis (left to right) to days since 1970, completing missing years."""
    parsed = [parse_date(t) for t in texts_in_axis_order]
    known = [p[0] for p in parsed if p and p[0] is not None]
    if not any(parsed):
        return [None] * len(texts_in_axis_order)
    # Year-less months: walk forwards from the first known year (or 2000 if none), wrapping at December.
    year = known[0] if known else 2000
    first_known = next((i for i, p in enumerate(parsed) if p and p[0] is not None), None)
    if first_known is not None:
        # Walk back from the first labelled year to seed the months before it.
        y = parsed[first_known][0]
        prev_m = parsed[first_known][1]
        for i in range(first_known - 1, -1, -1):
            p = parsed[i]
            if p is None:
                continue
            if p[1] > prev_m:
                y -= 1
            prev_m = p[1]
        year = y
    out: list[float | None] = []
    prev_m = None
    for p in parsed:
        if p is None:
            out.append(None)
            continue
        y, m, d, _ = p
        if y is not None:
            year = y
        elif prev_m is not None and m < prev_m:
            year += 1
        prev_m = m
        try:
            out.append(days(year, m or 1, d or 1))
        except ValueError:
            out.append(None)
    return out


# --- synthetic date axes -------------------------------------------------

DATE_FORMATS = [
    ("%Y", "year"), ("%b %Y", "mon"), ("%b '%y", "mon"), ("%Y-%m", "iso"), ("%b", "mon"), ("%d %b", "d mon"),
    ("%b %d", "mon d"), ("%Y-%m-%d", "iso"), ("%m/%Y", "m/y"),
]


def date_axis(rng, n: int):
    """X values in days since 1970 for a date axis, a matplotlib locator and formatter, and the format.

    The span decides which formats make sense: days for a few weeks, months for
    a few years, years beyond that.
    """
    import matplotlib.dates as mdates
    import numpy as np

    start = days(int(rng.integers(1990, 2025)), int(rng.integers(1, 13)), int(rng.integers(1, 28)))
    span_days = float(rng.choice([rng.uniform(20, 120), rng.uniform(120, 1100), rng.uniform(1100, 9000)]))
    x = start + np.linspace(0, span_days, n)
    if span_days < 120:
        fmt = str(rng.choice(["%d %b", "%b %d", "%Y-%m-%d"]))
        loc = mdates.DayLocator(interval=int(max(1, round(span_days / rng.integers(4, 9)))))
    elif span_days < 1100:
        fmt = str(rng.choice(["%b %Y", "%b '%y", "%Y-%m", "%b", "%m/%Y"]))
        loc = mdates.MonthLocator(interval=int(max(1, round(span_days / 30 / rng.integers(4, 9)))))
    else:
        fmt = str(rng.choice(["%Y", "%Y", "%b %Y", "%Y-%m"]))
        loc = mdates.YearLocator(base=int(max(1, round(span_days / 365 / rng.integers(4, 9)))))
    return x, loc, mdates.DateFormatter(fmt), fmt
