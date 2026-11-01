"""Round-4 benchmark expansion: synthesize charts from PUBLIC data APIs.

For sources where the publisher does not serve a canonical PNG for a convenient
query (World Bank, BLS, USGS), this script pulls the raw data via the public
API, renders a chart with matplotlib, and writes the pair as a `kind: inline`
benchmark entry: `<id>.png`, `<id>.data.csv` (verbatim API response), and
`<id>.json` with the ground truth embedded under `truth`.

    python ml/teams/round4-benchmark/tools/synth_real.py --out ml/data/t5-real-ext

Styles vary across charts: different sizes, DPI, line widths, with/without
grid, with/without markers, log/linear, light/dark. The GT is exactly the
values the matplotlib chart plots (so the extractor should be able to read
them back exactly, up to pixel quantisation).
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import random
import subprocess
import sys
import time
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def curl(url: str, data: str | None = None) -> str | None:
    cmd = ["curl", "-sSL", "-m", "60", "-A", "plot2data-ml benchmark"]
    if data is not None:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", data]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  curl fail {url}: {r.stderr[:200]}", file=sys.stderr)
        return None
    return r.stdout


def wb_series(country: str, indicator: str) -> list[tuple[float, float]]:
    """Return (year, value) sorted ascending; drops nulls."""
    body = curl(f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}?format=json&per_page=200")
    if not body:
        return []
    try:
        d = json.loads(body)
    except Exception:
        return []
    if len(d) < 2 or not d[1]:
        return []
    pts = [(float(r["date"]), float(r["value"])) for r in d[1] if r.get("value") is not None]
    pts.sort()
    return pts


def bls_series(sid: str, y0: int, y1: int) -> list[tuple[float, float]]:
    """BLS public v2 API. Returns (decimal_year, value)."""
    body = curl("https://api.bls.gov/publicAPI/v2/timeseries/data/",
                data=json.dumps({"seriesid": [sid], "startyear": str(y0), "endyear": str(y1)}))
    if not body:
        return []
    try:
        d = json.loads(body)
    except Exception:
        return []
    if d.get("status") != "REQUEST_SUCCEEDED":
        return []
    series = d.get("Results", {}).get("series", [])
    if not series or not series[0].get("data"):
        return []
    out = []
    for r in series[0]["data"]:
        y = int(r["year"])
        p = r["period"]
        if p.startswith("M"):
            m = int(p[1:])
            if m < 1 or m > 12:
                continue
            frac = (m - 0.5) / 12
        elif p.startswith("Q"):
            q = int(p[1:])
            frac = (q - 0.5) / 4
        else:
            frac = 0.5
        try:
            out.append((y + frac, float(r["value"])))
        except ValueError:
            continue
    out.sort()
    return out


def plot_line(xs, ys, title, ylabel, path, size=(900, 500), dpi=100,
              marker=None, lw=1.8, grid=True, logy=False, color="#1f77b4", bg=None, fg="#222"):
    """Simple one-series line/scatter chart."""
    plt.figure(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    ax = plt.gca()
    if bg:
        plt.gcf().patch.set_facecolor(bg)
        ax.set_facecolor(bg)
    plt.plot(xs, ys, marker=marker, markersize=4, linewidth=lw, color=color)
    if logy:
        plt.yscale("log")
    if grid:
        plt.grid(True, alpha=0.3, color=fg)
    plt.title(title, color=fg)
    plt.ylabel(ylabel, color=fg)
    plt.xlabel("Year", color=fg)
    ax.tick_params(colors=fg)
    for s in ax.spines.values():
        s.set_color(fg)
    plt.tight_layout()
    plt.savefig(path, dpi=dpi, facecolor=bg or "white")
    plt.close()


def plot_multi(series, title, ylabel, path, size=(1000, 550), dpi=100, lw=1.6, grid=True, logy=False,
               colors=None, markers=None):
    """Multiple series on one plot."""
    plt.figure(figsize=(size[0] / dpi, size[1] / dpi), dpi=dpi)
    ax = plt.gca()
    for i, s in enumerate(series):
        c = colors[i] if colors else None
        m = markers[i] if markers else None
        plt.plot(s["x"], s["y"], label=s["name"], color=c, marker=m, markersize=3, linewidth=lw)
    if logy:
        plt.yscale("log")
    if grid:
        plt.grid(True, alpha=0.3)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xlabel("Year")
    plt.legend(loc="best", frameon=True)
    plt.tight_layout()
    plt.savefig(path, dpi=dpi)
    plt.close()


def write_entry(out_dir: str, chart_id: str, truth_series: list[dict], meta_extra: dict, data_csv: str) -> None:
    stem = os.path.join(out_dir, chart_id)
    with open(stem + ".data.csv", "w") as f:
        f.write(data_csv)
    meta = dict(id=chart_id, kind="inline", truth=truth_series, fetched=time.strftime("%Y-%m-%d %H:%M"), **meta_extra)
    with open(stem + ".json", "w") as f:
        json.dump(meta, f, indent=1, default=float)


def _csv_from_pairs(name: str, pairs: list[tuple[float, float]]) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["x", name])
    for x, y in pairs:
        w.writerow([x, y])
    return out.getvalue()


def _csv_from_series(series: list[dict]) -> str:
    """Multi-series CSV (ragged x unions). First column is x, one column per series."""
    xs = sorted({x for s in series for x in s["x"]})
    maps = [{xi: yi for xi, yi in zip(s["x"], s["y"])} for s in series]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["x"] + [s["name"] for s in series])
    for x in xs:
        w.writerow([x] + [m.get(x, "") for m in maps])
    return out.getvalue()


# --- Catalog ---------------------------------------------------------------


def worldbank_entries(out: str) -> list[str]:
    """World Bank-sourced charts, each a line (or line+markers) with 1 to 4 series."""
    ids: list[str] = []

    # (chart_id, title, ylabel, indicator, countries, options)
    plan = [
        ("wb-gdp-usa", "US GDP (current $)", "USD trillion", "NY.GDP.MKTP.CD", ["USA"],
         dict(size=(900, 500), scale=1e-12, lw=2.0, marker="o")),
        ("wb-gdp-5", "GDP: top-5", "USD trillion", "NY.GDP.MKTP.CD",
         ["USA", "CHN", "JPN", "DEU", "IND"], dict(size=(1100, 600), scale=1e-12, lw=1.4)),
        ("wb-gdp-log-10", "GDP log scale", "USD", "NY.GDP.MKTP.CD",
         ["USA", "CHN", "IND", "BRA", "NGA"], dict(size=(1000, 600), logy=True, lw=1.6)),
        ("wb-pop-world", "World population", "billion", "SP.POP.TOTL", ["WLD"],
         dict(size=(900, 500), scale=1e-9, lw=2.4)),
        ("wb-pop-china-india", "China vs India population", "billion", "SP.POP.TOTL",
         ["CHN", "IND"], dict(size=(1000, 500), scale=1e-9)),
        ("wb-pop-africa", "African populations", "million", "SP.POP.TOTL",
         ["NGA", "ETH", "EGY", "ZAF"], dict(size=(1000, 600), scale=1e-6)),
        ("wb-inflation-us", "US inflation (CPI YoY %)", "percent", "FP.CPI.TOTL.ZG", ["USA"],
         dict(size=(900, 500), lw=1.6, grid=False)),
        ("wb-inflation-emerging", "Inflation (CPI YoY)", "percent", "FP.CPI.TOTL.ZG",
         ["BRA", "RUS", "TUR", "ARG"], dict(size=(1100, 550), lw=1.4)),
        ("wb-life-exp-eu", "Life expectancy, EU-5", "years", "SP.DYN.LE00.IN",
         ["DEU", "FRA", "ITA", "ESP", "GBR"], dict(size=(1000, 500), lw=1.5, marker="o")),
        ("wb-life-exp-world", "World life expectancy", "years", "SP.DYN.LE00.IN", ["WLD"],
         dict(size=(900, 500), lw=2.4, marker="s")),
        ("wb-co2-per-cap-oecd", "CO2 per capita", "t per capita", "EN.ATM.CO2E.PC",
         ["USA", "CAN", "AUS", "DEU"], dict(size=(1000, 550), lw=1.6)),
        ("wb-forest-share", "Forest area share", "percent", "AG.LND.FRST.ZS",
         ["BRA", "IDN", "COD", "RUS"], dict(size=(1100, 550), lw=1.6)),
    ]

    for row in plan:
        cid, title, ylabel, ind, countries, opts = row
        series_data = []
        for c in countries:
            pts = wb_series(c, ind)
            if not pts:
                print(f"  wb empty {c} {ind}", file=sys.stderr)
                continue
            # Trim to 1960..latest.
            pts = [(x, y) for x, y in pts if x >= 1960]
            if "scale" in opts:
                pts = [(x, y * opts["scale"]) for x, y in pts]
            series_data.append({"name": c, "x": [x for x, _ in pts], "y": [y for _, y in pts]})
            time.sleep(0.2)
        if not series_data:
            continue
        png = os.path.join(out, cid + ".png")
        if len(series_data) == 1:
            s = series_data[0]
            plot_line(s["x"], s["y"], title, ylabel, png,
                      size=opts.get("size", (900, 500)),
                      marker=opts.get("marker"),
                      lw=opts.get("lw", 1.6),
                      grid=opts.get("grid", True),
                      logy=opts.get("logy", False))
        else:
            plot_multi(series_data, title, ylabel, png,
                       size=opts.get("size", (1000, 550)),
                       lw=opts.get("lw", 1.6),
                       grid=opts.get("grid", True),
                       logy=opts.get("logy", False))
        write_entry(out, cid, series_data,
                    dict(source="worldbank", indicator=ind, countries=countries, title=title),
                    _csv_from_series(series_data))
        ids.append(cid)
        print(f"synth {cid} ({len(series_data)}x)")
    return ids


def bls_entries(out: str) -> list[str]:
    """BLS public v2 API: US labor statistics."""
    ids: list[str] = []
    # (chart_id, title, series_label, series_id, year range, opts)
    plan = [
        ("bls-unrate-15y", "US unemployment rate", "UNRATE", "LNS14000000", (2010, 2024),
         dict(size=(1100, 500), lw=1.8)),
        ("bls-unrate-women", "Unemployment: women 20+", "UNRATE women", "LNS14000026", (2000, 2024),
         dict(size=(1000, 550), lw=1.6)),
        ("bls-unrate-teens", "Unemployment: 16-19", "teens", "LNS14000012", (2000, 2024),
         dict(size=(1000, 500), lw=1.4, marker="x")),
        ("bls-labor-force", "Civilian labor force participation (%)", "LFPR", "LNS11300000", (1990, 2024),
         dict(size=(1100, 550), lw=1.8)),
        ("bls-cpi-u", "US CPI-U index", "CPI", "CUUR0000SA0", (2000, 2024),
         dict(size=(1100, 550), lw=1.6)),
        ("bls-cpi-food", "CPI food index", "CPI food", "CUUR0000SAF1", (2005, 2024),
         dict(size=(1000, 500), lw=1.6)),
        ("bls-cpi-energy", "CPI energy index", "CPI energy", "CUUR0000SA0E", (2005, 2024),
         dict(size=(1000, 500), lw=1.6)),
        ("bls-payems-recent", "US nonfarm payrolls", "payrolls (K)", "CES0000000001", (2015, 2024),
         dict(size=(1100, 550), lw=1.6, scale=1.0)),
    ]
    for cid, title, label, sid, (y0, y1), opts in plan:
        pts = bls_series(sid, y0, y1)
        if not pts:
            print(f"  bls empty {sid}", file=sys.stderr)
            continue
        xs = [x for x, _ in pts]
        ys = [y * opts.get("scale", 1.0) for _, y in pts]
        series = [{"name": label, "x": xs, "y": ys}]
        png = os.path.join(out, cid + ".png")
        plot_line(xs, ys, title, label, png,
                  size=opts.get("size", (900, 500)),
                  marker=opts.get("marker"),
                  lw=opts.get("lw", 1.6),
                  grid=opts.get("grid", True),
                  logy=opts.get("logy", False))
        write_entry(out, cid, series,
                    dict(source="bls", series_id=sid, title=title),
                    _csv_from_series(series))
        ids.append(cid)
        print(f"synth {cid}")
        time.sleep(0.4)
    return ids


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ml/data/t5-real-ext")
    ap.add_argument("--only", choices=["wb", "bls", "all"], default="all")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    random.seed(0)
    done = []
    if a.only in ("wb", "all"):
        done += worldbank_entries(a.out)
    if a.only in ("bls", "all"):
        done += bls_entries(a.out)
    print(f"\nsynthesized {len(done)}")


if __name__ == "__main__":
    main()
