"""Fetch the real-chart benchmark: chart images and the published data behind them.

    python teams/t5-robust/tools/fetch_real.py --out data/t5-real

Sources (all give the image and the data from the same query, so the image is
drawn from exactly the numbers in the file):

- Our World in Data grapher: `/grapher/<slug>.png?...` and `.csv?...&csvType=filtered`
  (D3/SVG rendering, 850 x 600, entity labels at line ends, "80 years" style labels).
- FRED: `/graph/fredgraph.png?id=...` and `fredgraph.csv?id=...` (server-rendered,
  recession bands, legend on top; width, height, line width, log axes, colours
  and date ranges are URL options).
- NASA GISS and NOAA GML: fixed PNG + CSV pairs for their headline graphs.

Everything downloaded is untrusted data: it is written as files and read by the
loader with plain parsers, never executed. Each chart gets `<id>.png`,
`<id>.data.csv` (verbatim) and `<id>.json` (source, series mapping, options).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

OWID = "https://ourworldindata.org/grapher/{slug}.{ext}?tab=chart{q}"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.{ext}?id={ids}{q}"

# id, kind, slug/ids, query options (image only / both), notes
MANIFEST: list[dict] = [
    # --- Our World in Data (D3) ---
    dict(id="owid-life-expectancy-gbr", kind="owid", slug="life-expectancy", q="&country=~GBR", notes="one line with a dot per point, 1543..2023"),
    dict(id="owid-life-expectancy-4", kind="owid", slug="life-expectancy", q="&country=~GBR~JPN~IND~NGA&time=1900..latest", notes="4 lines, end labels"),
    dict(id="owid-gdp-per-capita-log", kind="owid", slug="gdp-per-capita-worldbank", q="&country=~USA~CHN~IND~NGA&yScale=log", notes="log y, 4 lines"),
    dict(id="owid-co2-per-capita", kind="owid", slug="co2-emissions-per-capita", q="&country=~USA~GBR~CHN~IND&time=1900..latest", notes="4 lines"),
    dict(id="owid-child-mortality", kind="owid", slug="child-mortality", q="&country=~OWID_WRL~IND~BRA", notes="percent labels"),
    dict(id="owid-population-3", kind="owid", slug="population", q="&country=~CHN~IND~USA&time=1800..latest", notes="labels like 1 billion"),
    dict(id="owid-renewables", kind="owid", slug="share-electricity-renewables", q="&country=~DEU~GBR~USA~CHN", notes="percent"),
    dict(id="owid-solar-pv", kind="owid", slug="solar-pv-prices", q="&yScale=log", notes="log y, dollars"),
    dict(id="owid-energy-per-capita", kind="owid", slug="energy-use-per-capita", q="&country=~USA~CHN~IND", notes="kWh labels"),
    dict(id="owid-internet", kind="owid", slug="share-of-individuals-using-the-internet", q="&country=~USA~IND~NGA~BRA", notes="percent"),
    dict(id="owid-annual-co2-log", kind="owid", slug="annual-co2-emissions-per-country", q="&country=~CHN~USA~IND~DEU&yScale=log&time=1900..latest", notes="log y, billion t"),
    dict(id="owid-military", kind="owid", slug="military-spending-sipri", q="&country=~USA~CHN~RUS", notes="dollars"),
    # --- FRED ---
    dict(id="fred-unrate", kind="fred", ids="UNRATE", q="", notes="default 1024x623, recession bands"),
    dict(id="fred-cpiaucsl-2000", kind="fred", ids="CPIAUCSL", q="&cosd=2000-01-01&coed=2025-06-01&width=800&height=500", notes="index"),
    dict(id="fred-gdp-log", kind="fred", ids="GDP", q="&log_scales=Left&width=900&height=500", notes="log y, billions"),
    dict(id="fred-fedfunds-small", kind="fred", ids="FEDFUNDS", q="&cosd=2005-01-01&coed=2024-12-01&width=600&height=380", notes="small"),
    dict(id="fred-dgs10-daily", kind="fred", ids="DGS10", q="&cosd=2010-01-01&width=1200&height=700", notes="daily, dense"),
    dict(id="fred-sp500", kind="fred", ids="SP500", q="&width=900&height=450&lw=1", notes="daily, thin line"),
    dict(id="fred-houst-thick", kind="fred", ids="HOUST", q="&width=700&height=420&lw=3&recession_bars=off", notes="thick line, no bands"),
    dict(id="fred-m2sl-log", kind="fred", ids="M2SL", q="&log_scales=Left&width=1000&height=600", notes="log y"),
    dict(id="fred-oil-2015", kind="fred", ids="DCOILWTICO", q="&cosd=2015-01-01&width=1000&height=500", notes="daily"),
    dict(id="fred-payems", kind="fred", ids="PAYEMS", q="&width=1100&height=600", notes="thousands, 160,000 labels"),
    dict(id="fred-t10y2y", kind="fred", ids="T10Y2Y", q="&cosd=2000-01-01&width=900&height=500", notes="negative values"),
    dict(id="fred-unrate-civpart", kind="fred", ids="UNRATE,CIVPART", q="&cosd=1980-01-01&width=900&height=500", notes="two series"),
    dict(id="fred-mortgage-tiny", kind="fred", ids="MORTGAGE30US", q="&width=480&height=300&ts=8", notes="tiny, small font"),
    dict(id="fred-unrate-dark", kind="fred", ids="UNRATE", q="&cosd=1990-01-01&bgcolor=%23131722&graph_bgcolor=%23131722&txtcolor=%23d1d4dc&lc=%232962ff&width=900&height=500", notes="dark theme"),
    dict(id="fred-cpi-two", kind="fred", ids="CPIAUCSL,CPILFESL", q="&cosd=2010-01-01&width=1000&height=550&recession_bars=off", notes="two close series"),
    dict(id="fred-dexuseu", kind="fred", ids="DEXUSEU", q="&width=800&height=480&ts=14", notes="daily, bigger font"),
    # --- NASA GISS and NOAA ---
    dict(id="giss-global-mean", kind="giss", png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Global_Mean_Estimates_based_on_Land_and_Ocean_Data/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Global_Mean_Estimates_based_on_Land_and_Ocean_Data/graph.csv", notes="two series, 1130x600"),
    dict(id="giss-land-ocean", kind="giss", png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Temperature_Anomalies_over_Land_and_over_Ocean/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Temperature_Anomalies_over_Land_and_over_Ocean/graph.csv", notes="land and ocean"),
    dict(id="noaa-co2-mlo", kind="noaa", png="https://gml.noaa.gov/webdata/ccgg/trends/co2_data_mlo.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv", notes="monthly mean and trend, 800x600"),
    dict(id="noaa-ch4-global", kind="noaa", png="https://gml.noaa.gov/webdata/ccgg/trends/ch4/ch4_trend_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/ch4/ch4_mm_gl.csv", notes="methane"),
]


def urls(m: dict) -> tuple[str, str]:
    if m["kind"] == "owid":
        return (OWID.format(slug=m["slug"], ext="png", q=m["q"]), OWID.format(slug=m["slug"], ext="csv", q=m["q"] + "&csvType=filtered"))
    if m["kind"] == "fred":
        return (FRED.format(ids=m["ids"], ext="png", q=m["q"]), FRED.format(ids=m["ids"], ext="csv", q=m["q"]))
    return m["png"], m["csv"]


def fetch(url: str, path: str) -> bool:
    r = subprocess.run(["curl", "-sS", "-L", "-m", "60", "-A", "plot2data-ml benchmark fetch", "-o", path, "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    ok = r.returncode == 0 and r.stdout.strip() == "200" and os.path.getsize(path) > 500
    if not ok:
        print(f"  failed {url}: {r.stdout.strip()} {r.stderr.strip()[:100]}", file=sys.stderr)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/t5-real")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for m in MANIFEST:
        if a.only and m["id"] not in a.only:
            continue
        png, csv = urls(m)
        stem = os.path.join(a.out, m["id"])
        if os.path.exists(stem + ".json") and not a.force:
            continue
        print(m["id"], flush=True)
        if not (fetch(png, stem + ".png") and fetch(csv, stem + ".data.csv")):
            for ext in (".png", ".data.csv"):
                if os.path.exists(stem + ext):
                    os.remove(stem + ext)
            continue
        with open(stem + ".json", "w") as f:
            json.dump(dict(m, png_url=png, csv_url=csv, fetched=time.strftime("%Y-%m-%d %H:%M")), f, indent=1)
        time.sleep(1.0)


if __name__ == "__main__":
    main()
