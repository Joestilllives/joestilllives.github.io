#!/usr/bin/env python3
"""Mutual fund flows -> stocks. AMFI's monthly report gives each equity fund category's
net inflow. Funds must invest new money, so do strong small-cap fund inflows push small
caps ahead of large caps? The report comes out around the 10th of the next month, so
each test period runs from the first trading day on/after the 10th of the month after
the flow month, for one month (and three months).

Usage: python3 fund_flows.py AMFI_DIR PANEL.pkl FUNDS.txt
"""
import glob, os, re, sys
import numpy as np
import pandas as pd
from backtest import prepare

CATS = {"Large Cap Fund": "large", "Mid Cap Fund": "mid", "Small Cap Fund": "small", "Sectoral/Thematic Funds": "thematic",
        "Flexi Cap Fund": "flexi", "Multi Cap Fund": "multi"}
MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def read_flows(amfi_dir):
    rows = []
    for f in sorted(glob.glob(os.path.join(amfi_dir, "am*repo.xls"))):
        m = re.search(r"am([a-z]{3})(\d{4})repo", f)
        month = pd.Timestamp(int(m.group(2)), MON[m.group(1)], 1)
        try:
            x = pd.read_excel(f, header=None)
        except Exception:
            continue
        for _, r in x.iterrows():
            vals = [v for v in r.values if str(v) != "nan"]
            name = next((str(v).strip() for v in vals if isinstance(v, str) and str(v).strip() in CATS), None)
            if not name:
                continue
            nums = [float(v) for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if len(nums) >= 6:   # schemes, folios, mobilised, redeemed, net, AUM, ...
                rows.append({"month": month, "cat": CATS[name], "net": nums[4], "aum": nums[5]})
    df = pd.DataFrame(rows).drop_duplicates(["month", "cat"])
    w = df.pivot(index="month", columns="cat", values="net")
    a = df.pivot(index="month", columns="cat", values="aum")
    return w, (w / a.shift(1)).rename(columns=lambda c: c + "_pct")


def main(amfi_dir, panel, funds_txt):
    net, pct = read_flows(amfi_dir)
    print(f"flows for {len(net)} months, {net.index.min():%b %Y}..{net.index.max():%b %Y}")
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    p = p[p["liquid"]]
    daily = p.groupby(["date", "size_q"])["ret"].mean().unstack()
    lg = np.log1p(daily).cumsum()
    dates = lg.index
    rows = []
    for mth in pct.index:
        start = dates.searchsorted(mth + pd.DateOffset(months=1, days=9))
        for h, n in [("1m", 21), ("3m", 63)]:
            if start + n >= len(dates):
                continue
            mv = np.expm1(lg.iloc[start + n] - lg.iloc[start])
            rows.append({"month": mth, "h": h, "small_minus_large": mv[0] + mv[1] - mv[3] - mv[4],
                         "all": mv.mean()})
    out = pd.DataFrame(rows).pivot(index="month", columns="h", values=["small_minus_large", "all"])
    out.columns = [f"{a}_{b}" for a, b in out.columns]
    d = pct.join(out, how="inner").dropna(subset=["small_pct"])
    d = d[d.index >= "2019-06-01"]
    print(f"{len(d)} months tested")
    for c in ["small_pct", "mid_pct", "thematic_pct", "large_pct"]:
        if c not in d:
            continue
        z = d[c] - d[c].rolling(12, min_periods=6).mean()   # inflow vs its own past year
        for tgt in ["small_minus_large_1m", "small_minus_large_3m", "all_1m", "all_3m"]:
            ok = z.notna() & d[tgt].notna()
            hi = d.loc[ok & (z > z[ok].median()), tgt].mean()
            lo = d.loc[ok & (z <= z[ok].median()), tgt].mean()
            print(f"{c:13} -> {tgt:22} corr {z[ok].corr(d.loc[ok, tgt]):+.2f}   after above-normal inflows {hi*100:+5.1f}%   after below-normal {lo*100:+5.1f}%")


if __name__ == "__main__":
    main(*sys.argv[1:])
