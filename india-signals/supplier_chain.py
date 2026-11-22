#!/usr/bin/env python3
"""Western customers -> Indian suppliers (Swanson-style chain, Cohen & Frazzini's
'economic links'). No supplier list exists, so links are found from data: each month, for
each Indian company, the Western company whose monthly market-adjusted returns moved most
like it over the previous 36 months (point-in-time). Then: does that Western partner's move
THIS month predict the Indian company's move NEXT month (bought at the next day's close)?

Usage: python3 supplier_chain.py MONTHLY_TABLE.pkl OUTDIR
"""
import os, sys, time
import numpy as np
import pandas as pd
from factors import fetch

WEST = {  # big outsourcers to Indian pharma, auto parts, aerospace, IT/engineering, chemicals, apparel, electronics
    "pharma": ["PFE", "MRK", "LLY", "JNJ", "ABBV", "AMGN", "GILD", "BMY", "NVO", "AZN", "NVS", "SNY", "GSK", "TEVA", "VTRS"],
    "auto": ["F", "GM", "TSLA", "STLA", "TM", "HMC", "VOW3.DE", "BMW.DE", "MBG.DE", "VLVLY", "CAT", "DE", "PCAR", "CMI"],
    "aero_defence": ["BA", "AIR.PA", "GE", "RTX", "HON", "LMT", "SAF.PA", "RR.L"],
    "tech_it": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "IBM", "ACN", "CTSH", "EPAM", "ORCL", "SAP", "CRM"],
    "semis_electronics": ["NVDA", "INTC", "TXN", "ON", "NXPI", "QCOM", "AMD", "JBL", "FLEX"],
    "chemicals": ["DOW", "DD", "BAS.DE", "LYB", "AKZA.AS", "SHW", "PPG", "CTVA", "FMC"],
    "industrial": ["SIE.DE", "ABBN.SW", "SU.PA", "EMR", "ETN", "ROK", "MMM"],
    "apparel_retail": ["NKE", "WMT", "TGT", "ITX.MC", "HM-B.ST", "PVH", "RL", "GAP"],
    "medtech": ["MDT", "ABT", "BSX", "SYK"],
}


def month_returns(series):
    m = series.resample("ME").last()
    return np.log(m).diff()


def main(table_pkl, outdir):
    os.makedirs(outdir, exist_ok=True)
    cache = os.path.join(outdir, "west.pkl")
    if os.path.exists(cache):
        W = pd.read_pickle(cache)
    else:
        cols = {}
        for grp, ticks in WEST.items():
            for t in ticks:
                s = fetch(t)
                if s is not None and len(s) > 500:
                    cols[t] = s
                time.sleep(0.6)
        cols["^GSPC"] = fetch("^GSPC")
        W = pd.DataFrame(cols)
        W.to_pickle(cache)
    wr = W.apply(month_returns)
    wx = wr.drop(columns="^GSPC").sub(wr["^GSPC"], axis=0)          # Western move vs S&P 500
    print(f"{wx.shape[1]} Western companies, monthly from {wx.index.min():%Y-%m}")
    tab = pd.read_pickle(table_pkl)
    tab = tab[tab["size_q"].isin([0, 1, 2, 3])]
    # Indian monthly market-adjusted move in month t (from the table's 1-month momentum)
    tab["own_t"] = tab["mom1"] - tab.groupby("month")["mom1"].transform("mean")
    ind = tab.pivot_table(index="month", columns="symbol", values="own_t")
    ind.index = ind.index.to_period("M").to_timestamp("M")
    wx = wx.reindex(ind.index)
    rows = []
    months = list(ind.index)
    for i, m in enumerate(months):
        if i < 36:
            continue
        past_i, past_w = ind.iloc[i - 36:i], wx.iloc[i - 36:i]
        ok_w = past_w.columns[past_w.notna().sum() >= 30]
        Wz = (past_w[ok_w] - past_w[ok_w].mean()) / past_w[ok_w].std()
        for s in ind.columns[ind.iloc[i - 36:i].notna().sum() >= 30]:
            x = past_i[s]
            xz = (x - x.mean()) / x.std()
            c = (Wz.mul(xz, axis=0)).mean()          # correlation with each Western company
            if c.isna().all():
                continue
            partner = c.idxmax()
            rows.append({"month": tab["month"].unique()[i] if False else m, "symbol": s, "partner": partner,
                         "link": c.max(), "partner_move": wx.at[m, partner]})
    L = pd.DataFrame(rows)
    tab2 = tab.assign(month=tab["month"].dt.to_period("M").dt.to_timestamp("M"))
    d = L.merge(tab2[["month", "symbol", "fwd", "own_t"]], on=["month", "symbol"]).dropna(subset=["fwd", "partner_move"])
    d["fwd_x"] = d["fwd"] - d.groupby("month")["fwd"].transform("mean")
    d.to_pickle(os.path.join(outdir, "links.pkl"))
    grp = {t: g for g, ts in WEST.items() for t in ts}
    print(f"{len(d):,} stock-months; median link strength {d['link'].median():.2f}")
    print("most common partners:", d.groupby("partner").size().sort_values(ascending=False).head(8).to_dict())
    for label, sub in [("all links", d), ("strong links (top third)", d[d["link"] >= d["link"].quantile(2 / 3)])]:
        ic = sub.groupby("month").apply(lambda g: g["partner_move"].corr(g["fwd_x"], method="spearman"), include_groups=False).dropna()
        spread = sub.groupby("month").apply(lambda g: g.loc[g.partner_move >= g.partner_move.quantile(.8), "fwd_x"].mean()
                                            - g.loc[g.partner_move <= g.partner_move.quantile(.2), "fwd_x"].mean(), include_groups=False).dropna()
        half = ic.index < "2022-07-01"
        print(f"{label:26} rank corr {ic.mean():+.3f} (t {ic.mean()/ic.std()*np.sqrt(len(ic)):+.2f}; first half {ic[half].mean():+.3f}, "
              f"second {ic[~half].mean():+.3f}); top-minus-bottom fifth {spread.mean()*100:+.2f}%/month, {len(ic)} months")
    # by Western sector
    d["sector"] = d["partner"].map(grp)
    print("by the partner's sector (rank corr, t):")
    for sct, g in d.groupby("sector"):
        ic = g.groupby("month").apply(lambda x: x["partner_move"].corr(x["fwd_x"], method="spearman") if len(x) > 10 else np.nan, include_groups=False).dropna()
        if len(ic) > 20:
            print(f"   {sct:18} {ic.mean():+.3f}  t {ic.mean()/ic.std()*np.sqrt(len(ic)):+.2f}  (~{g.groupby('month').size().mean():.0f} Indian stocks/month)")


if __name__ == "__main__":
    main(*sys.argv[1:])
