#!/usr/bin/env python3
"""One forward-looking score per stock that weighs every signal together.

Every month-end, for every liquid NSE stock, ~25 signals are computed from data
available that day (trend, sector, money flow, frenzy, IPO, Wikipedia attention,
market mood). A gradient-boosted tree model learns how they combine to predict
the NEXT month's return relative to other stocks.

Walk-forward, no peeking: the model predicting month t is trained only on months
whose outcomes were fully known by t (labels ending at least one month earlier),
retrained every 3 months. The out-of-sample predictions are then turned into a
portfolio: top 20% within each size group, bought at the next day's close, held
one month, costs charged on turnover.

Usage: python3 combined.py PANEL.pkl INDUSTRY.csv IPOS.csv VIEWS.pkl OUTDIR
"""
import csv, json, os, sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from backtest import prepare, COST_ROUND_TRIP

MIN_TRAIN_MONTHS = 24
RETRAIN_EVERY = 3
TOP = 0.2

RANKED = ["mom12_1", "mom6_1", "mom3", "mom1", "high52", "smooth12", "vol252", "vol21", "maxret21",
          "turnover", "deliv20", "deliv_trend", "volume_trend", "frenzy21", "frenzy63", "acc10",
          "sector_mom6", "rel_sector", "peer_mom6", "rel_peer", "age", "listing_gain", "wiki_attn30", "wiki_spikes21", "wiki_level"]
RAW = ["mkt1", "mkt3", "breadth", "has_wiki", "recent_ipo"]
PLAIN = {"mom12_1": "12-month trend", "mom6_1": "6-month trend", "mom3": "3-month move", "mom1": "last month's move",
         "high52": "distance from 52-week high", "smooth12": "steadiness of the climb", "vol252": "yearly volatility",
         "vol21": "recent volatility", "maxret21": "biggest one-day jump last month", "turnover": "trading volume (size)",
         "deliv20": "delivery %", "deliv_trend": "delivery % trend", "volume_trend": "volume trend",
         "frenzy21": "frenzy days last month", "frenzy63": "frenzy days last 3 months", "acc10": "quiet accumulation days",
         "sector_mom6": "sector trend", "rel_sector": "strength vs sector", "peer_mom6": "peer group trend",
         "rel_peer": "strength vs peers", "age": "how long listed", "listing_gain": "IPO listing-day gain",
         "wiki_attn30": "Wikipedia attention trend", "wiki_spikes21": "Wikipedia spikes", "wiki_level": "Wikipedia readership"}


def matrices(p, views):
    m = {}
    piv = lambda col, agg="mean": p.pivot_table(index="date", columns="symbol", values=col, aggfunc=agg)
    m["lp"] = piv("logidx").ffill()
    m["liq"] = piv("liquid", "first").fillna(False).astype(bool)
    m["n"] = piv("n")
    m["turn"] = piv("turn_avg20")
    m["vol"] = piv("volume")
    m["deliv"] = piv("deliv_per")
    m["ret"] = m["lp"].diff()
    frz = ((p["vol_x"] >= 3) & (p["deliv_jump"] <= -15)).astype(float)
    acc = (p["deliv_jump"] >= 5).astype(float)
    m["frenzy"] = p.assign(f=frz).pivot_table(index="date", columns="symbol", values="f").fillna(0)
    m["acc"] = p.assign(a=acc).pivot_table(index="date", columns="symbol", values="a").fillna(0)
    v = (views.pivot_table(index="date", columns="symbol", values="views")
         .reindex(index=m["lp"].index, columns=m["lp"].columns).ffill(limit=3))  # blank for stocks with no page
    m["views"] = v
    return m


