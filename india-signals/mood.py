#!/usr/bin/env python3
"""Mood signals: things that change investors' mood, not companies.

- Sunshine (Hirshleifer & Shumway 2003): Mumbai cloud cover vs normal for that week of the year
- Air pollution: Mumbai daytime PM2.5 vs its previous 30 days (data from Aug 2022)
- Moon phase (Dichev & Janes 2003): days within 3 of a new moon vs a full moon
- Pre-holiday effect: the trading day before a weekday market holiday
The market is the equal-weight average of liquid NSE companies, same-day close to close.

Usage: python3 mood.py PANEL.pkl FUNDS.txt WEATHER.json AIR.json
"""
import json, sys
import numpy as np
import pandas as pd
from backtest import prepare

SPLIT = pd.Timestamp("2023-07-01")


def moon_age(d):
    ref = pd.Timestamp("2000-01-06 18:14")
    return ((d - ref) / pd.Timedelta(days=1)) % 29.530589


def report(label, a, b, ret):
    out = []
    for half, sel in [("2020-23", ret.index < SPLIT), ("2023-26", ret.index >= SPLIT)]:
        ra, rb = ret[a & sel], ret[b & sel]
        diff = ra.mean() - rb.mean()
        se = np.sqrt(ra.var() / len(ra) + rb.var() / len(rb))
        out.append(f"{half}: {ra.mean()*100:+.3f}% vs {rb.mean()*100:+.3f}%/day (diff {diff*100:+.3f}, t {diff/se:+.1f}, n {len(ra)}/{len(rb)})")
    print(f"{label:36} " + " | ".join(out))


def main(panel, funds_txt, wx_json, air_json):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    ret = p[p["liquid"]].groupby("date")["ret"].mean()
    big = p[p["liquid"] & (p["size_q"] == 4)].groupby("date")["ret"].mean()
    ret = ret[ret.index >= "2020-04-01"]
    w = json.load(open(wx_json))["daily"]
    wx = pd.DataFrame(w).assign(time=lambda x: pd.to_datetime(x["time"])).set_index("time")
    week = wx.index.isocalendar().week.values
    wx["cloud_dev"] = wx["cloud_cover_mean"] - wx.groupby(week)["cloud_cover_mean"].transform("mean")
    a = json.load(open(air_json))["hourly"]
    air = pd.DataFrame(a).assign(time=lambda x: pd.to_datetime(x["time"])).set_index("time")
    day = air.between_time("09:00", "15:30")["pm2_5"].groupby(lambda t: t.normalize()).mean()
    day.index = pd.to_datetime(day.index)
    air_dev = np.log(day / day.shift(1).rolling(30, min_periods=15).mean())
    cd = wx["cloud_dev"].reindex(ret.index)
    print("Sunshine (Mumbai cloud cover vs normal for the week):")
    report("  clearest fifth vs cloudiest fifth", cd <= cd.quantile(0.2), cd >= cd.quantile(0.8), ret)
    report("  same, largest companies only", cd <= cd.quantile(0.2), cd >= cd.quantile(0.8), big.reindex(ret.index))
    ad = air_dev.reindex(ret.index)
    print("Air pollution (Mumbai PM2.5 during market hours vs previous 30 days, from Aug 2022):")
    report("  cleanest fifth vs smoggiest fifth", ad <= ad.quantile(0.2), ad >= ad.quantile(0.8), ret)
    age = pd.Series(moon_age(ret.index.to_series()).values, index=ret.index)
    print("Moon:")
    report("  near new moon vs near full moon", (age <= 3) | (age >= 26.5), (age >= 11.8) & (age <= 17.8), ret)
    nxt = pd.Series(ret.index[1:].tolist() + [ret.index[-1]], index=ret.index)
    gap_bd = pd.Series([np.busday_count(d.date(), n.date()) for d, n in zip(ret.index, nxt)], index=ret.index)
    print("Holidays:")
    report("  day before a weekday holiday vs others", gap_bd >= 2, gap_bd == 1, ret)


if __name__ == "__main__":
    main(*sys.argv[1:])
