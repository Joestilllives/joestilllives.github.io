#!/usr/bin/env python3
"""New price-tape signals not in the factory, India-specific where possible.
  close_vs_vwap   close above the day's average price, 21-day mean (late buying / marking the close)
  upper_circuit   days closing at the high on a +5/10/20% band move, last 21 days
  lower_circuit   same, on the -5/10/20% band
  clv             where the close sits in the day's range, 21-day mean (accumulation)
  deliv_updown    delivery % on up days minus on down days, 63 days (who holds on up moves)
  trade_size_chg  average rupees per trade, last 21 days vs the prior 126 (bigger buyers arriving)
  price_level     low share price (lottery-like appeal)
Each is judged by monthly rank correlation with the next month's move vs the average company
(size groups 1-4), consistent in both halves; then whether it improves the money signal.
Usage: python3 new_signals.py DAILY_DIR MONTHLY_TABLE.pkl ENSEMBLE_PREDS.pkl CORP_ACTIONS.csv FUNDS.txt
"""
import glob, os, sys
import numpy as np
import pandas as pd
import audit as AU


def load(daily_dir, funds):
    cols = {"SYMBOL": "symbol", "SERIES": "series", "DATE1": "date", "PREV_CLOSE": "prev", "HIGH_PRICE": "high",
            "LOW_PRICE": "low", "CLOSE_PRICE": "close", "AVG_PRICE": "avg", "TURNOVER_LACS": "turnover",
            "NO_OF_TRADES": "trades", "DELIV_PER": "deliv"}
    parts = []
    for f in sorted(glob.glob(os.path.join(daily_dir, "*.csv"))):
        with open(f, "rb") as fh:
            if not fh.read(6).startswith(b"SYMBOL"):
                continue
        d = pd.read_csv(f, skipinitialspace=True, dtype=str)
        d.columns = [c.strip() for c in d.columns]
        d = d[[c for c in cols if c in d]].rename(columns=cols)
        parts.append(d[d["series"].str.strip() == "EQ"])
    a = pd.concat(parts, ignore_index=True)
    a["symbol"] = a["symbol"].str.strip()
    a = a[~a["symbol"].isin(funds)]
    a["date"] = pd.to_datetime(a["date"].str.strip(), format="%d-%b-%Y")
    for c in list(cols.values())[3:]:
        a[c] = pd.to_numeric(a[c].astype(str).str.strip(), errors="coerce")
    return a.drop_duplicates(["symbol", "date"])


