#!/usr/bin/env python3
"""Does Wikipedia attention predict the Indian market? (Moat et al., 2013, applied to NSE.)

Each week (Mon-Sun of Wikipedia readers), a topic's views are compared with the
average of the previous 3 weeks. Rising attention = expect the market to fall the
following week (Mon-Fri). Two versions per topic:
  timing  - hold the market when attention fell, sit in cash when it rose
  long/short - the original study's buy/sell rule, as a test of direction
The market is the equal-weight average of liquid NSE companies (ETFs excluded).

Usage: python3 wiki_market.py PANEL.pkl TOPIC_VIEWS.pkl FUNDS.txt [OUT.json]
"""
import json, sys
import numpy as np
import pandas as pd
from backtest import prepare

SPLIT = pd.Timestamp("2023-07-01")
WORRY = ["T_recession", "T_inflation", "T_crash", "T_unemployment", "T_layoff", "T_debt", "T_war",
         "T_pandemic", "T_interest", "T_fed", "T_rbi", "T_tariff", "T_tradewar", "T_shortsell", "T_bear"]


def main(panel, views_pkl, funds_txt, out="wiki_market_results.json"):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    p = p[p["liquid"]]
    daily = p.groupby("date")["ret"].mean()                       # equal-weight market, daily
    week_ret = daily.groupby(daily.index.to_period("W-SUN")).apply(lambda r: np.expm1(np.log1p(r).sum()))
    v = pd.read_pickle(views_pkl).pivot_table(index="date", columns="symbol", values="views")
    wv = v.groupby(v.index.to_period("W-SUN")).mean()
    delta = np.log(wv) - np.log(wv.shift(1).rolling(3).mean())    # last week vs the 3 before
    z = (delta - delta.rolling(52, min_periods=26).mean()) / delta.rolling(52, min_periods=26).std()
    delta["WORRY_INDEX"] = z[[c for c in WORRY if c in z]].mean(axis=1)
    nxt = week_ret.shift(-1)                                       # the week AFTER the views
    res = {}
    rows = []
    for topic in delta.columns:
        d = pd.DataFrame({"d": delta[topic], "r": nxt}).dropna()
        d = d[d.index.start_time >= pd.Timestamp("2020-06-01")]
        if len(d) < 100:
            continue
        stats = {}
        for label, part in [("first", d[d.index.start_time < SPLIT]), ("second", d[d.index.start_time >= SPLIT])]:
            signal = np.where(part["d"] > 0, -1.0, 1.0)            # attention up -> expect a fall
            ls = signal * part["r"]
            timing = np.where(signal > 0, part["r"], 0.0)
            stats[label] = {"weeks": int(len(part)),
                            "long_short_per_week": float(ls.mean()),
                            "t": float(ls.mean() / ls.std() * np.sqrt(len(ls))),
                            "timing_total": float(np.prod(1 + timing) - 1),
                            "market_total": float(np.prod(1 + part["r"]) - 1),
                            "corr": float(part["d"].corr(part["r"]))}
        res[topic] = stats
        rows.append((topic, stats))
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'topic':16} {'2020-23 corr':>12} {'t':>5} {'timing vs market':>22} | {'2023-26 corr':>12} {'t':>5} {'timing vs market':>22}")
    rows.sort(key=lambda x: x[1]["first"]["t"] + x[1]["second"]["t"], reverse=True)
    for topic, s in rows:
        a, b = s["first"], s["second"]
        both = " <- both periods" if a["t"] > 1.65 and b["t"] > 1.65 else ""
        print(f"{topic[2:] if topic.startswith('T_') else topic:16} {a['corr']:+12.3f} {a['t']:5.1f} "
              f"{a['timing_total']*100:+9.0f}% vs {a['market_total']*100:+5.0f}% | {b['corr']:+12.3f} {b['t']:5.1f} "
              f"{b['timing_total']*100:+9.0f}% vs {b['market_total']*100:+5.0f}%{both}")


if __name__ == "__main__":
    main(*sys.argv[1:])
