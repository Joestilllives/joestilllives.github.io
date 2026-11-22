#!/usr/bin/env python3
"""Signal factory: generate many candidate signals from NSE daily data and test each one
the same strict way, so luck does not pass for skill.

Each candidate is computed at every month-end from data available that day, then judged on
the universe the money signal trades (liquid companies, size groups 1-4, listed 1+ year):
  IC      = rank correlation between the signal and next month's return, per month
  t       = mean IC / its standard error over the months
  periods = mean IC in 2017-19, 2020-22 and 2023-26 separately
A signal SURVIVES only if |t| >= 3 and its IC has the same sign in all three periods.
With ~200 candidates, about 0.5 would pass |t| >= 3 by chance, and far fewer would also
hold their sign in three separate periods.

Usage: python3 signal_factory.py DAILY_DIR MONTHLY_TABLE.pkl FUNDS.txt OUTDIR
"""
import glob, json, os, sys
import numpy as np
import pandas as pd

WINDOWS = [5, 21, 63, 126, 252]
PERIODS = [("2017-19", "2017-01-01", "2019-12-31"), ("2020-22", "2020-01-01", "2022-12-31"), ("2023-26", "2023-01-01", "2026-12-31")]


def load_ohlc(daily_dir, funds):
    cols = {"SYMBOL": "symbol", "SERIES": "series", "DATE1": "date", "PREV_CLOSE": "prev", "OPEN_PRICE": "open",
            "HIGH_PRICE": "high", "LOW_PRICE": "low", "CLOSE_PRICE": "close", "TTL_TRD_QNTY": "volume",
            "TURNOVER_LACS": "turnover", "NO_OF_TRADES": "trades", "DELIV_PER": "deliv"}
    parts = []
    for f in sorted(glob.glob(os.path.join(daily_dir, "*.csv"))):
        with open(f, "rb") as fh:
            if not fh.read(6).startswith(b"SYMBOL"):
                continue
        d = pd.read_csv(f, skipinitialspace=True, dtype=str)
        d.columns = [c.strip() for c in d.columns]
        d = d[[c for c in cols if c in d]].rename(columns=cols)
        d = d[d["series"].str.strip() == "EQ"]
        parts.append(d)
    a = pd.concat(parts, ignore_index=True)
    a["symbol"] = a["symbol"].str.strip()
    a = a[~a["symbol"].isin(funds)]
    a["date"] = pd.to_datetime(a["date"].str.strip(), format="%d-%b-%Y")
    for c in ["prev", "open", "high", "low", "close", "volume", "turnover", "trades", "deliv"]:
        a[c] = pd.to_numeric(a[c].astype(str).str.strip(), errors="coerce")
    return a.drop_duplicates(["symbol", "date"]).sort_values(["symbol", "date"])


def P(a, col):
    return a.pivot_table(index="date", columns="symbol", values=col)


class Keep(dict):
    """Stores only month-end rows of each signal (the full daily tables would not fit in memory)."""
    def __init__(self, dates):
        super().__init__(); self.dates = dates
    def __setitem__(self, k, v):
        if v is not None:
            super().__setitem__(k, v.reindex(self.dates, method="ffill").astype("float32"))


