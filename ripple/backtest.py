"""Trade tests: can you make money from US moves the next Indian trading day?

For each signal (a US price move on day d, after India has closed), we trade on the
next Indian session D at the OPEN (09:15 IST, the first price you can actually get)
and exit at the CLOSE. Shorts are intraday (allowed in Indian cash equities).

We report separately:
  gap      = Indian prev close -> open   (news already priced in; you can't capture it)
  intraday = open -> close               (what you can trade)
The threshold is picked on the OLDER half of history and judged on the NEWER half,
so the reported result is not tuned to the data it is judged on.

    python backtest.py
"""
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

from prices import UA  # noqa: F401  (shared user agent)
import urllib.parse
import urllib.request

HERE = Path(__file__).parent
OUT = HERE / "output"

COST_ROUND_TRIP = 0.0006   # ~0.06%: discount-broker intraday equity (brokerage, STT, exchange, GST, stamp)
HEDGE_COST = 0.0003        # extra for the Nifty hedge leg (index futures are cheaper)
THRESHOLDS = [0.005, 0.01, 0.015, 0.02, 0.03]
MIN_TRADES = 15

IT_BASKET = ["TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS"]

STRATEGIES = [
    {"name": "Accenture move → Indian IT basket", "signal": ["ACN"], "target": IT_BASKET},
    {"name": "Accenture beyond the US market → Indian IT basket", "signal": ["ACN"], "minus": "^GSPC", "target": IT_BASKET},
    {"name": "Control: S&P 500 move → Indian IT basket", "signal": ["^GSPC"], "target": IT_BASKET},
    {"name": "Infosys US shares (ADR) → Infosys in India", "signal": ["INFY"], "target": ["INFY.NS"]},
    {"name": "Wipro US shares (ADR) → Wipro in India", "signal": ["WIT"], "target": ["WIPRO.NS"]},
    {"name": "Brent crude → Indian fuel retailers (inverse)", "signal": ["BZ=F"], "target": ["IOC.NS", "BPCL.NS", "HINDPETRO.NS"], "invert": True},
]


