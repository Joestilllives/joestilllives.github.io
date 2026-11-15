#!/usr/bin/env python3
"""Wikipedia attention as a stock signal, and combined with steady accumulation.

  fetch:  python3 wiki_signals.py fetch SYMBOL_ARTICLES.csv OUT_VIEWS.pkl
  test:   python3 wiki_signals.py test PANEL.pkl OUT_VIEWS.pkl SYMBOL_ARTICLES.csv [OUT.json]

Daily views come from Wikimedia's per-article pageviews API (human readers only).
A day's views are complete before the next day's market close, which is when the
test "buys", so using day t's views for a signal on day t doesn't peek ahead.
"""
import csv, json, subprocess, sys, time
import numpy as np
import pandas as pd

UA = "market-research-script/0.1 (personal research)"
API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
       "{}/daily/20200101/20261231")


def fetch(articles_csv, out):
    rows = list(csv.DictReader(open(articles_csv)))
    frames = []
    for i, r in enumerate(rows):
        res = subprocess.run(["curl", "-sS", "-m", "30", "-A", UA, API.format(r["article"])],
                             capture_output=True, text=True)
        try:
            items = json.loads(res.stdout).get("items", [])
        except json.JSONDecodeError:
            items = []
        if items:
            df = pd.DataFrame({"date": pd.to_datetime([x["timestamp"][:8] for x in items]),
                               "views": [x["views"] for x in items]})
            df["symbol"] = r["symbol"]
            frames.append(df)
        if i % 100 == 0:
            print(f"  {i}/{len(rows)} fetched", flush=True)
        time.sleep(0.15)
    v = pd.concat(frames, ignore_index=True)
    v.to_pickle(out)
    print(f"done: {v['symbol'].nunique()} articles, {len(v):,} daily rows")


def attention(views):
    v = views.sort_values(["symbol", "date"]).copy()
    g = v.groupby("symbol", sort=False)["views"]
    v["med60"] = g.transform(lambda s: s.shift(1).rolling(60, min_periods=30).median())
    v["attn_x"] = v["views"] / v["med60"].clip(lower=5)
    v["attn10"] = g.transform(lambda s: s.rolling(10).mean()) / v["med60"].clip(lower=5)
    spike = (v["attn_x"] >= 3) & (v["views"] >= 200)
    v["spike"] = spike
    v["spike10"] = spike.astype(float).groupby(v["symbol"]).transform(lambda s: s.rolling(10, min_periods=1).max())
    return v[["symbol", "date", "views", "med60", "attn_x", "attn10", "spike", "spike10"]]


def test(panel, views_pkl, articles_csv, out="wiki_results.json"):
    from backtest import prepare, summarize, SPLIT, HORIZONS
    from refine import features, rule
    p = prepare(pd.read_pickle(panel))
    p = p[p["liquid"]].copy()
    f = features(p)
    acc = rule(p, f, {"deliv_pts": 5, "min_days": 8, "vol_trend": 1.2, "max_move": 0.05})
    a = attention(pd.read_pickle(views_pkl))
    p = p.join(a.set_index(["symbol", "date"]), on=["symbol", "date"])
    has_wiki = p["med60"].notna()
    first = p["date"] < SPLIT
    tests = {
        "attention_spike": ("Wikipedia readers 3x+ usual (200+ views)", p["spike"].fillna(False).astype(bool)),
        "spike_price_up": ("Attention spike and price up 5%+ (crowd chasing)", p["spike"].fillna(False).astype(bool) & (p["ret"] >= 0.05)),
        "spike_price_down": ("Attention spike and price down 5%+", p["spike"].fillna(False).astype(bool) & (p["ret"] <= -0.05)),
        "accumulation_wiki_stocks": ("Steady accumulation, stocks with a Wikipedia page (reference)", acc & has_wiki),
        "accumulation_unnoticed": ("Steady accumulation, Wikipedia attention at or below usual, no spike in 10 days",
                                   acc & has_wiki & (p["attn10"] <= 1.1) & (p["spike10"] == 0)),
        "accumulation_noticed": ("Steady accumulation, attention already rising or spiked in last 10 days",
                                 acc & has_wiki & ((p["attn10"] > 1.3) | (p["spike10"] == 1))),
    }
    res = {"wiki_stocks": int(p.loc[has_wiki, "symbol"].nunique()), "signals": {}}
    print(f"Stocks with Wikipedia views data in the liquid universe: {res['wiki_stocks']}")
    for name, (desc, m) in tests.items():
        m = m.fillna(False).astype(bool)
        r = {"description": desc, "first_half": summarize(p[m & first], ""), "second_half": summarize(p[m & ~first], "")}
        res["signals"][name] = r
        for half in ["first_half", "second_half"]:
            s = r[half]
            cells = []
            for h in HORIZONS:
                v = s.get(f"h{h}")
                cells.append(f"{v['mean_excess']*100:6.2f}% med {v['median_excess']*100:5.1f}% t {v['t_stat']:4.1f}" if v else f"{'—':>26}")
            print(f"{name:26} {half[:5]} n={s['events']:<5} " + " | ".join(cells))
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "fetch":
        fetch(*sys.argv[2:4])
    else:
        test(*sys.argv[2:])
