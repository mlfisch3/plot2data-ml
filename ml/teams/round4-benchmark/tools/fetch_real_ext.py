"""Round-4 benchmark expansion: fetch 50+ more real-published charts.

Mirrors `teams/t5-robust/tools/fetch_real.py`: for each chart in the manifest
below, pulls the publisher's PNG and the data CSV for the same query. The pair
is written as `<id>.png` / `<id>.data.csv` with a `<id>.json` metadata file so
`p2d.eval_t5real` can score it. All downloads are untrusted data.

    python ml/teams/round4-benchmark/tools/fetch_real_ext.py --out ml/data/t5-real-ext

Sources (all public):
- FRED (fredgraph.png + fredgraph.csv): economic time series.
- OWID grapher (D3-rendered PNG + filtered CSV): international indicators.
- NASA GISS graphs_v4: fixed PNG + CSV pairs.
- NOAA GML trends: CO2, CH4, N2O, SF6 monthly/annual series.
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


MANIFEST: list[dict] = [
    # --- FRED (30) ---
    dict(id="fred-dgs2-2010", kind="fred", ids="DGS2", q="&cosd=2010-01-01&width=1000&height=600", notes="2-year treasury daily"),
    dict(id="fred-dgs30-full", kind="fred", ids="DGS30", q="&width=1100&height=600", notes="30-year treasury daily"),
    dict(id="fred-dff-2000", kind="fred", ids="DFF", q="&cosd=2000-01-01&width=900&height=500", notes="daily fed funds"),
    dict(id="fred-tb3ms-small", kind="fred", ids="TB3MS", q="&cosd=1970-01-01&width=700&height=420", notes="3-month T-bill"),
    dict(id="fred-walcl-log", kind="fred", ids="WALCL", q="&log_scales=Left&width=1000&height=500", notes="Fed balance sheet log"),
    dict(id="fred-bogmbase", kind="fred", ids="BOGMBASE", q="&cosd=1980-01-01&width=1000&height=550", notes="monetary base"),
    dict(id="fred-pcepi", kind="fred", ids="PCEPI", q="&cosd=2000-01-01&width=900&height=500", notes="PCE price index"),
    dict(id="fred-mich-infl", kind="fred", ids="MICH", q="&cosd=1980-01-01&width=900&height=500", notes="inflation expectations"),
    dict(id="fred-drccl-cards", kind="fred", ids="DRCCLACBS", q="&width=900&height=500", notes="credit card delinquency"),
    dict(id="fred-t10y3m-recess", kind="fred", ids="T10Y3M", q="&cosd=1990-01-01&width=1100&height=600", notes="recession spread"),
    dict(id="fred-recprous", kind="fred", ids="RECPROUSM156N", q="&width=900&height=500", notes="recession probability"),
    dict(id="fred-awhman-thick", kind="fred", ids="AWHMAN", q="&width=800&height=500&lw=3", notes="avg hours thick"),
    dict(id="fred-sp500-small", kind="fred", ids="SP500", q="&width=500&height=320&ts=10", notes="S&P500 tiny"),
    dict(id="fred-sp500-5y", kind="fred", ids="SP500", q="&cosd=2020-01-01&width=1200&height=700&lw=2", notes="S&P 5-year wide"),
    dict(id="fred-oil-full", kind="fred", ids="DCOILWTICO", q="&width=1100&height=600", notes="oil full history"),
    dict(id="fred-houst-2010", kind="fred", ids="HOUST", q="&cosd=2010-01-01&width=1000&height=500", notes="housing starts recent"),
    dict(id="fred-unrate-dark2", kind="fred", ids="UNRATE", q="&cosd=1960-01-01&bgcolor=%231a1a1a&graph_bgcolor=%231a1a1a&txtcolor=%23ffffff&lc=%2300ff88&width=1100&height=550", notes="dark theme green"),
    dict(id="fred-dgs10-dgs2", kind="fred", ids="DGS10,DGS2", q="&cosd=2000-01-01&width=1100&height=600", notes="two yields"),
    dict(id="fred-m2sl-full", kind="fred", ids="M2SL", q="&width=1200&height=600", notes="M2 money supply full"),
    dict(id="fred-cpi-cpifood", kind="fred", ids="CPIAUCSL,CPIFABSL", q="&cosd=1980-01-01&width=1100&height=600&recession_bars=off", notes="CPI vs food CPI"),
    dict(id="fred-unemp-black-white", kind="fred", ids="LNS14000003,LNS14000006", q="&cosd=1972-01-01&width=1100&height=600", notes="unemployment by race"),
    dict(id="fred-indpro-wide", kind="fred", ids="INDPRO", q="&cosd=1950-01-01&width=1300&height=600", notes="industrial production"),
    dict(id="fred-tcu-caputil", kind="fred", ids="TCU", q="&cosd=1970-01-01&width=1000&height=500", notes="capacity utilization"),
    dict(id="fred-retail-wide", kind="fred", ids="RSXFS", q="&cosd=2000-01-01&width=1100&height=600", notes="retail sales"),
    dict(id="fred-permit-houses", kind="fred", ids="PERMIT", q="&cosd=1990-01-01&width=1000&height=500", notes="building permits"),
    dict(id="fred-ngdp-realgdp", kind="fred", ids="GDP,GDPC1", q="&cosd=1970-01-01&width=1100&height=600&log_scales=Left", notes="nominal vs real GDP log"),
    dict(id="fred-dpoilbrent", kind="fred", ids="DCOILBRENTEU", q="&cosd=2000-01-01&width=1000&height=500", notes="Brent crude"),
    dict(id="fred-dcoilwti-dcoilbrent", kind="fred", ids="DCOILWTICO,DCOILBRENTEU", q="&cosd=2010-01-01&width=1100&height=550", notes="WTI vs Brent"),
    dict(id="fred-nasdaq", kind="fred", ids="NASDAQCOM", q="&cosd=2000-01-01&width=1100&height=600&lw=1", notes="NASDAQ composite"),
    dict(id="fred-vix", kind="fred", ids="VIXCLS", q="&cosd=2007-01-01&width=1100&height=550", notes="VIX volatility"),

    # --- OWID (20) ---
    dict(id="owid-co-emissions-per-capita", kind="owid", slug="co-emissions-per-capita", q="&country=~USA~CHN~IND~GBR&time=1900..latest", notes="per-capita CO2 four countries"),
    dict(id="owid-crude-death-rate", kind="owid", slug="crude-death-rate", q="&country=~GBR~JPN~CHN", notes="death rate three countries"),
    dict(id="owid-crude-birth-rate", kind="owid", slug="crude-birth-rate", q="&country=~GBR~JPN~CHN~NGA", notes="birth rate four countries"),
    dict(id="owid-share-poverty", kind="owid", slug="share-of-population-living-in-extreme-poverty", q="&country=~CHN~IND~OWID_WRL", notes="extreme poverty share"),
    dict(id="owid-fertility-rate", kind="owid", slug="children-born-per-woman", q="&country=~USA~CHN~IND~NGA", notes="fertility rate"),
    dict(id="owid-urban-share", kind="owid", slug="share-of-population-urban", q="&country=~USA~CHN~IND~NGA", notes="urban population share"),
    dict(id="owid-life-expectancy-many", kind="owid", slug="life-expectancy", q="&country=~USA~JPN~RUS~ZAF~IND", notes="life expectancy five countries"),
    dict(id="owid-gdp-per-cap-5", kind="owid", slug="gdp-per-capita-worldbank", q="&country=~USA~CHN~IND~DEU~JPN&yScale=log", notes="log GDP per capita five"),
    dict(id="owid-cumulative-co2", kind="owid", slug="cumulative-co-emissions", q="&country=~USA~CHN~GBR~DEU", notes="cumulative CO2"),
    dict(id="owid-ghg-emissions", kind="owid", slug="total-ghg-emissions", q="&country=~USA~CHN~IND~OWID_EU28", notes="GHG emissions four"),
    dict(id="owid-energy-mix", kind="owid", slug="electricity-production-by-source", q="&country=~USA&stackMode=absolute", notes="US electricity by source"),
    dict(id="owid-share-elec-renew", kind="owid", slug="share-electricity-renewables", q="&country=~OWID_WRL~DEU~CHN", notes="renewables share"),
    dict(id="owid-primary-energy", kind="owid", slug="primary-energy-cons", q="&country=~USA~CHN~IND&yScale=log", notes="primary energy log"),
    dict(id="owid-maternal-mortality", kind="owid", slug="maternal-mortality", q="&country=~USA~GBR~JPN~IND", notes="maternal mortality"),
    dict(id="owid-share-ren-energy", kind="owid", slug="renewable-share-energy", q="&country=~DEU~GBR~OWID_WRL", notes="renewable share of energy"),
    dict(id="owid-share-urban-single", kind="owid", slug="share-of-population-urban", q="&country=~OWID_WRL", notes="world urban share single"),
    dict(id="owid-gdp-per-cap-us", kind="owid", slug="gdp-per-capita-worldbank", q="&country=~USA", notes="US GDP per cap single"),
    dict(id="owid-child-mort-world", kind="owid", slug="child-mortality", q="&country=~OWID_WRL", notes="world child mortality"),
    dict(id="owid-population-world", kind="owid", slug="population", q="&country=~OWID_WRL&time=1700..latest&yScale=log", notes="world pop log"),
    dict(id="owid-literacy", kind="owid", slug="cross-country-literacy-rates", q="&country=~OWID_WRL~GBR~IND", notes="literacy rates"),

    # --- NASA GISS (5) ---
    dict(id="giss-us-temp", kind="giss",
         png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/U.S._Temperature/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/U.S._Temperature/graph.csv",
         notes="US temperature anomaly, two series"),
    dict(id="giss-hemispheric", kind="giss",
         png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Hemispheric_Temperature_Change/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Hemispheric_Temperature_Change/graph.csv",
         notes="hemispheric change multi-series"),
    dict(id="giss-land-only", kind="giss",
         png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Global_Mean_Estimates_based_on_Land_Data_only/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Global_Mean_Estimates_based_on_Land_Data_only/graph.csv",
         notes="land-only, two lines"),
    dict(id="giss-seasonal", kind="giss",
         png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/GISTEMP_Seasonal_Cycle_since_1880/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/GISTEMP_Seasonal_Cycle_since_1880/graph.csv",
         notes="seasonal cycle, single thin line"),
    dict(id="giss-lat-bands", kind="giss",
         png="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Temperature_Change_for_Three_Latitude_Bands/graph.png",
         csv="https://data.giss.nasa.gov/gistemp/graphs_v4/graph_data/Temperature_Change_for_Three_Latitude_Bands/graph.csv",
         notes="three latitude bands"),

    # --- NOAA GML (6) ---
    dict(id="noaa-ch4-monthly", kind="noaa2",
         png="https://gml.noaa.gov/webdata/ccgg/trends/ch4_trend_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/ch4/ch4_mm_gl.csv",
         notes="CH4 monthly global mean + trend"),
    dict(id="noaa-n2o-monthly", kind="noaa2",
         png="https://gml.noaa.gov/webdata/ccgg/trends/n2o_trend_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/n2o/n2o_mm_gl.csv",
         notes="N2O monthly global mean + trend"),
    dict(id="noaa-sf6-monthly", kind="noaa2",
         png="https://gml.noaa.gov/webdata/ccgg/trends/sf6_trend_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/sf6/sf6_mm_gl.csv",
         notes="SF6 monthly global mean + trend"),
    dict(id="noaa-co2-mlo-trend", kind="noaa",
         png="https://gml.noaa.gov/webdata/ccgg/trends/co2_trend_mlo.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/co2/co2_mm_mlo.csv",
         notes="CO2 trend MLO"),
    dict(id="noaa-ch4-growth", kind="noaa-growth",
         png="https://gml.noaa.gov/webdata/ccgg/trends/ch4_gr_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/ch4/ch4_gr_gl.csv",
         notes="CH4 annual growth global"),
    dict(id="noaa-n2o-growth", kind="noaa-growth",
         png="https://gml.noaa.gov/webdata/ccgg/trends/n2o_gr_gl.png",
         csv="https://gml.noaa.gov/webdata/ccgg/trends/n2o/n2o_gr_gl.csv",
         notes="N2O annual growth global"),
]


def urls(m: dict) -> tuple[str, str]:
    if m["kind"] == "owid":
        return (OWID.format(slug=m["slug"], ext="png", q=m["q"]), OWID.format(slug=m["slug"], ext="csv", q=m["q"] + "&csvType=filtered"))
    if m["kind"] == "fred":
        return (FRED.format(ids=m["ids"], ext="png", q=m["q"]), FRED.format(ids=m["ids"], ext="csv", q=m["q"]))
    return m["png"], m["csv"]


def fetch(url: str, path: str) -> bool:
    r = subprocess.run(
        ["curl", "-sSL", "-m", "60", "-A", "plot2data-ml benchmark fetch", "-o", path, "-w", "%{http_code}", url],
        capture_output=True, text=True,
    )
    ok = r.returncode == 0 and r.stdout.strip() == "200" and os.path.exists(path) and os.path.getsize(path) > 500
    if not ok:
        print(f"  failed {url}: {r.stdout.strip()} {r.stderr.strip()[:120]}", file=sys.stderr)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ml/data/t5-real-ext")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ok = fail = 0
    for m in MANIFEST:
        if a.only and m["id"] not in a.only:
            continue
        png, csv_url = urls(m)
        stem = os.path.join(a.out, m["id"])
        if os.path.exists(stem + ".json") and not a.force:
            ok += 1
            continue
        print(m["id"], flush=True)
        if not (fetch(png, stem + ".png") and fetch(csv_url, stem + ".data.csv")):
            for ext in (".png", ".data.csv"):
                if os.path.exists(stem + ext):
                    os.remove(stem + ext)
            fail += 1
            continue
        with open(stem + ".json", "w") as f:
            json.dump(dict(m, png_url=png, csv_url=csv_url, fetched=time.strftime("%Y-%m-%d %H:%M")), f, indent=1)
        ok += 1
        time.sleep(0.8)
    print(f"\nfetched {ok}, failed {fail}")


if __name__ == "__main__":
    main()
