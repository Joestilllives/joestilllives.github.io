#!/usr/bin/env python3
"""Audit of the money signal (blend of ensemble model + steady climb, size groups 1-4,
frenzy and split/bonus red flags, top 20% per group).

  1 size effect      random picks from the same groups and filters: how much "edge" is free?
  2 placebo          scores shuffled within each month: the pipeline should give ~0
  3 vanishing stocks picks that stop trading in EQ during the holding month (frozen prices)
  4 25% rule         genuine daily moves beyond 25% dropped during holding months
  5 costs            0.3% vs 0.6% vs 1.0% per round trip
  6 investable       basket vs Nifty 50, Midcap 150 and Smallcap 250 ETFs, same months
  7 one-month delay  last month's scores: a real signal should fade, not vanish

Usage: python3 audit.py ENSEMBLE_PREDS.pkl PANEL.pkl CORP_ACTIONS.csv FUNDS.txt
"""
import sys
import numpy as np
import pandas as pd

GROUPS, TOP = [0, 1, 2, 3], 0.2
RATIOS = [1 / 2, 2 / 3, 3 / 4, 1 / 3, 1 / 5, 1 / 10]


def eligible(p, ca):
    months = sorted(p["month"].unique())
    flag = set()
    for m in months:
        for s in ca[(ca["date"] > m - pd.Timedelta(days=182)) & (ca["date"] <= m)]["symbol"]:
            flag.add((m, s))
    p = p.copy()
    p["ok"] = p["size_q"].isin(GROUPS) & (p["frenzy21"] < 3) & ~pd.Series([(m, s) in flag for m, s in zip(p["month"], p["symbol"])], index=p.index)
    return p


def basket(p, score, cost=0.003, seed=None):
    rows, prev = [], set()
    rng = np.random.default_rng(seed)
    for m, g in p.groupby("month"):
        mkt = g["fwd"].mean()
        e = g[g["ok"]].dropna(subset=["blend"])
        if e["fwd"].isna().all():
            continue
        if score == "random":
            pick = e.groupby("size_q", group_keys=False).apply(lambda x: x.sample(frac=TOP, random_state=int(rng.integers(1e9))))
        else:
            r = e.groupby("size_q")[score].rank(pct=True)
            pick = e[r >= 1 - TOP]
        hold = set(pick["symbol"]); to = 1 - len(hold & prev) / max(len(hold), 1); prev = hold
        rows.append({"month": m, "r": pick["fwd"].mean() - to * cost, "mkt": mkt, "symbols": list(hold)})
    return pd.DataFrame(rows)


def stats(d):
    ex = d["r"] - d["mkt"]
    return (1 + ex.mean()) ** 12 - 1, ex.mean() / ex.std() * np.sqrt(len(ex)), (ex > 0).mean()


