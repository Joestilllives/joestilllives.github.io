#!/usr/bin/env python3
"""Results-season drift: do big moves on heavy volume during Indian results season keep going?

Indian companies report quarterly results mostly in four windows (about 10 Jan-15 Feb,
10 Apr-31 May, 10 Jul-15 Aug, 10 Oct-15 Nov). A day in those windows with volume 3x+
normal and a move of 5%+ is treated as a results reaction. The test buys at the next
day's close and measures the return over 1 and 3 months against similar-sized stocks.
Split by direction, and by whether delivery was high (real holders) or low (speculation).

Usage: python3 results_drift.py PANEL.pkl FUNDS.txt
"""
import sys
import numpy as np
import pandas as pd
from backtest import prepare, SPLIT


def in_window(d):
    md = d.month * 100 + d.day
    return (md.between(110, 215) | md.between(410, 531) | md.between(710, 815) | md.between(1010, 1115))


def main(panel, funds_txt):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    p = p[p["liquid"]].copy()
    p["season"] = in_window(p["date"].dt)
    ev = p[p["season"] & (p["vol_x"] >= 3) & (p["ret"].abs() >= 0.05)].copy()
    # one event per stock per season
    ev["q"] = ev["date"].dt.year * 10 + (ev["date"].dt.month - 1) // 3
    ev = ev.sort_values("date").groupby(["symbol", "q"]).head(1)
    ev["dir"] = np.where(ev["ret"] > 0, "jumped", "dropped")
    ev["holders"] = np.where(ev["deliv_jump"] >= 0, "high delivery", "low delivery")
    ev["half"] = np.where(ev["date"] < SPLIT, "2020-23", "2023-26")
    print(f"{len(ev)} results reactions. cells: mean / median excess vs similar-sized stocks (% beating them)")
    for keys, g in ev.groupby(["dir", "holders", "half"]):
        cells = "  ".join(f"{h}: {g['ex'+str(n)].mean()*100:+5.1f}/{g['ex'+str(n)].median()*100:+5.1f} ({(g['ex'+str(n)].dropna()>0).mean()*100:3.0f}%)"
                          for h, n in [("1m", 20), ("3m", 60)])
        print(f"{keys[0]:8} {keys[1]:14} {keys[2]} n={len(g):4} | {cells}")


if __name__ == "__main__":
    main(*sys.argv[1:])