def build_signals(a, month_ends):
    """Daily matrices -> month-end values of each candidate signal (month-ends x symbols)."""
    close, prev, op, hi, lo = P(a, "close"), P(a, "prev"), P(a, "open"), P(a, "high"), P(a, "low")
    vol, turn, trades, deliv = P(a, "volume"), P(a, "turnover"), P(a, "trades"), P(a, "deliv")
    ret = (close / prev - 1).where(lambda r: r.abs() <= 0.25)  # beyond 25% = split/bonus, not a return
    lr = np.log1p(ret.fillna(0))
    lidx = lr.cumsum()
    on = np.log((op / prev).where(lambda r: (r > 0.75) & (r < 1.33)))            # overnight move
    intra = np.log((close / op).where(lambda r: (r > 0.75) & (r < 1.33)))         # open to close
    clv = ((close - lo) / (hi - lo)).where(hi > lo)                          # where it closes in the day's range
    rng = (hi - lo) / close
    mkt = ret.mean(axis=1)
    ill = ret.abs() / turn.replace(0, np.nan)                                 # price impact per Rs lakh
    tsize = (turn * 1e5 / trades.replace(0, np.nan))                          # average trade size, Rs
    dw = ret * deliv / 100                                                     # delivery-weighted move
    up = (ret > 0).astype(float).where(ret.notna())
    s = Keep(pd.DatetimeIndex(month_ends))
    for w in WINDOWS:
        mp = max(3, int(w * 0.6))
        R = lambda x: x.rolling(w, min_periods=mp)
        s[f"ret_{w}"] = lidx - lidx.shift(w)
        s[f"overnight_{w}"] = R(on).sum()
        s[f"intraday_{w}"] = R(intra).sum()
        s[f"tug_{w}"] = R(intra).sum() - R(on).sum()
        s[f"clv_{w}"] = R(clv).mean()
        s[f"range_{w}"] = R(rng).mean()
        s[f"vol_{w}"] = R(ret).std()
        s[f"skew_{w}"] = R(ret).skew() if w >= 21 else None
        s[f"max_{w}"] = R(ret).max()
        s[f"min_{w}"] = R(ret).min()
        s[f"upfrac_{w}"] = R(up).mean()
        s[f"illiq_{w}"] = np.log(R(ill).mean() + 1e-12)
        s[f"tradesize_{w}"] = np.log(R(tsize).mean())
        s[f"deliv_{w}"] = R(deliv).mean()
        s[f"delivmove_{w}"] = R(dw).sum()
        s[f"turnover_{w}"] = np.log(R(turn).mean() + 1e-6)
        s[f"volcv_{w}"] = R(vol).std() / R(vol).mean()
        if w >= 63:
            beta = (R(ret.mul(mkt, axis=0)).mean() - R(ret).mean().mul(mkt.rolling(w, min_periods=mp).mean(), axis=0)) \
                .div(mkt.rolling(w, min_periods=mp).var(), axis=0)
            s[f"beta_{w}"] = beta
            resid = ret.sub(beta.mul(mkt, axis=0))
            s[f"idiovol_{w}"] = R(resid).std()
    # changes and ratios between windows (trends of the slow measures)
    for base in ["deliv", "tradesize", "turnover", "illiq", "vol", "range", "clv"]:
        s[f"{base}_trend_21v126"] = s[f"{base}_21"] - s[f"{base}_126"]
        s[f"{base}_trend_5v63"] = s[f"{base}_5"] - s[f"{base}_63"]
    s["mom_12_1"] = lidx.shift(21) - lidx.shift(252)
    s["mom_6_1"] = lidx.shift(21) - lidx.shift(126)
    s["high52"] = lidx - lidx.rolling(252, min_periods=150).max()
    s["low52"] = lidx - lidx.rolling(252, min_periods=150).min()
    s["mom_accel"] = (lidx - lidx.shift(63)) - (lidx.shift(63) - lidx.shift(126))
    s["log_price"] = np.log(close)
    s["up_days_5"] = up.rolling(5, min_periods=3).sum()
    s["gap_count_21"] = (on.abs() > 0.03).astype(float).where(on.notna()).rolling(21, min_periods=10).sum()
    s["trades_growth_21v126"] = np.log(trades.rolling(21, min_periods=10).mean() / trades.rolling(126, min_periods=60).mean())
    # seasonality: the same calendar month's return in past years (Heston-Sadka)
    s["same_month_last_year"] = lidx.shift(252 - 21) - lidx.shift(252)
    s["same_month_2y"] = ((lidx.shift(252 - 21) - lidx.shift(252)) + (lidx.shift(504 - 21) - lidx.shift(504))) / 2
    return s


def test(signals, tab):
    uni = tab[tab["size_q"].isin([0, 1, 2, 3]) & tab["fwd"].notna()][["month", "symbol", "fwd"]]
    months = sorted(uni["month"].unique())
    res = []
    for name, m in signals.items():
        v = m.reindex(pd.DatetimeIndex(months)).stack(future_stack=True).rename("x").reset_index()
        v.columns = ["month", "symbol", "x"]
        d = uni.merge(v, on=["month", "symbol"], how="inner").replace([np.inf, -np.inf], np.nan).dropna()
        if d.empty:
            continue
        ic = d.groupby("month").apply(lambda g: g["x"].corr(g["fwd"], method="spearman") if len(g) > 30 else np.nan,
                                      include_groups=False).dropna()
        if len(ic) < 24:
            continue
        row = {"signal": name, "months": len(ic), "ic": ic.mean(), "t": ic.mean() / ic.std() * np.sqrt(len(ic)),
               "ic_pos": (ic > 0).mean()}
        for lab, a0, b0 in PERIODS:
            row[lab] = ic[(ic.index >= a0) & (ic.index <= b0)].mean()
        signs = np.sign([row[l] for l, _, _ in PERIODS])
        row["consistent"] = bool(abs(signs.sum()) == 3)
        row["survives"] = bool(abs(row["t"]) >= 3 and row["consistent"])
        res.append(row)
    return pd.DataFrame(res).sort_values("t", key=abs, ascending=False)


def main(daily_dir, table_pkl, funds_txt, outdir):
    os.makedirs(outdir, exist_ok=True)
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    a = load_ohlc(daily_dir, funds)
    print(f"loaded {len(a):,} rows, {a['symbol'].nunique()} companies", flush=True)
    tab = pd.read_pickle(table_pkl)
    sig = build_signals(a, sorted(tab["month"].unique()))
    print(f"{len(sig)} candidate signals", flush=True)
    r = test(sig, tab)
    r.to_csv(os.path.join(outdir, "factory_results.csv"), index=False)
    # month-end values of the survivors, for the model
    surv = r[r["survives"]]["signal"].tolist()
    months = pd.DatetimeIndex(sorted(tab["month"].unique()))
    frames = []
    for n in surv:
        v = sig[n].reindex(months).stack(future_stack=True).rename(n)
        frames.append(v)
    if frames:
        out = pd.concat(frames, axis=1).reset_index().rename(columns={"level_0": "month", "date": "month"})
        out.columns = ["month", "symbol"] + surv
        out.to_pickle(os.path.join(outdir, "survivor_values.pkl"))
    json.dump(surv, open(os.path.join(outdir, "survivors.json"), "w"))
    pd.set_option("display.width", 200)
    print(f"\n{len(r)} tested, {int(r['survives'].sum())} survive (|t| >= 3 and same sign in all 3 periods)")
    print(r.head(40).to_string(index=False, float_format=lambda x: f"{x:+.3f}"))


if __name__ == "__main__":
    main(*sys.argv[1:])
