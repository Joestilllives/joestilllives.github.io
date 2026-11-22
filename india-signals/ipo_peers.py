#!/usr/bin/env python3
"""Hot IPO -> listed peers. When a company lists with a big first-day gain, do already
listed companies in the same sector move (investors re-rating "similar" companies)?

Sectors come from NSE's current index list, so only today's members are covered.
Peers are compared with OTHER members of that same list over the same days, so both
sides share that survivor bias. Windows are measured from the IPO's listing-day close
(and the 5 days before it).

Usage: python3 ipo_peers.py PANEL.pkl IPOS.csv INDUSTRY.csv FUNDS.txt
"""
import csv, sys
import numpy as np
import pandas as pd
from backtest import prepare, SPLIT

WIN = {"week before": (-5, 0), "next week": (0, 5), "next month": (0, 21), "next 3 months": (0, 63)}


def main(panel, ipos_csv, industry_csv, funds_txt):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    ind = {r["Symbol"]: r["Industry"] for r in csv.DictReader(open(industry_csv))}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    liq = p.pivot_table(index="date", columns="symbol", values="liquid", aggfunc="first").fillna(False).astype(bool)
    dates = lp.index
    members = [s for s in lp.columns if s in ind]
    ipos = pd.read_csv(ipos_csv)
    rows = []
    for r in ipos.itertuples():
        sec = ind.get(r.symbol)
        if not sec:
            continue
        d0 = pd.Timestamp(r.date)
        if d0 not in dates:
            continue
        k = dates.get_loc(d0)
        uni = [s for s in members if s != r.symbol and liq.iloc[max(k - 1, 0)].get(s, False)]
        peers = [s for s in uni if ind[s] == sec]
        others = [s for s in uni if ind[s] != sec]
        if len(peers) < 3:
            continue
        row = {"ipo": r.symbol, "date": r.date, "sector": sec, "listing_gain": r.listing_gain, "peers": len(peers)}
        for name, (a, b) in WIN.items():
            if k + a < 0 or k + b >= len(dates):
                row[name] = np.nan
                continue
            mv = np.expm1(lp.iloc[k + b] - lp.iloc[k + a])
            row[name] = mv[peers].mean() - mv[others].mean()
        rows.append(row)
    df = pd.DataFrame(rows)
    df["kind"] = pd.cut(df["listing_gain"], [-1, 0, 0.4, 10], labels=["IPO fell on day 1", "IPO up 0-40%", "IPO up 40%+"])
    df["half"] = np.where(pd.to_datetime(df["date"]) < SPLIT, "2020-23", "2023-26")
    print(f"{len(df)} IPOs with 3+ listed sector peers. Peers' return minus other listed companies, mean (share positive):")
    for keys, g in df.groupby(["kind", "half"], observed=True):
        cells = "  ".join(f"{w}: {g[w].mean()*100:+.2f}% ({(g[w].dropna()>0).mean()*100:.0f}%)" for w in WIN)
        print(f"{keys[0]:18} {keys[1]} n={len(g):3} | {cells}")
    df.to_csv("/dev/stdout" if False else sys.argv[0].replace(".py", "_events.csv"), index=False)


if __name__ == "__main__":
    main(*sys.argv[1:])
