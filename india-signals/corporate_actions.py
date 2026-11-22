#!/usr/bin/env python3
"""Splits and bonuses detected from NSE's unadjusted prices, and what the stocks did
around the ex-date (the day the share count changes), against the average liquid company.

An event = a day-on-day price ratio within 3% of 1/2, 2/3, 3/4, 1/3, 1/5 or 1/10 (not the
first day of trading). Returns use the corrected series (event day removed).

Usage: python3 corporate_actions.py PANEL.pkl FUNDS.txt OUT.csv
"""
import sys
import numpy as np
import pandas as pd
from backtest import prepare

RATIOS = {"1:1 bonus or 2-for-1 split": 1 / 2, "1:2 bonus": 2 / 3, "1:3 bonus": 3 / 4, "3-for-1 split / 2:1 bonus": 1 / 3,
          "5-for-1 split": 1 / 5, "10-for-1 split": 1 / 10}
WIN = {"month before": (-21, -1), "week after": (0, 5), "month after": (0, 21), "3 months after": (0, 63), "6 months after": (0, 126)}


def main(panel, funds_txt, out):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    raw = raw[~raw["symbol"].isin(funds)].sort_values(["symbol", "date"])
    raw["n"] = raw.groupby("symbol").cumcount()
    ratio = raw["close"] / raw["prev_close"]
    ev = []
    for name, v in RATIOS.items():
        hit = raw[(abs(ratio - v) < 0.03 * v) & (raw["n"] > 0)]
        ev.append(hit[["symbol", "date"]].assign(kind=name, liquid_before=False))
    # splits/bonuses mixed with that day's price move miss the exact ratios (a 5-for-1 split
    # can land at -78%); NSE bands are at most 20%, so any drop beyond 25% is a corporate action
    other = raw[(ratio < 0.75) & (raw["n"] > 0)][["symbol", "date"]].assign(kind="other split/bonus/demerger", liquid_before=False)
    ev = pd.concat(ev + [other]).drop_duplicates(["symbol", "date"])
    p = prepare(raw)
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    liq = p.pivot_table(index="date", columns="symbol", values="liquid", aggfunc="first").fillna(False).astype(bool)
    mkt = np.log1p(p[p["liquid"]].groupby("date")["ret"].mean()).cumsum().reindex(lp.index).ffill()
    dates = lp.index
    rows = []
    for r in ev.itertuples():
        k = dates.get_loc(r.date)
        row = {"symbol": r.symbol, "date": r.date.date(), "kind": r.kind,
               "liquid": bool(liq[r.symbol].iloc[max(k - 1, 0)]) if r.symbol in liq else False}
        for w, (a, b) in WIN.items():
            if k + a < 0 or k + b >= len(dates):
                row[w] = np.nan; continue
            row[w] = np.expm1(lp[r.symbol].iloc[k + b] - lp[r.symbol].iloc[k + a]) - np.expm1(mkt.iloc[k + b] - mkt.iloc[k + a])
        rows.append(row)
    df = pd.DataFrame(rows)
    df.to_csv(out, index=False)
    df["half"] = np.where(pd.to_datetime(df["date"]) < pd.Timestamp("2021-07-01"), "2016-21", "2021-26")
    print(f"{len(df)} splits/bonuses, {int(df.liquid.sum())} in liquid companies. Excess vs market: mean / median (share positive)")
    for (liqd, h), g in df.groupby(["liquid", "half"]):
        cells = "  ".join(f"{w}: {g[w].mean()*100:+.1f}/{g[w].median()*100:+.1f} ({(g[w].dropna()>0).mean()*100:.0f}%)" for w in WIN)
        print(f"{'liquid' if liqd else 'illiquid':8} {h} n={len(g):3} | {cells}")


if __name__ == "__main__":
    main(*sys.argv[1:])
