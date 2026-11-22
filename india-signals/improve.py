#!/usr/bin/env python3
"""Ways to improve the steady-climbers signal without new data, each tested on its own
and then together, over all months of the monthly table.

  buffer    keep a holding until it falls out of the top 40% of its size group (not 20%)
  invvol    weight holdings by 1/volatility instead of equally
  trend     hold 50% cash (6.5%/yr) when the market is unhealthy (half of stocks or fewer
            above their 200-day average, or the average company down over 3 months)
  blend     score = average of the steady rank and the ML model rank (months where the
            model has out-of-sample scores only)

Usage: python3 improve.py MONTHLY_TABLE.pkl PREDICTIONS.pkl PANEL.pkl FUNDS.txt
"""
import sys
import numpy as np
import pandas as pd
from backtest import prepare

COST, TOP, KEEP, CASH = 0.003, 0.2, 0.4, (1.065) ** (1 / 12) - 1
GROUPS = [0, 1, 2, 3]
SPLIT = pd.Timestamp("2023-07-01")


def breadth_by_month(panel, funds_txt, months):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    q = prepare(raw[~raw["symbol"].isin(funds)])
    L = q.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    liq = q.pivot_table(index="date", columns="symbol", values="liquid", aggfunc="first").fillna(False).astype(bool)
    b = ((L > L.rolling(200, min_periods=150).mean()) & liq).sum(axis=1) / liq.sum(axis=1)
    return b.reindex(months, method="ffill")


def run(tab, buffer=False, invvol=False, trend=None, score="steady", months=None):
    rows, held = [], set()
    for m in months:
        g = tab[(tab["month"] == m) & tab["size_q"].isin(GROUPS) & (tab["frenzy21"] < 3)].dropna(subset=[score, "vol252"]).copy()
        if g["fwd"].isna().all():
            continue
        g["r"] = g.groupby("size_q")[score].rank(pct=True)
        top = set(g.loc[g["r"] >= 1 - TOP, "symbol"])
        keep = set(g.loc[g["r"] >= 1 - KEEP, "symbol"]) & held if buffer else set()
        new = top | keep
        to = len(new - held) / max(len(new), 1)
        held = new
        h = g[g["symbol"].isin(held)]
        w = (1 / h["vol252"]) if invvol else pd.Series(1.0, index=h.index)
        w = w / w.sum()
        r = (h["fwd"].fillna(0) * w).sum() - to * COST
        mkt = tab.loc[tab["month"] == m, "fwd"].mean()
        if trend is not None and not trend.get(m, True):
            r = 0.5 * r + 0.5 * CASH
        rows.append({"month": m, "algo": r, "market": mkt, "n": len(held), "turnover": to})
    return pd.DataFrame(rows)


def stats(r):
    ex = r["algo"] - r["market"]
    cur = np.cumprod(1 + r["algo"])
    return {"ex_yr": (1 + ex.mean()) ** 12 - 1, "t": ex.mean() / ex.std() * np.sqrt(len(ex)), "ahead": (ex > 0).mean(),
            "abs_yr": np.prod(1 + r["algo"]) ** (12 / len(r)) - 1, "worst_fall": (cur / cur.cummax() - 1).min(),
            "turnover": r["turnover"].mean(), "n": r["n"].mean()}


def line(label, r):
    s, a, b = stats(r), stats(r[r["month"] < SPLIT]), stats(r[r["month"] >= SPLIT])
    print(f"{label:34} vs market {s['ex_yr']*100:+5.1f}%/yr t={s['t']:.2f} ahead {s['ahead']*100:3.0f}% | "
          f"2021-23 {a['ex_yr']*100:+5.1f}% 2023-26 {b['ex_yr']*100:+5.1f}% | own return {s['abs_yr']*100:+5.1f}%/yr, "
          f"worst fall {s['worst_fall']*100:5.1f}% | turnover {s['turnover']*100:3.0f}% ~{s['n']:.0f} stocks")


def main(table_pkl, pred_pkl, panel, funds_txt):
    tab = pd.read_pickle(table_pkl)
    pred = pd.read_pickle(pred_pkl)[["month", "symbol", "score"]].rename(columns={"score": "ml"})
    tab = tab.merge(pred, on=["month", "symbol"], how="left")
    tab["steady"] = tab["smooth12"]
    tab["ml_r"] = tab.groupby("month")["ml"].rank(pct=True)
    tab["steady_r"] = tab.groupby("month")["smooth12"].rank(pct=True)
    tab["blend"] = (tab["ml_r"] + tab["steady_r"]) / 2
    months = sorted(tab["month"].unique())
    b = breadth_by_month(panel, funds_txt, pd.DatetimeIndex(months))
    mkt3 = tab.groupby("month")["mom3"].mean()
    healthy = {m: (b.get(m, 1) > 0.5) and (mkt3.get(m, 0) > 0) for m in months}
    print(f"market healthy in {np.mean(list(healthy.values()))*100:.0f}% of months")
    print(f"--- all {len(months)} months (steady score)")
    line("baseline (top 20%, equal weight)", run(tab, months=months))
    line("+ buffer (keep while in top 40%)", run(tab, buffer=True, months=months))
    line("+ weight calmer stocks more", run(tab, invvol=True, months=months))
    line("+ 50% cash when market unhealthy", run(tab, trend=healthy, months=months))
    line("all three", run(tab, buffer=True, invvol=True, trend=healthy, months=months))
    ml_months = sorted(tab.loc[tab["ml"].notna(), "month"].unique())
    print(f"--- {len(ml_months)} months where the ML model has out-of-sample scores")
    for sc in ["steady", "ml", "blend"]:
        line(f"{sc} score", run(tab, score=sc, months=ml_months))
        line(f"{sc} score + buffer", run(tab, score=sc, buffer=True, months=ml_months))


if __name__ == "__main__":
    main(*sys.argv[1:])
