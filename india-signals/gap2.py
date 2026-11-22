#!/usr/bin/env python3
"""Gap 2: picks that move into NSE's surveillance segments (series BE/BZ, trade-for-trade)
during the holding month. The test's prices follow the EQ series only, so the price is frozen
while a stock trades in BE/BZ. Here each pick's TRUE return follows it across EQ, BE and BZ,
and is compared with the recorded EQ-only return.

Usage: python3 gap2.py DAILY_DIR ENSEMBLE_PREDS.pkl CORP_ACTIONS.csv
"""
import glob, os, sys
import numpy as np
import pandas as pd
import audit as AU


def all_series_prices(daily_dir):
    parts = []
    for f in sorted(glob.glob(os.path.join(daily_dir, "*.csv"))):
        with open(f, "rb") as fh:
            if not fh.read(6).startswith(b"SYMBOL"):
                continue
        d = pd.read_csv(f, skipinitialspace=True, usecols=[0, 1, 2, 3, 8], dtype=str)
        d.columns = ["symbol", "series", "date", "prev", "close"]
        d["series"] = d["series"].str.strip()
        parts.append(d[d["series"].isin(["EQ", "BE", "BZ"])])
    a = pd.concat(parts, ignore_index=True)
    a["symbol"] = a["symbol"].str.strip()
    a["date"] = pd.to_datetime(a["date"].str.strip(), format="%d-%b-%Y")
    for c in ["prev", "close"]:
        a[c] = pd.to_numeric(a[c].str.strip(), errors="coerce")
    a = a.sort_values(["symbol", "date", "series"]).drop_duplicates(["symbol", "date"])
    r = (a["close"] / a["prev"] - 1).where(lambda x: x.abs() <= 0.25).fillna(0)
    a["lp"] = np.log1p(r).groupby(a["symbol"]).cumsum()
    return a


def main(daily_dir, preds, ca_csv):
    a = all_series_prices(daily_dir)
    lp = a.pivot_table(index="date", columns="symbol", values="lp").ffill()
    ser = a.pivot_table(index="date", columns="symbol", values="series", aggfunc="first")
    dates = lp.index
    p = AU.eligible(pd.read_pickle(preds), pd.read_csv(ca_csv, parse_dates=["date"]))
    base = AU.basket(p, "blend")
    months = list(base["month"])
    pm = p.set_index(["month", "symbol"])["fwd"]
    rows = []
    for i, m in enumerate(months[:-1]):
        a0 = dates[min(dates.searchsorted(m) + 1, len(dates) - 1)]
        b0 = dates[min(dates.searchsorted(months[i + 1]) + 1, len(dates) - 1)]
        for s in base.loc[i, "symbols"]:
            if s not in ser:
                continue
            window = ser[s].loc[a0:b0]
            moved = window.isin(["BE", "BZ"]).any()
            true = np.expm1(lp[s].loc[b0] - lp[s].loc[a0]) if not (np.isnan(lp[s].loc[b0]) or np.isnan(lp[s].loc[a0])) else np.nan
            rows.append({"month": m, "symbol": s, "moved": bool(moved), "recorded": pm.get((m, s), np.nan), "true": true})
    d = pd.DataFrame(rows)
    mv = d[d["moved"]]
    n_months = d["month"].nunique()
    per_month_gap = (mv["recorded"] - mv["true"]).sum() / d.groupby("month").size().mean() / n_months
    print(f"{len(d):,} pick-months checked; {len(mv)} ({len(mv)/len(d)*100:.2f}%) moved into BE/BZ during the holding month")
    if len(mv):
        print(f"  those picks: recorded {mv['recorded'].mean()*100:+.1f}% on average, true {mv['true'].mean()*100:+.1f}% "
              f"(difference {(mv['recorded']-mv['true']).mean()*100:+.1f} points per affected pick)")
        print(f"  effect on the basket: {per_month_gap*100:+.3f} points per month = about {per_month_gap*12*100:+.2f} points per year overstated")
        print(mv.sort_values("true").head(10).to_string(index=False, float_format=lambda x: f"{x*100:+.1f}%"))
    # all picks, recorded vs true, as a check on the whole series
    both = d.dropna(subset=["recorded", "true"])
    print(f"  all picks: recorded {both['recorded'].mean()*100:+.2f}% vs true {both['true'].mean()*100:+.2f}% per month")


if __name__ == "__main__":
    main(*sys.argv[1:])