def features(m, ind, ipo_gain):
    lp, ret = m["lp"], m["ret"]
    f = {}
    f["mom12_1"] = lp.shift(21) - lp.shift(252)
    f["mom6_1"] = lp.shift(21) - lp.shift(126)
    f["mom3"] = lp - lp.shift(63)
    f["mom1"] = lp - lp.shift(21)
    f["high52"] = lp - lp.rolling(252, min_periods=200).max()
    f["vol252"] = ret.rolling(252, min_periods=200).std()
    f["vol21"] = ret.rolling(21, min_periods=15).std()
    f["smooth12"] = f["mom12_1"] / (f["vol252"] * np.sqrt(231))
    f["maxret21"] = ret.rolling(21, min_periods=15).max()
    f["turnover"] = np.log(m["turn"].clip(lower=1))
    f["deliv20"] = m["deliv"].rolling(20, min_periods=10).mean()
    f["deliv_trend"] = f["deliv20"] - m["deliv"].rolling(120, min_periods=60).mean()
    f["volume_trend"] = np.log(m["vol"].rolling(20, min_periods=10).mean() / m["vol"].rolling(120, min_periods=60).mean())
    f["frenzy21"] = m["frenzy"].rolling(21, min_periods=1).sum()
    f["frenzy63"] = m["frenzy"].rolling(63, min_periods=1).sum()
    f["acc10"] = m["acc"].rolling(10, min_periods=5).sum()
    f["age"] = m["n"].clip(upper=1000)
    v = m["views"]
    med180 = v.shift(1).rolling(180, min_periods=60).median().clip(lower=5)
    f["wiki_attn30"] = np.log(v.rolling(30, min_periods=15).mean() / med180)
    f["wiki_spikes21"] = ((v / med180 >= 3) & (v >= 200)).astype(float).rolling(21, min_periods=1).sum().where(v.notna())
    f["wiki_level"] = np.log(med180)
    return f


def month_table(m, f, ind, ipo_gain):
    lp = m["lp"]
    dates = lp.index
    ends = pd.Series(dates, index=dates).groupby(dates.to_period("M")).max().values
    ends = [pd.Timestamp(d) for d in ends if dates.get_loc(d) >= 260]
    ma200 = lp.rolling(200, min_periods=150).mean()
    rows = []
    for i, t in enumerate(ends):
        k = dates.get_loc(t)
        uni = m["liq"].loc[t] & (m["n"].loc[t] >= 252)
        syms = uni[uni].index
        df = pd.DataFrame({name: f[name].loc[t, syms] for name in f}, index=syms)
        sec = pd.Series(ind).reindex(syms)
        df["sector_mom6"] = sec.map(df["mom6_1"].groupby(sec).mean()).astype(float)
        df["rel_sector"] = df["mom6_1"] - df["sector_mom6"]
        # point-in-time peers: the 20 stocks whose daily returns moved most like this one over
        # the past year (no dependence on today's index lists, so no survivor bias)
        R = m["ret"].iloc[k - 251:k + 1][syms].fillna(0.0).to_numpy()
        R = (R - R.mean(0)) / (R.std(0) + 1e-12)
        C = (R.T @ R) / len(R)
        np.fill_diagonal(C, -np.inf)
        peers = np.argpartition(-C, 20, axis=1)[:, :20]
        mom6 = df["mom6_1"].to_numpy()
        df["peer_mom6"] = np.nanmean(mom6[peers], axis=1)
        df["rel_peer"] = df["mom6_1"] - df["peer_mom6"]
        df["listing_gain"] = pd.Series(ipo_gain).reindex(syms)
        df["recent_ipo"] = (df["listing_gain"].notna() & (df["age"] < 500)).astype(float)
        df["has_wiki"] = df["wiki_level"].notna().astype(float)
        df["mkt1"] = df["mom1"].mean()
        df["mkt3"] = df["mom3"].mean()
        df["breadth"] = float((lp.loc[t, syms] > ma200.loc[t, syms]).mean())
        df["size_q"] = pd.qcut(m["turn"].loc[t, syms].rank(method="first"), 5, labels=False)
        # outcome: next day's close to the day after the next month-end (NaN for the last month)
        if i + 1 < len(ends) and dates.get_loc(ends[i + 1]) + 1 < len(dates):
            a, b = k + 1, dates.get_loc(ends[i + 1]) + 1
            fwd = np.expm1(lp.iloc[b][syms] - lp.iloc[a][syms])
            df["fwd"] = fwd
            df["fwd_ex"] = fwd - fwd.mean()
        else:
            df["fwd"] = np.nan
            df["fwd_ex"] = np.nan
        df["month"] = t
        rows.append(df.reset_index().rename(columns={"index": "symbol"}))
    tab = pd.concat(rows, ignore_index=True)
    for c in RANKED:  # cross-sectional ranks keep the model stable across regimes
        tab[c + "_r"] = tab.groupby("month")[c].rank(pct=True)
    tab["label"] = tab.groupby("month")["fwd"].rank(pct=True)
    return tab


