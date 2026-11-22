#!/usr/bin/env python3
"""What happens after NSE moves a stock into, or out of, trade-for-trade (series BE)?

NSE shifts stocks to series BE (every trade must be settled by delivery, no intraday
trading) mostly under its surveillance frameworks for unusual speculation, and moves
them back to EQ when that ends. This finds both kinds of moves in the daily files and
measures returns from that day's close over the next 1, 3 and 6 months, compared with
the average liquid company over the same days.

Usage: python3 surveillance.py DAILY_DIR PANEL.pkl FUNDS.txt [OUT.csv]
"""
import glob, os, sys
import numpy as np
import pandas as pd
from backtest import prepare

H = {"1m": 21, "3m": 63, "6m": 126}


def main(daily_dir, panel, funds_txt, out="surveillance_events.csv"):
    rows = []
    for f in sorted(glob.glob(os.path.join(daily_dir, "*.csv"))):
        with open(f, "rb") as fh:
            if not fh.read(6).startswith(b"SYMBOL"):
                continue
        d = pd.read_csv(f, skipinitialspace=True, usecols=[0, 1, 2, 3, 8, 11], dtype=str)
        d.columns = ["symbol", "series", "date", "prev_close", "close", "turnover"]
        d = d[d["series"].str.strip().isin(["EQ", "BE"])]
        rows.append(d)
    a = pd.concat(rows, ignore_index=True)
    for c in ["symbol", "series", "date"]:
        a[c] = a[c].str.strip()
    a["date"] = pd.to_datetime(a["date"], format="%d-%b-%Y")
    for c in ["prev_close", "close", "turnover"]:
        a[c] = pd.to_numeric(a[c].str.strip(), errors="coerce")
    a = a.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"], keep="last")
    a["ret"] = (a["close"] / a["prev_close"] - 1).where(lambda r: r.abs() < 0.5).fillna(0)
    a["logidx"] = np.log1p(a["ret"]).groupby(a["symbol"]).cumsum()
    prev = a.groupby("symbol")["series"].shift(1)
    a["event"] = np.select([(prev == "EQ") & (a["series"] == "BE"), (prev == "BE") & (a["series"] == "EQ")],
                           ["into BE", "back to EQ"], "")
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    mkt = np.log1p(p[p["liquid"]].groupby("date")["ret"].mean()).cumsum()
    lp = a.pivot_table(index="date", columns="symbol", values="logidx").reindex(mkt.index).ffill()
    dates = lp.index
    ev = a[(a["event"] != "") & (a["date"] >= dates[60])].copy()
    for name, n in H.items():
        vals = []
        for s, d in zip(ev["symbol"], ev["date"]):
            k = dates.get_loc(d)
            if k + n >= len(dates):
                vals.append(np.nan); continue
            own = np.expm1(lp[s].iloc[k + n] - lp[s].iloc[k])
            vals.append(own - np.expm1(mkt.iloc[k + n] - mkt.iloc[k]))
        ev[name] = vals
    ev["prior_1m"] = [np.expm1(lp[s].iloc[dates.get_loc(d)] - lp[s].iloc[max(0, dates.get_loc(d) - 21)])
                      for s, d in zip(ev["symbol"], ev["date"])]
    ev["value_cr"] = ev["turnover"] / 100
    ev.to_csv(out, index=False)
    # which stock was in trade-for-trade on which day, for the combined model
    be = (a.assign(v=(a["series"] == "BE").astype(float))
           .pivot_table(index="date", columns="symbol", values="v").reindex(dates).fillna(0))
    be.to_pickle(out.replace(".csv", "_be_days.pkl"))
    ev["half"] = np.where(ev["date"] < "2023-07-01", "2020-23", "2023-26")
    print(f"{len(ev)} events. cells: mean / median excess vs market (% beating market)")
    for (e, h), g in ev.groupby(["event", "half"]):
        cells = "  ".join(f"{k}: {g[k].mean()*100:+5.1f}/{g[k].median()*100:+5.1f} ({(g[k].dropna()>0).mean()*100:3.0f}%)" for k in H)
        print(f"{e:11} {h} n={len(g):4} prior month {g['prior_1m'].median()*100:+5.1f}% | {cells}")


if __name__ == "__main__":
    main(*sys.argv[1:])
