#!/usr/bin/env python3
"""Trend-following tests on NSE stocks with monthly rebalancing.

Each month-end every liquid stock is scored. Within each size group (traded-value
quintile) the top 20% by score is bought at the next day's close and held until
the next rebalance, equal weight. That portfolio is compared with all liquid
stocks, equal weight, over the same days. Costs are charged on what changes.

Scores:
  mom12_1   return over the last 12 months, skipping the most recent month
  mom6_1    return over the last 6 months, skipping the most recent month
  high52    how close the price is to its 52-week high
  smooth12  12-1 month return divided by its daily volatility (steady climbers)
  rev1      last month's return (expected to REVERSE, so bottom group is "best")
  industry6 the stock's sector's average 6-1 month return (theme momentum)
  combo     average rank of mom12_1, high52 and industry6, skipping recent frenzies

Usage: python3 momentum.py PANEL.pkl INDUSTRY.csv [OUT.json]
"""
import csv, json, sys
import numpy as np
import pandas as pd
from backtest import prepare, SPLIT, COST_ROUND_TRIP

TOP = 0.2


def build(p, industry):
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()  # delisted: held at last price
    liq = p.pivot_table(index="date", columns="symbol", values="liquid", aggfunc="first").fillna(False).astype(bool)
    size = p.pivot_table(index="date", columns="symbol", values="turn_avg20")
    n = p.pivot_table(index="date", columns="symbol", values="n")
    frenzy = ((p["vol_x"] >= 3) & (p["deliv_jump"] <= -15)).astype(float)
    fz = p.assign(f=frenzy).pivot_table(index="date", columns="symbol", values="f").fillna(0).rolling(5, min_periods=1).max()
    ret = lp.diff()
    feats = {
        "mom12_1": lp.shift(21) - lp.shift(252),
        "mom6_1": lp.shift(21) - lp.shift(126),
        "high52": lp - lp.rolling(252, min_periods=200).max(),
        "smooth12": (lp.shift(21) - lp.shift(252)) / (ret.rolling(252, min_periods=200).std() * np.sqrt(231)),
        "rev1": -(lp - lp.shift(21)),
    }
    ind = pd.Series(industry)
    return lp, liq, size, n, fz, feats, ind


def run(p, industry):
    lp, liq, size, n, fz, feats, ind = build(p, industry)
    dates = lp.index
    month_ends = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max().values
    month_ends = [d for d in month_ends if dates.get_loc(d) >= 260][:-1]
    out = {name: [] for name in list(feats) + ["industry6", "combo"]}
    prev_hold = {name: set() for name in out}
    for i, t in enumerate(month_ends):
        k = dates.get_loc(t)
        nxt = month_ends[i + 1] if i + 1 < len(month_ends) else dates[-2]
        k_in, k_out = k + 1, dates.get_loc(nxt) + 1
        if k_out >= len(dates):
            break
        uni = liq.loc[t] & (n.loc[t] >= 252)
        syms = uni[uni].index
        fwd = np.expm1(lp.iloc[k_out][syms] - lp.iloc[k_in][syms]).dropna()
        syms = fwd.index
        bench = fwd.mean()
        sq = pd.qcut(size.loc[t, syms].rank(method="first"), 5, labels=False)
        scores = {name: f.loc[t, syms] for name, f in feats.items()}
        # sector momentum: average 6-1 month return of liquid stocks in the same sector
        sec = ind.reindex(syms)
        sec_mom = scores["mom6_1"].groupby(sec).mean()
        scores["industry6"] = sec.map(sec_mom).astype(float)
        r = pd.DataFrame({k2: v.rank(pct=True) for k2, v in scores.items() if k2 in ("mom12_1", "high52", "industry6")})
        combo = r.mean(axis=1, skipna=False)
        combo[fz.loc[t, syms] > 0] = np.nan  # skip stocks with a frenzy day in the last 5 sessions
        scores["combo"] = combo
        for name, sc in scores.items():
            sc = sc.dropna()
            if len(sc) < 50:
                continue
            picks, lows = [], []
            for q in range(5):  # top and bottom 20% within each size group
                g = sc[sq.reindex(sc.index) == q]
                if len(g) >= 5:
                    picks += list(g[g >= g.quantile(1 - TOP)].index)
                    lows += list(g[g <= g.quantile(TOP)].index)
            hold = set(picks)
            turnover = 1 - len(hold & prev_hold[name]) / max(len(hold), 1)
            prev_hold[name] = hold
            top_ret = fwd[picks].mean() - turnover * COST_ROUND_TRIP
            # benchmark = every stock this score could have picked from (for sector scores
            # that means today's index members only, so both sides share that survivor bias)
            out[name].append({"month": str(pd.Timestamp(t).date()), "top": top_ret, "bottom": fwd[lows].mean(),
                              "bench": fwd[sc.index].mean(), "bench_all": bench, "n": len(picks), "turnover": turnover})
    return out


def summarize(rows):
    df = pd.DataFrame(rows)
    df["ex"] = df["top"] - df["bench"]
    df["spread"] = df["top"] - df["bottom"]
    res = {}
    for label, part in [("all", df), ("first_half", df[pd.to_datetime(df.month) < SPLIT]),
                        ("second_half", df[pd.to_datetime(df.month) >= SPLIT])]:
        if len(part) < 6:
            continue
        ex = part["ex"]
        res[label] = {
            "months": int(len(part)),
            "excess_per_month": round(float(ex.mean()), 4),
            "excess_per_year": round(float((1 + ex.mean()) ** 12 - 1), 4),
            "t": round(float(ex.mean() / ex.std() * np.sqrt(len(ex))), 2),
            "months_ahead": round(float((ex > 0).mean()), 3),
            "top_minus_bottom_per_month": round(float(part["spread"].mean()), 4),
            "top_total": round(float(np.prod(1 + part["top"]) - 1), 3),
            "bench_total": round(float(np.prod(1 + part["bench"]) - 1), 3),
            "avg_stocks": round(float(part["n"].mean())), "avg_turnover": round(float(part["turnover"].mean()), 2),
        }
    years = df.assign(y=pd.to_datetime(df.month).dt.year).groupby("y").apply(
        lambda g: pd.Series({"top": np.prod(1 + g.top) - 1, "bench": np.prod(1 + g.bench) - 1}), include_groups=False)
    res["yearly"] = {int(y): {"top": round(float(r.top), 3), "bench": round(float(r.bench), 3)} for y, r in years.iterrows()}
    return res


