#!/usr/bin/env python3
"""Test volume + delivery-percentage signals on NSE stocks.

For each signal day, we "buy" at the NEXT day's close (the data is only published
after the market closes) and measure the return over the following 5, 20 and 60
trading days, minus the average return of all liquid stocks over the same days
(excess return). Results are split into two periods so a pattern found in the first
can be checked in the second.

Usage: python3 backtest.py PANEL.pkl [OUT.json]
"""
import json, sys
import numpy as np
import pandas as pd

HORIZONS = [5, 20, 60]
SPLIT = pd.Timestamp("2023-07-01")       # first half: discover, second half: check
MIN_TURNOVER_LACS = 100                  # ₹1 crore average daily traded value
MIN_PRICE = 20
COST_ROUND_TRIP = 0.0030                 # ~0.3%: STT, exchange fees, stamp duty, GST


def prepare(p):
    p = p.copy()
    r = p["close"] / p["prev_close"] - 1          # PREV_CLOSE is adjusted for splits/bonuses
    r[(r.abs() > 0.5)] = np.nan                    # broken rows (relistings, errors)
    p["ret"] = r.fillna(0.0)
    g = p.groupby("symbol", sort=False)
    p["n"] = g.cumcount()
    p["logidx"] = g["ret"].transform(lambda s: np.log1p(s).cumsum())
    past = lambda col, w: g[col].transform(lambda s: s.shift(1).rolling(w, min_periods=w // 2).mean())
    p["vol_avg20"] = past("volume", 20)
    p["turn_avg20"] = past("turnover_lacs", 20)
    p["deliv_avg60"] = past("deliv_per", 60)
    p["ret_prior20"] = g["logidx"].transform(lambda s: s - s.shift(20))
    for h in HORIZONS:  # entry at next day's close, exit h days later
        p[f"fwd{h}"] = g["logidx"].transform(lambda s: s.shift(-(1 + h)) - s.shift(-1))
    p["liquid"] = (p["turn_avg20"] >= MIN_TURNOVER_LACS) & (p["close"] >= MIN_PRICE) & (p["n"] >= 60)
    # market = average of liquid stocks' forward returns on the same entry day
    for h in HORIZONS:
        mkt = p[p["liquid"]].groupby("date")[f"fwd{h}"].mean()
        p[f"ex{h}"] = np.expm1(p[f"fwd{h}"]) - np.expm1(p["date"].map(mkt))
    p["vol_x"] = p["volume"] / p["vol_avg20"]
    p["deliv_jump"] = p["deliv_per"] - p["deliv_avg60"]
    return p


SIGNALS = {
    "quiet_accumulation": ("Heavy volume, much higher delivery than usual, price barely moved",
        lambda p: (p.vol_x >= 3) & (p.deliv_jump >= 20) & p.ret.between(-0.02, 0.04)),
    "delivery_breakout": ("Heavy volume, much higher delivery than usual, price jumped 5%+",
        lambda p: (p.vol_x >= 3) & (p.deliv_jump >= 20) & (p.ret >= 0.05)),
    "delivery_selloff": ("Heavy volume, much higher delivery than usual, price fell 5%+",
        lambda p: (p.vol_x >= 3) & (p.deliv_jump >= 20) & (p.ret <= -0.05)),
    "speculative_churn": ("Heavy volume but delivery far below usual (same-day trading frenzy)",
        lambda p: (p.vol_x >= 3) & (p.deliv_jump <= -15)),
    "volume_spike_up": ("Heavy volume and price up 5%+, ignoring delivery (comparison)",
        lambda p: (p.vol_x >= 3) & (p.ret >= 0.05)),
    "steady_accumulation": ("Delivery above usual on most of the last 10 days, volume rising, price flat",
        None),  # built below, needs rolling windows
}


def steady(p):
    g = p.groupby("symbol", sort=False)
    high_days = g["deliv_jump"].transform(lambda s: (s >= 10).astype(float).rolling(10).sum())
    vol_trend = g["volume"].transform(lambda s: s.rolling(10).mean()) / p["vol_avg20"].replace(0, np.nan)
    ret10 = g["logidx"].transform(lambda s: s - s.shift(10))
    sig = (high_days >= 7) & (vol_trend >= 1.5) & ret10.abs().lt(0.05)
    # count only the first day of each run, so one episode is one event
    prev = sig.groupby(p["symbol"]).shift(1, fill_value=False)
    return sig & ~prev.astype(bool)


def summarize(ev, label):
    out = {"events": int(len(ev)), "stocks": int(ev["symbol"].nunique())}
    for h in HORIZONS:
        x = ev[f"ex{h}"].dropna()
        if len(x) < 30:
            out[f"h{h}"] = None
            continue
        # average per date first, so 50 stocks firing on one crash day count once
        by_day = x.groupby(ev.loc[x.index, "date"]).mean()
        t = by_day.mean() / (by_day.std(ddof=1) / np.sqrt(len(by_day))) if len(by_day) > 2 else np.nan
        out[f"h{h}"] = {"mean_excess": round(float(x.mean()), 4), "median_excess": round(float(x.median()), 4),
                        "hit_rate": round(float((x > 0).mean()), 3), "t_stat": round(float(t), 2),
                        "after_costs": round(float(x.mean() - COST_ROUND_TRIP), 4), "n": int(len(x))}
    return out


def main(panel_path, out_path="backtest_results.json"):
    p = prepare(pd.read_pickle(panel_path))
    p = p[p["liquid"]]
    results = {"period": [str(p.date.min().date()), str(p.date.max().date())], "split": str(SPLIT.date()),
               "universe_days": int(len(p)), "signals": {}}
    for name, (desc, rule) in SIGNALS.items():
        mask = steady(p) if rule is None else rule(p).fillna(False)
        ev = p[mask]
        results["signals"][name] = {
            "description": desc,
            "all": summarize(ev, name),
            "first_half": summarize(ev[ev.date < SPLIT], name),
            "second_half": summarize(ev[ev.date >= SPLIT], name),
        }
    with open(out_path, "w") as f:
        json.dump(results, f, indent=1)
    print(f"Universe: liquid NSE stocks {results['period'][0]}..{results['period'][1]}, split at {SPLIT.date()}")
    print(f"{'signal':22} {'half':6} {'events':>7}  " + "  ".join(f"{'ex'+str(h)+'d':>8} {'hit':>5} {'t':>5}" for h in HORIZONS))
    for name, r in results["signals"].items():
        for half in ["first_half", "second_half"]:
            s = r[half]
            cells = []
            for h in HORIZONS:
                v = s.get(f"h{h}")
                cells.append(f"{v['mean_excess']*100:7.2f}% {v['hit_rate']*100:4.0f}% {v['t_stat']:5.1f}" if v else f"{'—':>8} {'':>5} {'':>5}")
            print(f"{name:22} {half[:5]:6} {s['events']:>7}  " + "  ".join(cells))


if __name__ == "__main__":
    main(*sys.argv[1:3])
