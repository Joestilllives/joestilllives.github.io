"""#1 Outcome tracker: did flagged companies actually beat / lag their market afterwards?

For each logged alert impact with a clear direction (tailwind/headwind):
  base  = the last close of that stock at or before the moment the alert was published
  after = the close 1, 3 and 7 trading days later
  excess return = stock return - its market index return over the same days
A tailwind is a "hit" if excess > 0; a headwind is a hit if excess < 0.
"""
import bisect
from collections import defaultdict
from datetime import datetime, timezone

from prices import CLOSE_UTC, benchmark_of, market_of

HORIZONS = (1, 3, 7)
MIN_SAMPLE = 20  # below this, hit rates are mostly noise


def _close_time(date_str, symbol):
    hour = CLOSE_UTC[market_of(symbol)]
    d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return d.timestamp() + hour * 3600


def _period_return(series, dates, i0, i1):
    return series[dates[i1]] / series[dates[i0]] - 1


def score_impact(alert_time, symbol, effect, prices, benchmarks):
    """Return {h: {'excess': x, 'hit': bool}} for horizons that have data."""
    series = prices.get(symbol)
    if not series:
        return {}
    dates = sorted(series)
    times = [_close_time(d, symbol) for d in dates]
    i0 = bisect.bisect_right(times, alert_time) - 1  # last close at/before alert
    if i0 < 0:
        return {}
    bench_sym = benchmark_of(symbol, benchmarks)
    bench = prices.get(bench_sym) if bench_sym else None
    out = {}
    for h in HORIZONS:
        i1 = i0 + h
        if i1 >= len(dates):
            continue
        r = _period_return(series, dates, i0, i1)
        if bench:
            d0, d1 = dates[i0], dates[i1]
            if d0 not in bench or d1 not in bench:
                continue
            r -= bench[d1] / bench[d0] - 1
        want = 1 if effect == "tailwind" else -1
        out[h] = {"excess": round(r, 5), "hit": (r > 0) == (want > 0) and r != 0}
    return out


def build_scorecard(alert_log, prices, symbol_of, benchmarks):
    """alert_log: list of {id, title, published, impacts:[{id, name, effect, path}]}.
    symbol_of: entity id -> yahoo symbol or None."""
    rows = []
    for a in alert_log:
        if not a.get("published"):
            continue
        t = datetime.fromisoformat(a["published"]).timestamp()
        for i in a["impacts"]:
            if i["effect"] not in ("tailwind", "headwind"):
                continue
            sym = symbol_of(i["id"])
            if not sym:
                continue
            res = score_impact(t, sym, i["effect"], prices, benchmarks)
            if not res:
                continue
            link = " → ".join([i["path"][0]["from"]] + [p["to"] for p in i["path"]])
            rows.append({"alert": a["title"], "published": a["published"], "company": i["name"],
                         "symbol": sym, "effect": i["effect"], "link": link,
                         "cross_market": i.get("cross_market", False), "results": res})

    def summarize(subset):
        s = {}
        for h in HORIZONS:
            scored = [(r["effect"], r["results"][h]) for r in subset if h in r["results"]]
            if not scored:
                continue
            vals = [v for _, v in scored]
            hits = sum(v["hit"] for v in vals)
            # average excess move in the predicted direction (positive = prediction paid off)
            edge = sum(v["excess"] * (1 if eff == "tailwind" else -1) for eff, v in scored) / len(vals)
            s[str(h)] = {"n": len(vals), "hit_rate": round(hits / len(vals), 3),
                         "avg_edge_pct": round(edge * 100, 2), "enough_data": len(vals) >= MIN_SAMPLE}
        return s

    by_link = defaultdict(list)
    for r in rows:
        by_link[r["link"]].append(r)
    links = [{"link": k, **{"stats": summarize(v)}} for k, v in by_link.items()]
    links.sort(key=lambda x: -max((s["n"] for s in x["stats"].values()), default=0))

    return {
        "overall": summarize(rows),
        "by_effect": {e: summarize([r for r in rows if r["effect"] == e]) for e in ("tailwind", "headwind")},
        "cross_market": summarize([r for r in rows if r["cross_market"]]),
        "by_link": links[:40],
        "recent": sorted(rows, key=lambda r: r["published"], reverse=True)[:40],
        "min_sample": MIN_SAMPLE,
        "horizons": list(HORIZONS),
    }
