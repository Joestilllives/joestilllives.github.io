#!/usr/bin/env python3
"""Tune the steady-accumulation rule on the FIRST half only, then test the winner
once on the second half (which the tuning never saw).

Usage: python3 refine.py PANEL.pkl [OUT.json]
"""
import itertools, json, sys
import numpy as np
import pandas as pd
from backtest import prepare, summarize, SPLIT, HORIZONS

GRID = {
    "deliv_pts": [5, 10, 15],      # delivery % above its 60-day average by at least this
    "min_days": [6, 7, 8],         # ...on at least this many of the last 10 days
    "vol_trend": [1.2, 1.5, 2.0],  # 10-day avg volume vs prior 20-day avg
    "max_move": [0.03, 0.05, 0.08],  # price change over those 10 days stays within ±this
}


def features(p):
    g = p.groupby("symbol", sort=False)
    f = pd.DataFrame(index=p.index)
    for d in GRID["deliv_pts"]:
        f[f"hd{d}"] = g["deliv_jump"].transform(lambda s: (s >= d).astype(float).rolling(10).sum())
    f["vol_trend"] = g["volume"].transform(lambda s: s.rolling(10).mean()) / p["vol_avg20"].replace(0, np.nan)
    f["ret10"] = g["logidx"].transform(lambda s: s - s.shift(10)).abs()
    # any "frenzy" day (3x volume, delivery 15 pts below usual) in the last 5 days
    frenzy = ((p["vol_x"] >= 3) & (p["deliv_jump"] <= -15)).astype(float)
    f["frenzy5"] = frenzy.groupby(p["symbol"]).transform(lambda s: s.rolling(5, min_periods=1).max())
    return f


def first_days(p, sig):
    prev = sig.groupby(p["symbol"]).shift(1, fill_value=False)
    return sig & ~prev.astype(bool)


def rule(p, f, c):
    sig = (f[f"hd{c['deliv_pts']}"] >= c["min_days"]) & (f["vol_trend"] >= c["vol_trend"]) & (f["ret10"] < c["max_move"])
    return first_days(p, sig.fillna(False))


def score(s):
    """Tuning objective: average t-stat at 20 and 60 days, needing enough events."""
    if s["events"] < 150 or not s.get("h20") or not s.get("h60"):
        return -np.inf
    return (s["h20"]["t_stat"] + s["h60"]["t_stat"]) / 2


def main(panel, out="refine_results.json"):
    p = prepare(pd.read_pickle(panel))
    p = p[p["liquid"]].copy()
    f = features(p)
    first = p["date"] < SPLIT
    tried = []
    for combo in itertools.product(*GRID.values()):
        c = dict(zip(GRID, combo))
        m = rule(p, f, c)
        s1 = summarize(p[m & first], "")
        tried.append((score(s1), c, s1))
    tried.sort(key=lambda x: -x[0])
    best_score, best, s1 = tried[0]
    m = rule(p, f, best)
    s2 = summarize(p[m & ~first], "")
    # same winner, but skipping stocks that had a frenzy day in the last 5 days
    calm = m & (f["frenzy5"] == 0)
    res = {"grid_size": len(tried), "best_rule": best,
           "first_half_tuned": s1, "second_half_unseen": s2,
           "calm_first_half": summarize(p[calm & first], ""), "calm_second_half": summarize(p[calm & ~first], ""),
           "top5_first_half": [{"rule": c, "score": round(sc, 2), "events": s["events"]} for sc, c, s in tried[:5]],
           "median_rule_first_half_score": round(float(np.median([t[0] for t in tried if np.isfinite(t[0])])), 2)}
    json.dump(res, open(out, "w"), indent=1)

    def line(label, s):
        cells = []
        for h in HORIZONS:
            v = s.get(f"h{h}")
            cells.append(f"{v['mean_excess']*100:6.2f}% med {v['median_excess']*100:5.1f}% hit {v['hit_rate']*100:3.0f}% t {v['t_stat']:4.1f}" if v else "—")
        print(f"{label:26} n={s['events']:<5} " + " | ".join(cells))
    print(f"Tried {len(tried)} versions on 2020-{SPLIT.date()}; best: {best}")
    print("Top 5 (first half score):", [(round(sc, 2), c) for sc, c, _ in tried[:5]])
    print("Median version's score:", res["median_rule_first_half_score"])
    print(f"{'':26} {'':7} " + " | ".join(f"{h}-day excess" .ljust(38) for h in HORIZONS))
    line("best, 2020-23 (tuned)", s1)
    line("best, 2023-26 (UNSEEN)", s2)
    line("best+calm, 2020-23", res["calm_first_half"])
    line("best+calm, 2023-26", res["calm_second_half"])


if __name__ == "__main__":
    main(*sys.argv[1:])