def main(daily_dir, table_pkl, preds_pkl, ca_csv, funds_txt):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    a = load(daily_dir, funds)
    P = lambda c: a.pivot_table(index="date", columns="symbol", values=c)
    close, prev, high, low, avg = P("close"), P("prev"), P("high"), P("low"), P("avg")
    turn, trades, deliv = P("turnover"), P("trades"), P("deliv")
    r = close / prev - 1
    ok = r.abs() <= 0.25
    rng = (high - low).where(lambda x: x > 0)
    sig = {}
    sig["close_vs_vwap"] = (close / avg - 1).where(ok).rolling(21, min_periods=15).mean()
    at_high, at_low = (close >= high * 0.999), (close <= low * 1.001)
    band = lambda x: np.any([(x - b).abs() < 0.003 for b in (0.05, 0.10, 0.20)], axis=0)
    sig["upper_circuit"] = pd.DataFrame(band(r) & at_high.values, index=r.index, columns=r.columns).astype(float).rolling(21, min_periods=15).sum()
    sig["lower_circuit"] = pd.DataFrame(band(-r) & at_low.values, index=r.index, columns=r.columns).astype(float).rolling(21, min_periods=15).sum()
    sig["clv"] = ((2 * close - high - low) / rng).where(ok).rolling(21, min_periods=15).mean()
    up, dn = deliv.where(r > 0), deliv.where(r < 0)
    sig["deliv_updown"] = up.rolling(63, min_periods=20).mean() - dn.rolling(63, min_periods=20).mean()
    ts = turn / trades
    sig["trade_size_chg"] = np.log(ts.rolling(21, min_periods=15).mean() / ts.shift(21).rolling(126, min_periods=80).mean())
    sig["price_level"] = -np.log(close)
    tab = pd.read_pickle(table_pkl)
    tab = tab[tab["size_q"].isin([0, 1, 2, 3])].dropna(subset=["fwd"]).copy()
    tab["fx"] = tab["fwd"] - tab.groupby("month")["fwd"].transform("mean")
    dates = close.index
    for k, v in sig.items():
        idx = [dates[dates <= m][-1] for m in sorted(tab["month"].unique())]
        mv = v.loc[idx]; mv.index = sorted(tab["month"].unique())
        tab = tab.merge(mv.stack().rename(k).reset_index().rename(columns={"level_0": "month"}), on=["month", "symbol"], how="left")
    print(f"{tab['month'].nunique()} months, {len(tab):,} stock-months (size groups 1-4)\n")
    print(f"{'signal':16} {'rank corr':>9} {'t':>6} {'to 2021':>8} {'after':>7} {'top-bottom fifth':>17} {'within small (grp 1)':>21}")
    for k in sig:
        def ic(d):
            return d.groupby("month").apply(lambda x: x[k].corr(x["fx"], method="spearman") if x[k].nunique() > 5 else np.nan, include_groups=False).dropna()
        s = ic(tab); h = s.index < "2022-01-01"; s0 = ic(tab[tab.size_q == 0])
        sp = tab.groupby("month").apply(lambda x: x.loc[x[k] >= x[k].quantile(.8), "fx"].mean() - x.loc[x[k] <= x[k].quantile(.2), "fx"].mean(), include_groups=False)
        print(f"{k:16} {s.mean():+9.3f} {s.mean()/s.std()*np.sqrt(len(s)):+6.1f} {s[h].mean():+8.3f} {s[~h].mean():+7.3f} {sp.mean()*100:+15.2f}%/m "
              f"{s0.mean():+10.3f} (t {s0.mean()/s0.std()*np.sqrt(len(s0)):+.1f})")
    # circuit counts are sparse: compare stocks with >=2 upper/lower circuit days vs the rest
    for k in ["upper_circuit", "lower_circuit"]:
        hit = tab[tab[k] >= 2]
        print(f"   {k} >=2 days: {len(hit):,} stock-months, next month vs average company {hit['fx'].mean()*100:+.2f}% "
              f"(median {hit['fx'].median()*100:+.2f}%), share beating average {(hit['fx']>0).mean()*100:.0f}%")
    tab.to_pickle(os.path.join(os.path.dirname(preds_pkl), "new_signals_table.pkl"))
    # does any of them improve the money signal? (as an extra red flag: drop the worst fifth)
    p = pd.read_pickle(preds_pkl).merge(tab[["month", "symbol"] + list(sig)], on=["month", "symbol"], how="left")
    p = AU.eligible(p, pd.read_csv(ca_csv, parse_dates=["date"]))
    base = AU.basket(p, "blend"); e0 = AU.stats(base)
    f = lambda d: AU.stats(d)[0] * 100
    h0 = base["month"] < "2022-01-01"
    print(f"\nmoney signal: {e0[0]*100:+.1f}%/yr (to 2021 {f(base[h0]):+.1f}, after {f(base[~h0]):+.1f})")
    for k in sig:
        for direction, lbl in [(1, "drop lowest fifth"), (-1, "drop highest fifth")]:
            q = p.copy()
            rk = (direction * q[k]).groupby(q["month"]).rank(pct=True)
            q["ok"] = q["ok"] & ~(rk <= 0.2)
            b = AU.basket(q, "blend"); h = b["month"] < "2022-01-01"
            print(f"   {k:16} {lbl:19} {f(b):+.1f}%/yr (to 2021 {f(b[h]):+.1f}, after {f(b[~h]):+.1f})")


if __name__ == "__main__":
    main(*sys.argv[1:])