def main(panel, industry_csv, out="momentum_results.json"):
    industry = {r["Symbol"]: r["Industry"] for r in csv.DictReader(open(industry_csv))}
    p = prepare(pd.read_pickle(panel))
    raw = run(p, industry)
    res = {name: summarize(rows) for name, rows in raw.items() if rows}
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'score':10} {'half':6} {'months':>6} {'ex/mo':>7} {'ex/yr':>7} {'t':>5} {'ahead':>6} {'top-bot':>8} {'stocks':>6} {'turn':>5}")
    for name, r in res.items():
        for half in ["first_half", "second_half"]:
            s = r.get(half)
            if s:
                print(f"{name:10} {half[:5]:6} {s['months']:>6} {s['excess_per_month']*100:6.2f}% {s['excess_per_year']*100:6.1f}% "
                      f"{s['t']:5.1f} {s['months_ahead']*100:5.0f}% {s['top_minus_bottom_per_month']*100:7.2f}% {s['avg_stocks']:>6} {s['avg_turnover']:5.2f}")


if __name__ == "__main__":
    main(*sys.argv[1:])


def risk_and_picks(panel, industry_csv, bhav, out_prefix):
    """Worst stretches vs benchmark for the main scores, and today's combo picks."""
    industry = {r["Symbol"]: r["Industry"] for r in csv.DictReader(open(industry_csv))}
    names = {r["TckrSymb"]: r["FinInstrmNm"].title() for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    p = prepare(pd.read_pickle(panel))
    raw = run(p, industry)
    risk = {}
    for name in ["combo", "mom12_1", "smooth12"]:
        df = pd.DataFrame(raw[name])
        rel = (1 + df["top"]) / (1 + df["bench"])
        curve = rel.cumprod()
        dd = curve / curve.cummax() - 1
        risk[name] = {"worst_month_vs_bench": round(float((df["top"] - df["bench"]).min()), 4),
                      "worst_month": df.loc[(df["top"] - df["bench"]).idxmin(), "month"],
                      "max_drawdown_vs_bench": round(float(dd.min()), 4),
                      "worst_absolute_month": round(float(df["top"].min()), 4),
                      "monthly": df[["month", "top", "bench"]].round(4).to_dict("records")}
        print(f"{name:9} worst month vs bench {risk[name]['worst_month_vs_bench']*100:+.1f}% ({risk[name]['worst_month']}), "
              f"deepest slide vs bench {risk[name]['max_drawdown_vs_bench']*100:.1f}%, worst month overall {risk[name]['worst_absolute_month']*100:+.1f}%")
    json.dump(risk, open(out_prefix + "_risk.json", "w"), indent=1)

    # today's picks with the combo score
    lp, liq, size, n, fz, feats, ind = build(p, industry)
    t = lp.index[-1]
    uni = liq.loc[t] & (n.loc[t] >= 252)
    syms = uni[uni].index
    sc = {k: f.loc[t, syms] for k, f in feats.items()}
    sec = ind.reindex(syms)
    sc["industry6"] = sec.map(sc["mom6_1"].groupby(sec).mean()).astype(float)
    r = pd.DataFrame({k: sc[k].rank(pct=True) for k in ("mom12_1", "high52", "industry6")})
    combo = r.mean(axis=1, skipna=False)
    frz = fz.loc[t, syms] > 0
    sq = pd.qcut(size.loc[t, syms].rank(method="first"), 5, labels=False)
    rows = []
    for s in combo.dropna().index:
        g = combo.dropna()[sq.reindex(combo.dropna().index) == sq[s]]
        rows.append({"symbol": s, "company": names.get(s, s), "sector": industry.get(s, ""),
                     "score": round(float(combo[s]), 3), "picked": bool(combo[s] >= g.quantile(0.8) and not frz[s]),
                     "skipped_frenzy": bool(frz[s] and combo[s] >= g.quantile(0.8)),
                     "size_group": int(sq[s]) + 1,
                     "return_12_1_pct": round(float(np.expm1(sc["mom12_1"][s])) * 100, 1),
                     "below_52w_high_pct": round(float(-np.expm1(sc["high52"][s])) * 100, 1),
                     "sector_6_1_pct": round(float(np.expm1(sc["industry6"][s])) * 100, 1),
                     "as_of": str(t.date())})
    rows.sort(key=lambda x: -x["score"])
    json.dump(rows, open(out_prefix + "_picks.json", "w"), indent=1)
    picked = [x for x in rows if x["picked"]]
    print(f"\n{len(picked)} picks as of {t.date()} (top 20% within each size group, frenzy stocks skipped: "
          f"{sum(x['skipped_frenzy'] for x in rows)})")
    from collections import Counter
    print("By sector:", Counter(x["sector"] for x in picked).most_common(8))
    for x in picked[:15]:
        print(f"  {x['symbol']:12} {x['sector'][:24]:24} 12m {x['return_12_1_pct']:+6.1f}%  {x['below_52w_high_pct']:4.1f}% below high")