def walk_forward(tab):
    cols = [c + "_r" for c in RANKED] + RAW
    months = sorted(tab["month"].unique())
    preds, model, importances = [], None, []
    params = dict(objective="regression", learning_rate=0.03, num_leaves=15, min_data_in_leaf=200,
                  feature_fraction=0.7, bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
    for i, t in enumerate(months):
        if i < MIN_TRAIN_MONTHS + 1:
            continue
        if model is None or (i - MIN_TRAIN_MONTHS - 1) % RETRAIN_EVERY == 0:
            train = tab[tab["month"] <= months[i - 2]].dropna(subset=["label"])  # labels fully known by t
            model = lgb.train(params, lgb.Dataset(train[cols], train["label"]), num_boost_round=300)
            importances.append(pd.Series(model.feature_importance("gain"), index=cols))
        cur = tab[tab["month"] == t].copy()
        cur["score"] = model.predict(cur[cols])
        preds.append(cur)
    imp = pd.concat(importances, axis=1).mean(axis=1).sort_values(ascending=False)
    return pd.concat(preds, ignore_index=True), (imp / imp.sum()).round(4), model, cols


def portfolio(pred, score="score"):
    out, prev = [], set()
    for t, g in pred.dropna(subset=["fwd"]).groupby("month"):
        picks = []
        for q, gq in g.groupby("size_q"):
            picks += list(gq[gq[score] >= gq[score].quantile(1 - TOP)]["symbol"])
        hold = set(picks)
        turnover = 1 - len(hold & prev) / max(len(hold), 1)
        prev = hold
        top = g[g["symbol"].isin(hold)]["fwd"].mean() - turnover * COST_ROUND_TRIP
        bottom_cut = g.groupby("size_q")[score].transform(lambda s: s.quantile(TOP))
        out.append({"month": str(t.date()), "top": top, "bench": g["fwd"].mean(),
                    "bottom": g[g[score] <= bottom_cut]["fwd"].mean(), "n": len(hold), "turnover": turnover,
                    "ic": g[score].corr(g["fwd"], method="spearman")})
    return pd.DataFrame(out)


def stats(df):
    ex = df["top"] - df["bench"]
    curve = ((1 + df["top"]) / (1 + df["bench"])).cumprod()
    return {"months": int(len(df)), "first": df["month"].iloc[0], "last": df["month"].iloc[-1],
            "excess_per_month": round(float(ex.mean()), 4), "excess_per_year": round(float((1 + ex.mean()) ** 12 - 1), 4),
            "t": round(float(ex.mean() / ex.std() * np.sqrt(len(ex))), 2), "months_ahead": round(float((ex > 0).mean()), 3),
            "top_minus_bottom": round(float((df["top"] - df["bottom"]).mean()), 4),
            "avg_ic": round(float(df["ic"].mean()), 4), "ic_positive_months": round(float((df["ic"] > 0).mean()), 3),
            "worst_month_vs_bench": round(float(ex.min()), 4), "max_slide_vs_bench": round(float((curve / curve.cummax() - 1).min()), 4),
            "total_top": round(float(np.prod(1 + df["top"]) - 1), 3), "total_bench": round(float(np.prod(1 + df["bench"]) - 1), 3),
            "avg_stocks": int(df["n"].mean()), "avg_turnover": round(float(df["turnover"].mean()), 2)}


def main(panel, industry_csv, ipos_csv, views_pkl, outdir):
    os.makedirs(outdir, exist_ok=True)
    ind = {r["Symbol"]: r["Industry"] for r in csv.DictReader(open(industry_csv))}
    if not os.environ.get("USE_SECTOR_LIST"):
        # Off by default: NSE's sector list only covers today's index members, so using it
        # leaks survivorship ("stocks still listed today did well"). Peers stand in for it.
        ind = {}
    ipo_gain = {r["symbol"]: float(r["listing_gain"]) for r in csv.DictReader(open(ipos_csv))}
    raw = pd.read_pickle(panel)
    funds_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "funds_exclude.txt")
    funds = {l.strip() for l in open(funds_file) if l.strip() and not l.startswith("#")}
    p = prepare(raw[~raw["symbol"].isin(funds)])  # companies only: ETFs are not stocks
    m = matrices(p, pd.read_pickle(views_pkl))
    f = features(m, ind, ipo_gain)
    tab = month_table(m, f, ind, ipo_gain)
    tab.to_pickle(os.path.join(outdir, "monthly_table.pkl"))
    pred, imp, model, cols = walk_forward(tab)
    pred.to_pickle(os.path.join(outdir, "predictions.pkl"))

    # comparison: the earlier hand-made trend score on the same months
    pred["handmade"] = pred[["mom12_1_r", "high52_r", "sector_mom6_r"]].mean(axis=1, skipna=False)
    pred.loc[pred["frenzy21"] > 0, "handmade"] = np.nan
    res = {"model": stats(portfolio(pred)), "feature_importance": imp.to_dict()}
    if pred["handmade"].notna().any():
        res["handmade_trend_score"] = stats(portfolio(pred.dropna(subset=["handmade"]), "handmade"))
    port = portfolio(pred)
    res["monthly"] = port.round(4).to_dict("records")

    # today's forward-looking scores (latest month-end, outcome not yet known)
    last = tab["month"].max()
    train = tab[tab["month"] <= sorted(tab["month"].unique())[-3]].dropna(subset=["label"])
    params = dict(objective="regression", learning_rate=0.03, num_leaves=15, min_data_in_leaf=200, feature_fraction=0.7,
                  bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0, verbose=-1, seed=7)
    final = lgb.train(params, lgb.Dataset(train[cols], train["label"]), num_boost_round=300)
    now = tab[tab["month"] == last].copy()
    now["score"] = final.predict(now[cols])
    now["score_pct"] = now.groupby("size_q")["score"].rank(pct=True)
    now.to_pickle(os.path.join(outdir, "current_scores.pkl"))
    # why: per-stock contribution of each signal to its score (tree SHAP values)
    contrib = pd.DataFrame(final.predict(now[cols], pred_contrib=True)[:, :-1], columns=cols, index=now.index)
    stock_cols = [c for c in cols if c.endswith("_r")]
    def reasons(i, sign):
        c = contrib.loc[i, stock_cols].sort_values(ascending=(sign < 0))
        c = c[c * sign > 0].head(3)
        row = now.loc[i]
        return "; ".join(f"{'high' if row[k] >= 0.5 else 'low'} {PLAIN.get(k[:-2], k)}" if pd.notna(row[k])
                         else f"no {PLAIN.get(k[:-2], k)}" for k in c.index)
    names = {}
    bhav = os.environ.get("BHAVCOPY")
    if bhav:
        names = {r["TckrSymb"]: r["FinInstrmNm"].title() for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    picks = []
    for i, r in now.sort_values("score", ascending=False).iterrows():
        picks.append({"symbol": r["symbol"], "company": names.get(r["symbol"], r["symbol"]),
                      "score_pct_in_size_group": round(float(r["score_pct"]) * 100, 1),
                      "size_group": int(r["size_q"]) + 1,
                      "signal": "buy list" if r["score_pct"] >= 1 - TOP else ("avoid list" if r["score_pct"] <= TOP else "neutral"),
                      "helps": reasons(i, 1), "hurts": reasons(i, -1),
                      "return_12m_pct": round(float(np.expm1(r["mom12_1"] if pd.notna(r["mom12_1"]) else np.nan)) * 100, 1),
                      "below_52w_high_pct": round(float(-np.expm1(r["high52"])) * 100, 1) if pd.notna(r["high52"]) else None,
                      "frenzy_days_last_month": int(r["frenzy21"]), "as_of": str(pd.Timestamp(last).date())})
    json.dump(picks, open(os.path.join(outdir, "current_picks.json"), "w"), indent=1)
    res["market_mood_now"] = {"market_1m": round(float(np.expm1(now["mkt1"].iloc[0])), 4),
                              "market_3m": round(float(np.expm1(now["mkt3"].iloc[0])), 4),
                              "share_above_200d_avg": round(float(now["breadth"].iloc[0]), 3)}
    res["as_of"] = str(pd.Timestamp(last).date())
    json.dump(res, open(os.path.join(outdir, "combined_results.json"), "w"), indent=1, default=str)

    for name in [k for k in ["model", "handmade_trend_score"] if k in res]:
        s = res[name]
        print(f"{name:22} {s['first']}..{s['last']} ({s['months']} months, all out-of-sample)")
        print(f"   ahead of market {s['excess_per_month']*100:+.2f}%/month ({s['excess_per_year']*100:+.1f}%/yr), t={s['t']}, "
              f"ahead in {s['months_ahead']*100:.0f}% of months; top-bottom {s['top_minus_bottom']*100:+.2f}%/month; "
              f"rank corr {s['avg_ic']:+.3f} (positive {s['ic_positive_months']*100:.0f}% of months)")
        print(f"   worst month {s['worst_month_vs_bench']*100:+.1f}%, deepest slide {s['max_slide_vs_bench']*100:.1f}%, "
              f"total {s['total_top']*100:+.0f}% vs market {s['total_bench']*100:+.0f}%, ~{s['avg_stocks']} stocks, turnover {s['avg_turnover']}")
    print("Most influential signals:", ", ".join(f"{k.replace('_r','')} {v*100:.0f}%" for k, v in imp.head(10).items()))
    print(f"Current scores as of {res['as_of']}: {len(now)} stocks")


if __name__ == "__main__":
    main(*sys.argv[1:])
