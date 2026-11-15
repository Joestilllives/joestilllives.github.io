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

UA = "market-research-script/0.1 (https://joestilllives.github.io; personal research)"
API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
       "{}/daily/20200101/20261231")


def fetch(articles_csv, out):
    """Resumable: each article's views are saved to OUT_dir/<symbol>.json, then
    combined into OUT. Waits as long as Wikimedia's retry-after header asks."""
    import os, re, urllib.parse
    rows = list(csv.DictReader(open(articles_csv)))
    d = out + "_dir"
    os.makedirs(d, exist_ok=True)
    hdr = os.path.join(d, "_headers.txt")
    for i, r in enumerate(rows):
        path = os.path.join(d, r["symbol"] + ".json")
        if os.path.exists(path):
            continue
        art = urllib.parse.quote(urllib.parse.unquote(r["article"]), safe="")
        for attempt in range(12):
            res = subprocess.run(["curl", "-sS", "-m", "30", "-A", UA, "-D", hdr, API.format(art)],
                                 capture_output=True, text=True)
            head = open(hdr).read() if os.path.exists(hdr) else ""
            code = (re.findall(r"HTTP/\S+ (\d+)", head) or ["000"])[-1]
            if code in ("200", "404"):
                break
            ra = re.search(r"retry-after: (\d+)", head, re.I)
            time.sleep(int(ra.group(1)) + 1 if ra else 20)
        items = json.loads(res.stdout).get("items", []) if code == "200" else []
        json.dump(items, open(path, "w"))
        if i % 25 == 0:
            print(f"  {i}/{len(rows)} fetched", flush=True)
        time.sleep(1.0)
    frames = []
    for r in rows:
        path = os.path.join(d, r["symbol"] + ".json")
        items = json.load(open(path)) if os.path.exists(path) else []
        if items:
            df = pd.DataFrame({"date": pd.to_datetime([x["timestamp"][:8] for x in items]),
                               "views": [x["views"] for x in items]})
            df["symbol"] = r["symbol"]
            frames.append(df)
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
    p = prepare(pd.read_pickle(panel))
    p = p[p["liquid"]].copy()
    a = attention(pd.read_pickle(views_pkl))
    p = p.join(a.set_index(["symbol", "date"]), on=["symbol", "date"])
    has_wiki = p["med60"].notna()
    first = p["date"] < SPLIT
    def first_day(m):  # one event per run of consecutive signal days
        m = m.fillna(False).astype(bool)
        return m & ~m.groupby(p["symbol"]).shift(1, fill_value=False).astype(bool)

    spike = p["spike"].fillna(False).astype(bool)
    spike3 = spike.groupby(p["symbol"]).transform(lambda s: s.astype(float).rolling(3, min_periods=1).max()).astype(bool)
    frenzy = ((p["vol_x"] >= 3) & (p["deliv_jump"] <= -15)).fillna(False)
    tests = {
        "attention_spike": ("Wikipedia readers 3x+ usual (200+ views), first day", first_day(spike)),
        "spike_price_up": ("Attention spike and price up 5%+ (crowd chasing)", first_day(spike & (p["ret"] >= 0.05))),
        "spike_price_down": ("Attention spike and price down 5%+", first_day(spike & (p["ret"] <= -0.05))),
        "attention_building": ("10-day average readers 2x+ usual, no single big spike", first_day((p["attn10"] >= 2) & ~spike3)),
        "frenzy_wiki_stocks": ("Frenzy day, stocks with a Wikipedia page (reference)", first_day(frenzy & has_wiki)),
        "frenzy_with_attention": ("Frenzy day with a Wikipedia spike in the last 3 days", first_day(frenzy & has_wiki & spike3)),
        "frenzy_unnoticed": ("Frenzy day, Wikipedia readers at or below usual", first_day(frenzy & has_wiki & (p["attn_x"] <= 1.2) & ~spike3)),
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
