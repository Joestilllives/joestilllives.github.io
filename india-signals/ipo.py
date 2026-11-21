#!/usr/bin/env python3
"""What happens to NSE IPOs after listing day?

A new listing is a symbol whose first appearance in ANY series of NSE's daily files
is after the first 60 days of data, appearing directly in the EQ series. Renamed
symbols, demergers and board migrations also look like that, so the analysis keeps
only listings whose day-1 volume is at least 4x the median of the next 20 days. On that
day NSE's PREV_CLOSE is the IPO issue price, so close / prev_close - 1 is the
listing-day gain. From the listing-day close (or a later entry day) we measure the
return over the next 1, 3 and 6 months against the average liquid stock.

Usage: python3 ipo.py DAILY_DIR PANEL.pkl [OUT.json]
"""
import glob, json, os, sys
import numpy as np
import pandas as pd
from backtest import prepare

HOLD = {"1m": 21, "3m": 63, "6m": 126}


def first_seen(daily_dir):
    first, first_series = {}, {}
    for f in sorted(glob.glob(os.path.join(daily_dir, "*.csv"))):
        with open(f, "rb") as fh:
            if not fh.read(6).startswith(b"SYMBOL"):
                continue
        d = pd.read_csv(f, skipinitialspace=True, usecols=[0, 1, 2], dtype=str)
        d.columns = ["symbol", "series", "date"]
        date = pd.to_datetime(d["date"].iloc[0].strip(), format="%d-%b-%Y")
        for s, ser in zip(d["symbol"].str.strip(), d["series"].str.strip()):
            if s not in first:
                first[s], first_series[s] = date, ser
    return first, first_series


def main(daily_dir, panel, out="ipo_results.json"):
    first, fser = first_seen(daily_dir)
    p = prepare(pd.read_pickle(panel))
    dates = np.sort(p["date"].unique())
    start_ok = dates[60]
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    liq = p.pivot_table(index="date", columns="symbol", values="liquid", aggfunc="first").fillna(False).astype(bool)
    day1 = p.sort_values("date").groupby("symbol").head(1).set_index("symbol")
    rows = []
    for s, d0 in first.items():
        if d0 < start_ok or fser[s] != "EQ" or s not in day1.index or day1.loc[s, "date"] != d0:
            continue
        r = day1.loc[s]
        gain = r["close"] / r["prev_close"] - 1
        if not np.isfinite(gain) or abs(gain) > 3:
            continue
        k = lp.index.get_loc(d0)
        row = {"symbol": s, "date": str(pd.Timestamp(d0).date()), "listing_gain": round(float(gain), 4),
               "listing_delivery_pct": None if pd.isna(r["deliv_per"]) else float(r["deliv_per"]),
               "listing_value_cr": round(float(r["turnover_lacs"]) / 100, 1)}
        for entry_lag, tag in [(0, "from_listing"), (21, "from_month2")]:
            for h, n in HOLD.items():
                a, b = k + entry_lag, k + entry_lag + n
                if b >= len(lp.index):
                    continue
                own = np.expm1(lp[s].iloc[b] - lp[s].iloc[a])
                uni = liq.iloc[a]
                mkt = np.expm1(lp.loc[:, uni[uni].index].iloc[b] - lp.loc[:, uni[uni].index].iloc[a]).mean()
                row[f"{tag}_{h}"] = round(float(own - mkt), 4)
        rows.append(row)
    df = pd.DataFrame(rows)
    df["bucket"] = pd.cut(df["listing_gain"], [-1, 0, 0.15, 0.4, 10],
                          labels=["fell on day 1", "0-15% pop", "15-40% pop", "40%+ pop"])
    res = {"ipos": len(df), "by_bucket": {}}
    print(f"{len(df)} IPO listings since {pd.Timestamp(start_ok).date()}; median day-1 gain {df.listing_gain.median()*100:.1f}%")
    cols = [c for c in df.columns if c.startswith(("from_listing", "from_month2"))]
    print(f"{'listing day':16} {'n':>4} " + " ".join(f"{c.replace('from_listing','L').replace('from_month2','M2'):>9}" for c in cols))
    for b, g in list(df.groupby("bucket", observed=True)) + [("all", df)]:
        stats = {}
        cells = []
        for c in cols:
            x = g[c].dropna()
            stats[c] = {"mean": round(float(x.mean()), 4), "median": round(float(x.median()), 4),
                        "beat_market": round(float((x > 0).mean()), 3), "n": int(len(x))}
            cells.append(f"{x.mean()*100:+5.1f}/{x.median()*100:+4.0f}")
        res["by_bucket"][str(b)] = stats
        print(f"{str(b):16} {len(g):>4} " + " ".join(f"{c:>9}" for c in cells))
    print("(each cell: mean / median excess return vs average liquid stock, %; L = bought at listing close, "
          "M2 = bought one month after listing)")
    df.to_csv(out.replace(".json", ".csv"), index=False)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
