#!/usr/bin/env python3
"""US sector moves overnight -> Indian stocks the next day.

Each month-end, for each Indian company, using the previous 126 trading days only: which
US sector fund's previous-day move best explains its daily moves (market-adjusted), and how
strongly (beta). Over the next month, each day's signal = beta x that US fund's move the
previous US session. Judged against the Indian stock's next-day moves, market-adjusted:
  gap      = open vs previous close (happens before anyone in India can trade)
  intraday = close vs open (tradable: buy at the open, sell at the close)
Split by size group, so slow-reacting small companies show separately.

Usage: python3 us_spillover.py DAILY_DIR FACTORS.pkl MONTHLY_TABLE.pkl FUNDS.txt
"""
import sys
import numpy as np
import pandas as pd
from signal_factory import load_ohlc, P

US = ["US tech", "US healthcare", "US energy stocks", "US financials", "US materials", "US industrials",
      "US consumer", "Chip stocks", "US biotech", "US defence", "Solar stocks", "Lithium/batteries", "S&P 500", "Nasdaq"]


def main(daily_dir, factors_pkl, table_pkl, funds_txt):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    a = load_ohlc(daily_dir, funds)
    close, prev, op = P(a, "close"), P(a, "prev"), P(a, "open")
    ret = (close / prev - 1).where(lambda r: r.abs() <= 0.25)
    gap = (op / prev - 1).where(lambda r: r.abs() <= 0.25)
    intra = (close / op - 1).where(lambda r: r.abs() <= 0.25)
    adj = lambda x: x.sub(x.mean(axis=1), axis=0)                 # vs the average stock that day
    ret, gap, intra = adj(ret), adj(gap), adj(intra)
    f = pd.read_pickle(factors_pkl)[US]
    us = np.log(f).diff()
    # the US session that closed BEFORE each Indian trading day = last US date strictly earlier
    us_prev = us.reindex(us.index.union(ret.index)).ffill().shift(1).reindex(ret.index)
    tab = pd.read_pickle(table_pkl)
    size = tab.pivot_table(index="month", columns="symbol", values="size_q")
    months = [m for m in sorted(tab["month"].unique()) if m >= pd.Timestamp("2017-01-01")]
    dates = ret.index
    out = []
    for i, m in enumerate(months[:-1]):
        k = dates.searchsorted(m, side="right")
        past = slice(max(0, k - 126), k)
        R, X = ret.iloc[past], us_prev.iloc[past]
        Xz = (X - X.mean()) / X.std()
        Rz = (R - R.mean()) / R.std()
        corr = pd.DataFrame({u: (Rz.mul(Xz[u], axis=0)).mean() for u in US})       # stocks x US funds
        corr = corr[(R.notna().sum() >= 100).reindex(corr.index, fill_value=False)].dropna(how="all")
        best = corr.abs().idxmax(axis=1)
        beta = pd.Series({s: corr.at[s, u] * R[s].std() / X[u].std() for s, u in best.items()})
        nxt = dates[(dates > m) & (dates <= months[i + 1])]
        for d in nxt:
            sig = beta * us_prev.loc[d, best.values].to_numpy()
            row = pd.DataFrame({"sig": sig, "gap": gap.loc[d].reindex(sig.index), "intra": intra.loc[d].reindex(sig.index),
                                "size": size.loc[m].reindex(sig.index) if m in size.index else np.nan})
            row = row.dropna()
            if len(row) < 50:
                continue
            for grp, sel in [("small (groups 1-2)", row["size"] <= 1), ("mid-large (3-4)", row["size"].isin([2, 3])), ("largest (5)", row["size"] == 4)]:
                r = row[sel]
                if len(r) > 30:
                    out.append({"date": d, "grp": grp, "ic_gap": r["sig"].corr(r["gap"], method="spearman"),
                                "ic_intra": r["sig"].corr(r["intra"], method="spearman"),
                                "spread_intra": r.loc[r.sig >= r.sig.quantile(.8), "intra"].mean() - r.loc[r.sig <= r.sig.quantile(.2), "intra"].mean()})
    o = pd.DataFrame(out)
    print(f"{o['date'].nunique()} trading days tested, 2017-2026")
    for grp, g in o.groupby("grp"):
        h = g["date"] < pd.Timestamp("2021-12-31")
        t = lambda x: x.mean() / x.std() * np.sqrt(len(x))
        print(f"{grp:20} opening gap: rank corr {g.ic_gap.mean():+.3f} (t {t(g.ic_gap):+.1f}) | tradable open->close: "
              f"{g.ic_intra.mean():+.3f} (t {t(g.ic_intra):+.1f}; first half {g[h].ic_intra.mean():+.3f}, second {g[~h].ic_intra.mean():+.3f}), "
              f"top-minus-bottom fifth {g.spread_intra.mean()*100:+.3f}%/day")


if __name__ == "__main__":
    main(*sys.argv[1:])
