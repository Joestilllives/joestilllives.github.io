#!/usr/bin/env python3
"""Simulate holding every steady-accumulation stock for a fixed period.

Each signal buys the stock at the next day's close and holds it HOLD trading days,
equal weight across everything held that day. The benchmark holds, for each
position, the average stock of the same size group (traded-value quintile), so
the comparison is like-for-like. Trading costs are charged on every entry and exit.

Usage: python3 portfolio.py PANEL.pkl [OUT.json] [HOLD]
"""
import json, sys
import numpy as np
import pandas as pd
from backtest import prepare, COST_ROUND_TRIP
from refine import features, rule

BEST = {"deliv_pts": 5, "min_days": 8, "vol_trend": 1.2, "max_move": 0.05}


SIGNALS = {
    "accumulation": lambda liq: rule(liq, features(liq), BEST),
    # heavy volume but delivery far below usual; one event per run of days
    "frenzy": lambda liq: (lambda s: s & ~s.groupby(liq["symbol"]).shift(1, fill_value=False).astype(bool))(
        ((liq["vol_x"] >= 3) & (liq["deliv_jump"] <= -15)).fillna(False)),
}


def main(panel, out="portfolio_results.json", hold=60, signal="accumulation"):
    hold = int(hold)
    p = prepare(pd.read_pickle(panel))
    dates = np.sort(p["date"].unique())
    di = {d: i for i, d in enumerate(dates)}
    liq = p[p["liquid"]].copy()
    sig = SIGNALS[signal](liq)
    ev = liq.loc[sig, ["symbol", "date", "size_q"]]

    # daily returns for every stock, and the daily mean return of each size group
    ret = p.pivot_table(index="date", columns="symbol", values="ret")
    qmean = liq.groupby(["date", "size_q"])["ret"].mean().unstack().reindex(dates)

    port, bench, count = np.zeros(len(dates)), np.zeros(len(dates)), np.zeros(len(dates))
    for sym, d, q in ev.itertuples(index=False):
        start = di[d] + 2                      # bought at next day's close, earns from the day after
        end = min(start + hold, len(dates))
        if start >= len(dates):
            continue
        r = ret[sym].values[start:end]
        b = qmean[q].values[start:end]
        r = np.nan_to_num(r); b = np.nan_to_num(b)
        r[0] -= COST_ROUND_TRIP / 2; r[-1] -= COST_ROUND_TRIP / 2 if end - start > 1 else 0
        port[start:end] += r; bench[start:end] += b; count[start:end] += 1
    active = count > 0
    pr = np.where(active, port / np.maximum(count, 1), 0.0)
    br = np.where(active, bench / np.maximum(count, 1), 0.0)
    df = pd.DataFrame({"date": pd.to_datetime(dates), "portfolio": pr, "benchmark": br, "positions": count})
    df["year"] = df["date"].dt.year
    yearly = df.groupby("year").apply(lambda g: pd.Series({
        "portfolio": float(np.prod(1 + g.portfolio) - 1), "benchmark": float(np.prod(1 + g.benchmark) - 1),
        "avg_positions": float(g.positions[g.positions > 0].mean() if (g.positions > 0).any() else 0)}),
        include_groups=False)
    yearly["excess"] = yearly["portfolio"] - yearly["benchmark"]
    df["curve_port"] = np.cumprod(1 + df["portfolio"]); df["curve_bench"] = np.cumprod(1 + df["benchmark"])
    ex = df.loc[active, "portfolio"] - df.loc[active, "benchmark"]
    # monthly excess returns are close to independent, so judge significance on them
    m = (1 + df.set_index("date")[["portfolio", "benchmark"]]).resample("ME").prod() - 1
    mex = (m["portfolio"] - m["benchmark"])[m["portfolio"] != 0]
    res = {"hold_days": hold, "signal": signal, "rule": BEST if signal == "accumulation" else "vol_x>=3 & deliv_jump<=-15", "events": int(len(ev)),
           "monthly_excess_mean": float(mex.mean()), "monthly_excess_t": float(mex.mean() / mex.std() * np.sqrt(len(mex))),
           "months_beating_benchmark": float((mex > 0).mean()),
           "total_portfolio": float(df["curve_port"].iloc[-1] - 1), "total_benchmark": float(df["curve_bench"].iloc[-1] - 1),
           "yearly": yearly.round(4).reset_index().to_dict("records"),
           "curve": df.loc[df.index % 5 == 0, ["date", "curve_port", "curve_bench", "positions"]]
                      .assign(date=lambda x: x.date.dt.strftime("%Y-%m-%d")).round(4).to_dict("records")}
    json.dump(res, open(out, "w"), indent=1)
    print(f"[{signal}] {len(ev)} signals, held {hold} days, ~{df.positions[active].mean():.0f} stocks held on average")
    print(f"Whole period: portfolio {res['total_portfolio']*100:+.0f}%, similar-size benchmark {res['total_benchmark']*100:+.0f}%")
    print(f"Monthly excess: mean {res['monthly_excess_mean']*100:+.2f}%, t = {res['monthly_excess_t']:.1f}, "
          f"beat benchmark in {res['months_beating_benchmark']*100:.0f}% of months")
    print(yearly.assign(**{c: (yearly[c] * 100).round(1) for c in ["portfolio", "benchmark", "excess"]})
          .assign(avg_positions=yearly.avg_positions.round(0)).to_string())


if __name__ == "__main__":
    main(*sys.argv[1:])