def main(preds, panel, ca_csv, funds_txt):
    p = pd.read_pickle(preds)
    ca = pd.read_csv(ca_csv, parse_dates=["date"])
    p = eligible(p, ca)
    base = basket(p, "blend")
    e, t, a = stats(base)
    print(f"Money signal as tested: {e*100:+.1f}%/yr vs average company, t={t:.2f}, ahead {a*100:.0f}% of months, {len(base)} months\n")

    print("1. Size effect: random picks from the same groups and filters (20 draws)")
    rand = [stats(basket(p, "random", seed=i)) for i in range(20)]
    re_ = np.array([x[0] for x in rand])
    print(f"   random baskets: {re_.mean()*100:+.1f}%/yr on average (range {re_.min()*100:+.1f} to {re_.max()*100:+.1f})"
          f" -> skill beyond the universe choice ~ {(e - re_.mean())*100:+.1f}%/yr\n")

    print("2. Placebo: scores shuffled within each month (20 draws)")
    pl = []
    for i in range(20):
        q = p.copy(); q["blend"] = q.groupby("month")["blend"].transform(lambda s: s.sample(frac=1, random_state=i).to_numpy())
        pl.append(stats(basket(q, "blend"))[0])
    print(f"   shuffled: {np.mean(pl)*100:+.1f}%/yr on average (should match the random baskets above)\n")

    raw = pd.read_pickle(panel)
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = raw[~raw["symbol"].isin(funds)]
    last_trade = raw.groupby("symbol")["date"].max()
    dates = pd.DatetimeIndex(np.sort(raw["date"].unique()))
    months = list(base["month"])
    print("3. Vanishing stocks: picks whose EQ trading stops before the month's exit")
    n_all = n_stop = 0; stopped_fwd = []
    pm = p.set_index(["month", "symbol"])
    for i, m in enumerate(months[:-1]):
        exit_d = dates[min(dates.searchsorted(months[i + 1]) + 1, len(dates) - 1)]
        for s in base.loc[i, "symbols"]:
            n_all += 1
            if last_trade.get(s, exit_d) < exit_d - pd.Timedelta(days=5):
                n_stop += 1; stopped_fwd.append(pm.loc[(m, s), "fwd"])
    print(f"   {n_stop} of {n_all} picks ({n_stop/n_all*100:.2f}%) stopped trading in EQ during the month; their recorded mean return "
          f"{np.nanmean(stopped_fwd)*100:+.1f}%. If each had truly gone to -50% instead: impact ~ "
          f"{n_stop/n_all*(-0.5 - np.nanmean(stopped_fwd))*12*100:+.2f}%/yr (worst case)\n")

    print("4. 25% rule: genuine big daily moves (not a split/bonus ratio) dropped while a pick was held")
    raw = raw.sort_values(["symbol", "date"])
    rr = raw["close"] / raw["prev_close"]
    big = raw[((rr - 1).abs() > 0.25) & ~np.any([abs(rr - v) < 0.03 * v for v in RATIOS], axis=0)].assign(r=rr - 1)
    held = {(months[i], s) for i in range(len(months)) for s in base.loc[i, "symbols"]}
    hits = []
    for b in big.itertuples():
        k = dates.searchsorted(b.date)
        m = max([x for x in months if x < b.date], default=None)
        if m is not None and (m, b.symbol) in held:
            hits.append(b.r)
    if hits:
        imp = np.sum(hits) / max(len(held), 1) * 12
        print(f"   {len(hits)} such days among {len(held)} holdings; their moves sum to {np.sum(hits)*100:+.0f}% -> impact if real ~ {imp*100:+.2f}%/yr\n")
    else:
        print("   none\n")

    print("5. Costs")
    for c in [0.003, 0.006, 0.010]:
        e2, t2, a2 = stats(basket(p, "blend", cost=c))
        print(f"   {c*100:.1f}% per round trip: {e2*100:+.1f}%/yr, t={t2:.2f}, ahead {a2*100:.0f}%")

    print("\n6. Against index funds you can buy (same holding months, basket after costs)")
    etf = {"NIFTYBEES": "Nifty 50", "MID150BEES": "Midcap 150", "HDFCSML250": "Smallcap 250"}
    rawall = pd.read_pickle(panel)
    for sym, name in etf.items():
        e_ = rawall[rawall["symbol"] == sym].set_index("date")
        rr = (e_["close"] / e_["prev_close"] - 1).where(lambda x: x.abs() <= 0.25).fillna(0)  # unit splits are not returns
        q = np.exp(np.log1p(rr).cumsum()).reindex(dates).ffill()
        rows = []
        for i, m in enumerate(months[:-1]):
            a0 = dates[min(dates.searchsorted(m) + 1, len(dates) - 1)]
            b0 = dates[min(dates.searchsorted(months[i + 1]) + 1, len(dates) - 1)]
            if np.isnan(q[a0]) or np.isnan(q[b0]):
                continue
            rows.append((base.loc[i, "r"], q[b0] / q[a0] - 1))
        if len(rows) > 12:
            x = np.array(rows)
            yrs = len(x) / 12
            print(f"   vs {name:12} ({len(x)} months): basket {np.prod(1+x[:,0])**(1/yrs)*100-100:+.1f}%/yr, "
                  f"fund {np.prod(1+x[:,1])**(1/yrs)*100-100:+.1f}%/yr, basket ahead in {(x[:,0]>x[:,1]).mean()*100:.0f}% of months")

    print("\n7. One-month delay: using last month's scores")
    q = p.sort_values(["symbol", "month"]).copy()
    q["blend"] = q.groupby("symbol")["blend"].shift(1)
    e3, t3, a3 = stats(basket(q, "blend"))
    print(f"   {e3*100:+.1f}%/yr, t={t3:.2f} (vs {e*100:+.1f}% on time)")


if __name__ == "__main__":
    main(*sys.argv[1:])
