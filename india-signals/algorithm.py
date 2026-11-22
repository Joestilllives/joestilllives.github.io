#!/usr/bin/env python3
"""The strongest signals as a simple, transparent monthly rule set (no machine learning).

Final version, chosen after testing the pieces one at a time (see README): the score is
the steadiness of the 12-month climb; heavy frenzy (3+ frenzy days last month) is removed
when HEAVY_FRENZY_FILTER is on. Momentum alone and the global-reversal signal did worse as
simple rules; a filter on ANY frenzy day removed a third of all stocks and hurt.

Each month-end:
 1. Universe: liquid NSE companies (>= Rs 1 crore traded a day, price >= Rs 20), ETFs and
    funds excluded, listed at least a year (so recent hot IPOs are out), and the most-traded
    fifth skipped (no edge among the most-watched stocks).
 2. Red flags removed: any frenzy day in the last month (volume 3x+ normal with delivery
    15+ points below normal), or any day in NSE's trade-for-trade surveillance segment.
 3. Score = average percentile rank of
      - 12-month momentum (skipping the latest month)
      - steadiness of the climb (12-month momentum / daily volatility)
      - reversal of global overreaction (stocks outside forces pushed DOWN last month rank higher)
 4. Buy the top 20% by score within each size group, equal weight, at the next day's close;
    hold to the next month-end. 0.3% costs charged on everything that changes.

Usage: python3 algorithm.py MONTHLY_TABLE.pkl BE_DAYS.pkl BHAVCOPY.csv OUTDIR
(MONTHLY_TABLE.pkl comes from combined.py run with FACTORS set.)
"""
import csv, json, os, sys
import numpy as np
import pandas as pd

COST = 0.003
TOP = 0.2
GROUPS = [0, 1, 2, 3]
HEAVY_FRENZY_FILTER = True
SPLIT = pd.Timestamp("2023-07-01")


def score_month(g):
    g = g[g["size_q"].isin(GROUPS)].copy()
    g["red_flag"] = (g["frenzy21"] >= 3) if HEAVY_FRENZY_FILTER else pd.Series(False, index=g.index)
    ok = ~g["red_flag"] & g[["mom12_1", "smooth12"]].notna().all(axis=1)
    s = pd.DataFrame(index=g.index)
    s["steady"] = g.loc[ok, "smooth12"].rank(pct=True)
    g["score"] = s["steady"]
    g["pick"] = False
    for q, gq in g[ok].groupby("size_q"):
        cut = gq["score"].quantile(1 - TOP)
        g.loc[gq.index[gq["score"] >= cut], "pick"] = True
    return g.join(s)


def backtest(tab):
    rows, prev = [], set()
    for m, g in tab.groupby("month"):
        g = score_month(g)
        if g["fwd"].isna().all():
            continue
        picks = set(g.loc[g["pick"], "symbol"])
        turnover = 1 - len(picks & prev) / max(len(picks), 1)
        prev = picks
        top = g.loc[g["pick"], "fwd"].mean() - turnover * COST
        flagged = g.loc[g["red_flag"], "fwd"].mean()
        rows.append({"month": m, "algo": top, "market": g["fwd"].mean(), "red_flags": flagged,
                     "stocks": len(picks), "turnover": turnover})
    return pd.DataFrame(rows)


def stats(df, col="algo"):
    ex = df[col] - df["market"]
    curve = ((1 + df[col]) / (1 + df["market"])).cumprod()
    return {"months": int(len(df)), "excess_per_month": float(ex.mean()), "excess_per_year": float((1 + ex.mean()) ** 12 - 1),
            "t": float(ex.mean() / ex.std() * np.sqrt(len(ex))), "months_ahead": float((ex > 0).mean()),
            "worst_month": float(ex.min()), "max_slide": float((curve / curve.cummax() - 1).min()),
            "total": float(np.prod(1 + df[col]) - 1), "market_total": float(np.prod(1 + df["market"]) - 1)}


def main(table_pkl, be_pkl, bhav, outdir):
    os.makedirs(outdir, exist_ok=True)
    tab = pd.read_pickle(table_pkl)
    be = pd.read_pickle(be_pkl).rolling(21, min_periods=1).sum()
    tab["be21"] = [be.at[m, s] if (m in be.index and s in be.columns) else 0.0 for m, s in zip(tab["month"], tab["symbol"])]
    res = backtest(tab)
    out = {"all": stats(res), "2021-23": stats(res[res.month < SPLIT]), "2023-26": stats(res[res.month >= SPLIT])}
    for k, s in out.items():
        print(f"{k:8} {s['months']} months: ahead {s['excess_per_month']*100:+.2f}%/month ({s['excess_per_year']*100:+.1f}%/yr), "
              f"t={s['t']:.2f}, ahead in {s['months_ahead']*100:.0f}% of months, worst month {s['worst_month']*100:+.1f}%, "
              f"deepest slide {s['max_slide']*100:.1f}%, total {s['total']*100:+.0f}% vs market {s['market_total']*100:+.0f}%")
    rf = res.dropna(subset=["red_flags"])
    print(f"red-flagged stocks (removed) vs market: {(rf.red_flags - rf.market).mean()*100:+.2f}%/month, "
          f"behind in {((rf.red_flags - rf.market) < 0).mean()*100:.0f}% of months")
    print(f"~{res.stocks.mean():.0f} stocks held, {res.turnover.mean()*100:.0f}% replaced each month")
    res.to_csv(os.path.join(outdir, "algorithm_monthly.csv"), index=False)
    json.dump(out, open(os.path.join(outdir, "algorithm_stats.json"), "w"), indent=1, default=str)

    # this month's list
    names = {r["TckrSymb"]: r["FinInstrmNm"].title() for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    last = tab["month"].max()
    g = score_month(tab[tab["month"] == last])
    picks = g[g["pick"]].sort_values("score", ascending=False)
    rows = [{"symbol": r.symbol, "company": names.get(r.symbol, r.symbol), "size_group": int(r.size_q) + 1,
             "score": round(float(r.score) * 100, 1),
             "below_52w_high_pct": round(float(-np.expm1(r.high52)) * 100, 1) if pd.notna(r.high52) else None,
             "return_12m_pct": round(float(np.expm1(r.mom12_1)) * 100, 1), "as_of": str(pd.Timestamp(last).date())}
            for r in picks.itertuples()]
    flags = g[g["red_flag"]]
    json.dump({"picks": rows, "red_flags": [{"symbol": s, "company": names.get(s, s),
               "why": f"{int(f)} frenzy days last month"}
               for s, f, b in zip(flags.symbol, flags.frenzy21, flags.be21)]},
              open(os.path.join(outdir, "algorithm_current.json"), "w"), indent=1)
    print(f"\nAs of {pd.Timestamp(last).date()}: {len(rows)} picks, {len(flags)} red-flagged. Top 12:")
    for r in rows[:12]:
        print(f"  {r['symbol']:12} group {r['size_group']}  score {r['score']:5.1f}  12m {r['return_12m_pct']:+6.1f}%  "
              f"{r['below_52w_high_pct']}% below 52-week high")


if __name__ == "__main__":
    main(*sys.argv[1:])
