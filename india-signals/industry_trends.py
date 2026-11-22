#!/usr/bin/env python3
"""Major industry trends, point-in-time. 'Industry' = each stock's 20 closest peers by past
daily co-movement (no hindsight sector lists). Tests, per month, rank correlation with the
next month's move vs the average company, size groups 1-4:
  theme trend 6m / 12m, theme breadth acceleration (last month vs 6m pace),
  laggard in a hot theme, leader in a hot theme, and theme trend among the smallest companies.
Usage: python3 industry_trends.py MONTHLY_TABLE.pkl
"""
import sys
import numpy as np
import pandas as pd

t = pd.read_pickle(sys.argv[1])
t = t[t["size_q"].isin([0, 1, 2, 3])].dropna(subset=["fwd", "peer_mom6"]).copy()
t["fx"] = t["fwd"] - t.groupby("month")["fwd"].transform("mean")
g = t.groupby("month")
pr = lambda c: g[c].rank(pct=True)
t["theme6"] = pr("peer_mom6")
t["theme_accel"] = pr("peer_ret1") - pr("peer_mom6")              # theme speeding up
t["hot_laggard"] = t["theme6"] - pr("rel_peer")                    # hot theme, stock behind its peers
t["hot_leader"] = t["theme6"] + pr("rel_peer")                     # hot theme, stock leading it
t["own6"] = pr("mom6_1")
for name, sub in [("all groups 1-4", t), ("smallest (group 1)", t[t.size_q == 0])]:
    print(name)
                   ("theme_accel", "theme speeding up"), ("hot_laggard", "laggard in a hot theme"), ("hot_leader", "leader in a hot theme")]:
        ic = sub.groupby("month").apply(lambda x: x[c].corr(x["fx"], method="spearman"), include_groups=False).dropna()
        sp = sub.groupby("month").apply(lambda x: x.loc[x[c] >= x[c].quantile(.8), "fx"].mean() - x.loc[x[c] <= x[c].quantile(.2), "fx"].mean(), include_groups=False).dropna()
        h = ic.index < "2022-01-01"
        print(f"  {lbl:34} rank corr {ic.mean():+.3f} (t {ic.mean()/ic.std()*np.sqrt(len(ic)):+.1f}; to 2021 {ic[h].mean():+.3f}, after {ic[~h].mean():+.3f}) "
              f"top-minus-bottom fifth {sp.mean()*100:+.2f}%/month")
