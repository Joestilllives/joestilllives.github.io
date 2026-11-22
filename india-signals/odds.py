#!/usr/bin/env python3
"""Can the odds be raised? Walk-forward variants of the model, judged on:
  pick odds  = share of picked stocks that beat the average company next month
  month odds = share of months the basket beats the average company
  edge       = excess return per year after 0.3% costs

Variants: target (regression on return rank | classification 'beats market' |
learning-to-rank), an ensemble of 5 seeds, a 3-month target, and high-conviction
filters (blend with the steady-climb rank, agreement above a cutoff).

Usage: python3 odds.py MONTHLY_TABLE.pkl
"""
import sys
import numpy as np
import pandas as pd
import lightgbm as lgb
from combined import RANKED, RAW

COST, GROUPS, MIN_TRAIN, EVERY = 0.003, [0, 1, 2, 3], 24, 3
BASE = dict(learning_rate=0.03, num_leaves=15, min_data_in_leaf=200, feature_fraction=0.7,
            bagging_fraction=0.7, bagging_freq=1, lambda_l2=5.0, verbose=-1)


def add_targets(tab):
    tab = tab.sort_values(["symbol", "month"]).copy()
    tab["beat"] = (tab["fwd"] > tab.groupby("month")["fwd"].transform("mean")).astype(float).where(tab["fwd"].notna())
    # 3-month forward: compound this and the next two monthly returns of the same stock
    g = tab.groupby("symbol")["fwd"]
    f3 = (1 + tab["fwd"]) * (1 + g.shift(-1)) * (1 + g.shift(-2)) - 1
    tab["label3"] = f3.groupby(tab["month"]).rank(pct=True)
    tab["rel"] = np.floor((tab.groupby("month")["fwd"].rank(pct=True) * 4).clip(0, 3.999))  # 0-3 relevance, NaN stays NaN
    return tab


def walk(tab, kind="reg", seeds=(7,), horizon=1, extra=()):
    cols = [c + "_r" for c in RANKED if c + "_r" in tab] + [c for c in RAW if c in tab] + list(extra)
    months = sorted(tab["month"].unique())
    out, models = [], None
    lab = {"reg": "label", "clf": "beat", "rank": "rel"}[kind] if horizon == 1 else "label3"
    gap = 1 + horizon  # labels must be fully known when predicting
    for i, t in enumerate(months):
        if i < MIN_TRAIN + gap:
            continue
        if models is None or (i - MIN_TRAIN - gap) % EVERY == 0:
            tr = tab[tab["month"] <= months[i - gap]].dropna(subset=[lab]).sort_values("month")
            models = []
            for sd in seeds:
                p = dict(BASE, seed=sd)
                if kind == "clf" and horizon == 1:
                    p["objective"] = "binary"
                    ds = lgb.Dataset(tr[cols], tr[lab])
                elif kind == "rank" and horizon == 1:
                    p["objective"] = "lambdarank"; p["min_data_in_leaf"] = 50
                    ds = lgb.Dataset(tr[cols], tr[lab], group=tr.groupby("month").size().to_numpy())
                else:
                    p["objective"] = "regression"
                    ds = lgb.Dataset(tr[cols], tr[lab])
                models.append(lgb.train(p, ds, num_boost_round=300))
        cur = tab[tab["month"] == t].copy()
        cur["ml"] = np.mean([m.predict(cur[cols]) for m in models], axis=0)
        out.append(cur)
    return pd.concat(out, ignore_index=True)


def evaluate(pred, score, top=0.2, min_score=None):
    rows, prev = [], set()
    for m, g in pred.groupby("month"):
        g = g[g["size_q"].isin(GROUPS) & (g["frenzy21"] < 3)].dropna(subset=[score])
        if g["fwd"].isna().all():
            continue
        r = g.groupby("size_q")[score].rank(pct=True)
        pick = g[(r >= 1 - top) & ((g[score] >= min_score) if min_score is not None else True)]
        if pick.empty:
            continue
        mkt = pred.loc[pred["month"] == m, "fwd"].mean()
        hold = set(pick["symbol"]); to = 1 - len(hold & prev) / max(len(hold), 1); prev = hold
        rows.append({"month": m, "r": pick["fwd"].mean() - to * COST, "mkt": mkt,
                     "pick_odds": (pick["fwd"] > mkt).mean(), "n": len(pick)})
    d = pd.DataFrame(rows)
    ex = d["r"] - d["mkt"]
    half = d["month"] < pd.Timestamp("2022-12-31")
    return {"edge": (1 + ex.mean()) ** 12 - 1, "t": ex.mean() / ex.std() * np.sqrt(len(ex)),
            "month_odds": (ex > 0).mean(), "pick_odds": d["pick_odds"].mean(), "n": d["n"].mean(),
            "edge1": (1 + ex[half].mean()) ** 12 - 1, "edge2": (1 + ex[~half].mean()) ** 12 - 1, "months": len(d)}


def show(label, s):
    print(f"{label:46} edge {s['edge']*100:+5.1f}%/yr t={s['t']:.2f} | month odds {s['month_odds']*100:3.0f}% | "
          f"pick odds {s['pick_odds']*100:4.1f}% | 2019-22 {s['edge1']*100:+5.1f}% 2023-26 {s['edge2']*100:+5.1f}% | ~{s['n']:.0f} stocks, {s['months']} mo")


def main(table_pkl):
    tab = add_targets(pd.read_pickle(table_pkl))
    tab["steady_r2"] = tab.groupby("month")["smooth12"].rank(pct=True)
    runs = {"A regression (current)": dict(kind="reg"), "A classification: beats market?": dict(kind="clf"),
            "A learning-to-rank": dict(kind="rank"), "B ensemble of 5 (regression)": dict(kind="reg", seeds=(1, 2, 3, 4, 5)),
            "C 3-month target": dict(kind="reg", horizon=3)}
    preds = {}
    for name, kw in runs.items():
        p = walk(tab, **kw)
        p["ml_r"] = p.groupby("month")["ml"].rank(pct=True)
        p["blend"] = (p["ml_r"] + p["steady_r2"]) / 2
        preds[name] = p
        show(name, evaluate(p, "ml"))
        show("   + blend with steady climb", evaluate(p, "blend"))
    p = preds["B ensemble of 5 (regression)"]
    common = p["month"].isin(preds["C 3-month target"]["month"].unique())
    print("--- D. high conviction (ensemble blend)")
    for cut in [0.80, 0.85, 0.90]:
        show(f"   both ranks above {cut:.2f}", evaluate(p[common].assign(agree=np.minimum(p["ml_r"], p["steady_r2"])), "agree", top=1.0, min_score=cut))


if __name__ == "__main__":
    main(*sys.argv[1:])
