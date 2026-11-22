#!/usr/bin/env python3
"""Two more outside forces for the stock model.

weather:  daily rain and max temperature for 13 economically important Indian regions
          (Open-Meteo archive), turned into 30-day rain totals and 7-day heat averages.
news:     daily news volume and tone per company (GDELT DOC API, worldwide online news),
          one request per company per measure, at most one request every 6 seconds.

Usage: python3 weather_news.py weather OUT.pkl
       python3 weather_news.py news SYMBOL_ARTICLES.csv OUTDIR
"""
import csv, json, os, subprocess, sys, time, urllib.parse
import pandas as pd

REGIONS = {  # name: (lat, lon, why it matters)
    "Punjab": (30.9, 75.85, "wheat, rice"), "Uttar Pradesh": (26.85, 80.95, "sugar, rural demand"),
    "Madhya Pradesh": (22.72, 75.86, "soybean, pulses"), "Maharashtra (Vidarbha)": (21.15, 79.09, "cotton"),
    "Gujarat": (23.02, 72.57, "cotton, groundnut, industry"), "Rajasthan": (26.91, 75.79, "mustard, cement"),
    "Bihar": (25.59, 85.14, "rural demand"), "West Bengal": (22.57, 88.36, "rice, jute, tea"),
    "Karnataka": (12.97, 77.59, "coffee, sugar"), "Tamil Nadu": (13.08, 80.27, "rice, industry"),
    "Andhra/Telangana": (17.39, 78.49, "rice, chilli"), "Mumbai": (19.08, 72.88, "consumer demand"),
    "Delhi": (28.61, 77.21, "power demand, heat"),
}


def weather(out):
    frames = []
    for name, (lat, lon, _) in REGIONS.items():
        url = ("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode({
            "latitude": lat, "longitude": lon, "start_date": "2019-01-01", "end_date": "2026-11-20",
            "daily": "precipitation_sum,temperature_2m_max", "timezone": "Asia/Kolkata"}))
        for attempt in range(5):
            r = subprocess.run(["curl", "-sSf", "-m", "90", url], capture_output=True, text=True)
            if r.returncode == 0 and r.stdout.startswith("{"):
                break
            time.sleep(3 * (attempt + 1))
        d = json.loads(r.stdout)["daily"]
        idx = pd.to_datetime(d["time"])
        rain = pd.Series(d["precipitation_sum"], index=idx).fillna(0)
        heat = pd.Series(d["temperature_2m_max"], index=idx).ffill()
        frames.append(rain.rolling(30, min_periods=20).sum().rename(f"Rain 30d: {name}"))
        frames.append(heat.rolling(7, min_periods=5).mean().rename(f"Heat 7d: {name}"))
        time.sleep(1)
    w = pd.concat(frames, axis=1)
    rain_cols = [c for c in w if c.startswith("Rain")]
    heat_cols = [c for c in w if c.startswith("Heat")]
    # all-India measures, compared with the same calendar day in other years (rain is seasonal)
    w["Rain 30d: all regions"] = w[rain_cols].mean(axis=1)
    w["Heat 7d: all regions"] = w[heat_cols].mean(axis=1)
    doy = w.index.dayofyear
    for c in ["Rain 30d: all regions", "Heat 7d: all regions"] + rain_cols + heat_cols:
        normal = w[c].groupby(doy).transform("mean")
        w[c.replace("30d:", "30d vs normal:").replace("7d:", "7d vs normal:")] = w[c] - normal
    keep = [c for c in w if "vs normal" in c]
    w[keep].to_pickle(out)
    print(f"{len(keep)} weather series, {w.index.min().date()}..{w.index.max().date()}")


def gdelt(query, mode):
    url = "https://api.gdeltproject.org/api/v2/doc/doc?" + urllib.parse.urlencode({
        "query": query, "mode": mode, "startdatetime": "20200101000000", "enddatetime": "20261120000000",
        "format": "json"})
    for attempt in range(8):
        time.sleep(6 + 4 * attempt)
        r = subprocess.run(["curl", "-sS", "-m", "120", url], capture_output=True, text=True)
        if r.stdout.lstrip().startswith("{"):
            try:
                tl = json.loads(r.stdout).get("timeline", [])
                return tl[0]["data"] if tl else []
            except json.JSONDecodeError:
                pass
    return None


def news(articles_csv, outdir):
    os.makedirs(outdir, exist_ok=True)
    for r in csv.DictReader(open(articles_csv)):
        path = os.path.join(outdir, r["symbol"] + ".json")
        if os.path.exists(path):
            continue
        name = urllib.parse.unquote(r["article"]).replace("_", " ")
        name = name.split(" (")[0]
        q = f'"{name}"'
        tone = gdelt(q, "timelinetone")
        vol = gdelt(q, "timelinevolraw")
        if tone is None or vol is None:
            print(f"{r['symbol']}: GDELT kept refusing, will retry on next run", flush=True)
            continue
        json.dump({"query": q, "tone": tone, "volume": vol}, open(path, "w"))
    print("done", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "weather":
        weather(sys.argv[2])
    else:
        news(sys.argv[2], sys.argv[3])
