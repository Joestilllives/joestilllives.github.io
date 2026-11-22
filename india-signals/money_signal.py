#!/usr/bin/env python3
"""NSE money signal: the final algorithm (blend + buffer, optional trend overlay).

Run once a month, after the last trading day of the month.

 1. UNIVERSE   NSE companies (EQ series, ETFs/funds excluded) with average daily traded value
               >= Rs 1 crore over 20 days, price >= Rs 20, listed >= 252 trading days.
               Rank all of them by traded value into 5 equal size groups; drop the
               most-traded group (no edge among the most-watched stocks).
 2. RED FLAG   Drop stocks with 3+ frenzy days in the last 21 trading days
               (frenzy day = volume >= 3x its 20-day average AND delivery % at least
               15 points below its 60-day average).
 3. SCORE      a) Steady climb = (12-month return skipping the last month) / daily volatility
                  over the last year, as a percentile rank among all stocks that month.
               b) Model score = the gradient-boosted model in combined.py (about 30 signals:
                  trend, money flow, frenzy, peers, 50 global factors, IPO, Wikipedia,
                  market mood), retrained every 3 months on past months only, as a
                  percentile rank.
               Blend = average of (a) and (b).
 4. SELECT     Within each of the 4 size groups, BUY stocks in the top 20% by blend.
               BUFFER: keep a stock you already hold while it stays in the top 40% of its
               group; sell it when it falls below.
 5. WEIGHT     Equal amounts in every holding. Trade at the next day's close.
 6. OVERLAY    (optional, for safety) If half or fewer of liquid stocks are above their
               200-day average, OR the average stock fell over the last 3 months:
               keep only half the money in the basket and the rest in a liquid fund.

Tested out-of-sample Feb 2019-Sep 2026 (94 months), after 0.3% costs:
+11.9%/yr vs the average company, t = 5.2, ahead in 72% of months, ~31% turnover.

Usage: python3 money_signal.py OUTDIR TABLE.pkl PREDICTIONS.pkl PANEL.pkl FUNDS.txt BHAVCOPY.csv [PREVIOUS_HOLDINGS.csv]
"""
import csv, json, os, sys
import numpy as np
import pandas as pd
from improve import breadth_by_month

BUY, KEEP, GROUPS = 0.2, 0.4, [0, 1, 2, 3]


def main(outdir, table, preds, panel, funds_txt, bhav, prev=None):
    os.makedirs(outdir, exist_ok=True)
    tab = pd.read_pickle(table)
    pr = pd.read_pickle(preds)[["month", "symbol", "score"]].rename(columns={"score": "ml"})
    last = tab["month"].max()
    g = tab[tab["month"] == last].merge(pr[pr["month"] == last], on=["month", "symbol"], how="left")
    g["steady_r"] = g["smooth12"].rank(pct=True)
    g["ml_r"] = g["ml"].rank(pct=True)
    g["blend"] = (g["steady_r"] + g["ml_r"]) / 2
    g = g[g["size_q"].isin(GROUPS) & (g["frenzy21"] < 3)].dropna(subset=["blend"]).copy()
    g["rank_in_group"] = g.groupby("size_q")["blend"].rank(pct=True)
    held = set(pd.read_csv(prev)["symbol"]) if prev else set()
    g["action"] = np.select(
        [g["rank_in_group"] >= 1 - BUY, (g["rank_in_group"] >= 1 - KEEP) & g["symbol"].isin(held)],
        ["buy / hold", "keep (buffer)"], "")
    sells = sorted(held - set(g.loc[g["action"] != "", "symbol"]))
    names = {r["TckrSymb"]: r["FinInstrmNm"].title() for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    b = breadth_by_month(panel, funds_txt, pd.DatetimeIndex([last])).iloc[0]
    mkt3 = tab.loc[tab["month"] == last, "mom3"].mean()
    healthy = bool(b > 0.5 and mkt3 > 0)
    basket = g[g["action"] != ""].sort_values(["size_q", "blend"], ascending=[True, False])
    path = os.path.join(outdir, f"money_signal_{pd.Timestamp(last):%Y-%m}.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "company", "size_group", "blend_score", "steady_rank", "model_rank", "action", "weight_pct"])
        for r in basket.itertuples():
            w.writerow([r.symbol, names.get(r.symbol, r.symbol), int(r.size_q) + 1, round(r.blend * 100, 1),
                        round(r.steady_r * 100), round(r.ml_r * 100), r.action, round(100 / len(basket), 2)])
    json.dump({"as_of": str(pd.Timestamp(last).date()), "stocks": len(basket), "sell": sells,
               "share_above_200d": round(float(b), 3), "avg_stock_3m": round(float(np.expm1(mkt3)), 4),
               "market_healthy": healthy, "overlay": "fully invested" if healthy else "50% basket, 50% liquid fund"},
              open(os.path.join(outdir, "money_signal_status.json"), "w"), indent=1)
    print(f"As of {pd.Timestamp(last).date()}: {len(basket)} stocks; market healthy: {healthy} "
          f"({b*100:.0f}% of stocks above 200-day average, average stock {np.expm1(mkt3)*100:+.1f}% over 3 months)")
    print(f"Overlay: {'fully invested' if healthy else 'hold 50% basket, 50% liquid fund'}")
    print(f"Saved {path}")
    for r in basket.groupby("size_q").head(3).itertuples():
        print(f"  group {int(r.size_q)+1}  {r.symbol:12} {names.get(r.symbol, '')[:30]:30} blend {r.blend*100:5.1f}")


if __name__ == "__main__":
    main(*sys.argv[1:])