def fetch_ohlc(symbol, rng="5y"):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           f"{urllib.parse.quote(symbol, safe='')}?range={rng}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; RippleBot/1.0)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.loads(r.read())["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    out = {}
    for ts, o, c in zip(res["timestamp"], q["open"], q["close"]):
        if o and c and o > 0 and c > 0:
            out[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")] = (float(o), float(c))
    return out


def drop_stale_opens(ohlc):
    """Yahoo sometimes reports an Indian stock's open as exactly the previous close.
    Those days would leak the overnight gap into 'open -> close', faking an edge, so we drop them."""
    d = sorted(ohlc)
    bad = {b for a, b in zip(d, d[1:]) if abs(ohlc[b][0] / ohlc[a][1] - 1) < 1e-5}
    return {k: v for k, v in ohlc.items() if k not in bad}


def daily_returns(ohlc):
    d = sorted(ohlc)
    return {b: ohlc[b][1] / ohlc[a][1] - 1 for a, b in zip(d, d[1:])}


def build_days(strategy, data):
    """One row per Indian session D that follows a US signal day d (d < D, within 4 days)."""
    sig = [daily_returns(data[s]) for s in strategy["signal"]]
    sig = {d: statistics.mean(r[d] for r in sig) for d in sig[0] if all(d in r for r in sig)}
    if strategy.get("minus"):
        m = daily_returns(data[strategy["minus"]])
        sig = {d: v - m[d] for d, v in sig.items() if d in m}
    if strategy.get("invert"):
        sig = {d: -v for d, v in sig.items()}
    nifty = data["^NSEI"]
    tgt = [data[t] for t in strategy["target"]]
    india_days = sorted(set.intersection(*(set(t) for t in tgt)) & set(nifty))
    sig_days = sorted(sig)
    rows, j = [], 0
    for i in range(1, len(india_days)):
        D, prev = india_days[i], india_days[i - 1]
        while j + 1 < len(sig_days) and sig_days[j + 1] < D:
            j += 1
        if not sig_days or sig_days[j] >= D:
            continue
        d = sig_days[j]
        if (datetime.fromisoformat(D) - datetime.fromisoformat(d)).days > 4 or d < prev:
            continue  # US signal must be newer than the previous Indian close
        gap = statistics.mean(t[D][0] / t[prev][1] - 1 for t in tgt)
        intra = statistics.mean(t[D][1] / t[D][0] - 1 for t in tgt)
        n_intra = nifty[D][1] / nifty[D][0] - 1
        rows.append({"date": D, "signal": sig[d], "gap": gap, "intraday": intra, "hedged": intra - n_intra})
    return rows


def corr(xs, ys):
    if len(xs) < 30:
        return None
    mx, my = statistics.mean(xs), statistics.mean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else None


def simulate(rows, k, field, cost):
    trades = []
    for r in rows:
        if abs(r["signal"]) >= k:
            side = 1 if r["signal"] > 0 else -1
            trades.append({"date": r["date"], "side": side, "net": side * r[field] - cost})
    if not trades:
        return {"trades": 0}
    nets = [t["net"] for t in trades]
    eq, peak, dd = 1.0, 1.0, 0.0
    for x in nets:
        eq *= 1 + x
        peak = max(peak, eq)
        dd = min(dd, eq / peak - 1)
    sd = statistics.pstdev(nets) or 1e-9
    return {
        "trades": len(nets), "win_rate": round(sum(x > 0 for x in nets) / len(nets), 3),
        "avg_net_pct": round(statistics.mean(nets) * 100, 3), "total_pct": round((eq - 1) * 100, 1),
        "max_drawdown_pct": round(dd * 100, 1), "t_stat": round(statistics.mean(nets) / sd * math.sqrt(len(nets)), 2),
    }


def evaluate(strategy, data):
    rows = build_days(strategy, data)
    half = len(rows) // 2
    old, new = rows[:half], rows[half:]
    res = {"name": strategy["name"], "days": len(rows),
           "from": rows[0]["date"] if rows else None, "to": rows[-1]["date"] if rows else None,
           "corr_gap": round(corr([r["signal"] for r in rows], [r["gap"] for r in rows]) or 0, 3),
           "corr_intraday": round(corr([r["signal"] for r in rows], [r["intraday"] for r in rows]) or 0, 3),
           "variants": []}
    for field, cost, label in (("intraday", COST_ROUND_TRIP, "open → close"),
                               ("hedged", COST_ROUND_TRIP + HEDGE_COST, "open → close, Nifty-hedged")):
        grid = {k: simulate(old, k, field, cost) for k in THRESHOLDS}
        usable = {k: v for k, v in grid.items() if v["trades"] >= MIN_TRADES}
        best_k = max(usable, key=lambda k: usable[k]["avg_net_pct"]) if usable else None
        res["variants"].append({
            "trade": label, "picked_threshold_pct": best_k * 100 if best_k else None,
            "older_half": usable.get(best_k) if best_k else None,
            "newer_half": simulate(new, best_k, field, cost) if best_k else None,
            "all_thresholds_full_period": {f"{k*100:g}%": simulate(rows, k, field, cost) for k in THRESHOLDS},
        })
    return res


def verdict(r):
    best = None
    for v in r["variants"]:
        n = v["newer_half"]
        if n and n.get("trades", 0) >= MIN_TRADES and (best is None or n["avg_net_pct"] > best[1]["avg_net_pct"]):
            best = (v, n)
    if not best:
        return "Not enough trades to judge."
    v, n = best
    if n["avg_net_pct"] > 0.05 and n["t_stat"] >= 2:
        return f"Promising: held up on unseen data ({v['trade']}), {n['avg_net_pct']:+.2f}% per trade after costs."
    if n["avg_net_pct"] > 0:
        return "Small edge after costs, not statistically solid. Watch, don't trade yet."
    return "No tradable edge after costs: the move is already in the opening price."


def main():
    symbols = {"^NSEI", "^GSPC"}
    for s in STRATEGIES:
        symbols |= set(s["signal"]) | set(s["target"]) | ({s["minus"]} if s.get("minus") else set())
    data, errors = {}, []
    for s in sorted(symbols):
        try:
            data[s] = fetch_ohlc(s)
            if s.endswith(".NS") or s == "^NSEI":
                data[s] = drop_stale_opens(data[s])
        except Exception as e:
            errors.append(f"{s}: {e}")
    results = []
    for s in STRATEGIES:
        need = set(s["signal"]) | set(s["target"]) | {"^NSEI"} | ({s["minus"]} if s.get("minus") else set())
        if need - set(data):
            continue
        r = evaluate(s, data)
        r["verdict"] = verdict(r)
        results.append(r)
    OUT.mkdir(exist_ok=True)
    payload = {"generated": datetime.now(timezone.utc).isoformat(), "cost_round_trip_pct": COST_ROUND_TRIP * 100,
               "note": "Days where Yahoo's Indian open equals the previous close are excluded as possibly stale.",
               "errors": errors, "strategies": results}
    (OUT / "backtest.json").write_text(json.dumps(payload, indent=1), encoding="utf-8")
    for r in results:
        print(f"\n== {r['name']}  ({r['days']} days, {r['from']} → {r['to']})")
        print(f"   signal vs opening gap: r={r['corr_gap']}   signal vs open→close: r={r['corr_intraday']}")
        for v in r["variants"]:
            print(f"   [{v['trade']}] threshold {v['picked_threshold_pct']}%  older: {v['older_half']}")
            print(f"   {' ' * len(v['trade'])}   newer (unseen): {v['newer_half']}")
        print("   →", r["verdict"])
    for e in errors:
        print("error:", e)


if __name__ == "__main__":
    main()
