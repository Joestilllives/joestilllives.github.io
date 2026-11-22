"""#2 Price-based link discovery (no AI).

For every pair (leader X, follower Y):
  "When X moves on a day, does Y beat or lag its own market on Y's NEXT trading day?"
Follower returns are market-adjusted (minus Nifty / S&P / Taiwan index) so we don't
rediscover "everything moves with the market". A link is only reported when it is
statistically strong AND holds in both halves of the history (older and newer).

It also measures the links already in the map and marks them confirmed / weak /
contradicted by real prices.
"""
import bisect
import math
from datetime import datetime

from prices import benchmark_of, returns

T_DISCOVER = 3.5   # overall t-stat needed to report a new link (≈1 false alarm per 2–3 runs on pure noise)
T_HALF = 2.0       # each half of history must point the same way at least this strongly
T_CONFIRM = 2.0    # for checking existing map links
MAX_GAP_DAYS = 4   # ignore leader moves older than this (long holidays)


def _corr(xs, ys):
    n = len(xs)
    if n < 30:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    r = sxy / math.sqrt(sxx * syy)
    r = max(min(r, 0.999999), -0.999999)
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return {"r": r, "t": t, "n": n, "beta": sxy / sxx}


def _days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def align(leader, follower, lag):
    """Pair follower return on day d with leader return on the latest day < d (lag=1)
    or on the same day d (lag=0). Returns (xs, ys)."""
    ldates = sorted(leader)
    xs, ys = [], []
    for d in sorted(follower):
        if lag == 0:
            if d in leader:
                xs.append(leader[d]); ys.append(follower[d])
            continue
        i = bisect.bisect_left(ldates, d) - 1
        if i < 0 or _days(ldates[i], d) > MAX_GAP_DAYS:
            continue
        xs.append(leader[ldates[i]]); ys.append(follower[d])
    return xs, ys


def measure(leader, follower, lag):
    xs, ys = align(leader, follower, lag)
    full = _corr(xs, ys)
    if not full:
        return None
    h = len(xs) // 2
    a, b = _corr(xs[:h], ys[:h]), _corr(xs[h:], ys[h:])
    full["stable"] = bool(a and b and (a["t"] > 0) == (b["t"] > 0) == (full["t"] > 0)
                          and min(abs(a["t"]), abs(b["t"])) >= T_HALF)
    full["halves"] = [round(a["t"], 2) if a else None, round(b["t"], 2) if b else None]
    return full


def build_series(graph, prices, symbol_of, benchmarks):
    """Per entity: raw returns (for leading) and market-adjusted returns (for following)."""
    raw, adj = {}, {}
    for eid, ent in graph.entities.items():
        sym = symbol_of(eid)
        if not sym or sym not in prices:
            continue
        r = returns(prices[sym], invert=ent.get("invert", False))
        raw[eid] = r
        b = benchmark_of(sym, benchmarks)
        if b and b in prices:
            br = returns(prices[b])
            adj[eid] = {d: v - br[d] for d, v in r.items() if d in br}
        else:
            adj[eid] = r
    return raw, adj


def _linked(graph, a, b, hops=2):
    """Is b reachable from a (or a from b) within `hops` steps in the map?"""
    def reach(src, dst):
        frontier, seen = {src}, {src}
        for _ in range(hops):
            nxt = set()
            for n in frontier:
                for e in graph.out[n]:
                    if e["to"] == dst:
                        return True
                    if e["to"] not in seen:
                        seen.add(e["to"]); nxt.add(e["to"])
            frontier = nxt
        return False
    return reach(a, b) or reach(b, a)


def _sentence(graph, lead, follow, m):
    L, F = graph.entities[lead]["name"], graph.entities[follow]["name"]
    move = abs(m["beta"]) * 100
    way = "outperform" if m["beta"] > 0 else "underperform"
    return (f"When {L} rises 1%, {F} tends to {way} its market by about {move:.2f}% "
            f"the next trading day (and the reverse when it falls).")


def discover(graph, prices, symbol_of, benchmarks, limit=40):
    raw, adj = build_series(graph, prices, symbol_of, benchmarks)
    groups = {}
    for gname, members in getattr(graph, "groups", {}).items():
        for m in members:
            groups.setdefault(m, set()).add(gname)

    found = []
    for lead in raw:
        for follow in adj:
            if lead == follow or graph.entities[follow]["type"] != "company":
                continue
            m = measure(raw[lead], adj[follow], lag=1)
            if not m or abs(m["t"]) < T_DISCOVER or not m["stable"]:
                continue
            found.append({
                "leader": graph.entities[lead]["name"], "follower": graph.entities[follow]["name"],
                "leader_market": graph.entities[lead]["market"], "follower_market": graph.entities[follow]["market"],
                "r": round(m["r"], 3), "t": round(m["t"], 2), "n": m["n"], "beta": round(m["beta"], 4),
                "halves_t": m["halves"],
                "in_map": _linked(graph, lead, follow),
                "same_sector": bool(groups.get(lead, set()) & groups.get(follow, set())),
                "sentence": _sentence(graph, lead, follow, m),
            })
    found.sort(key=lambda x: (x["in_map"], x["same_sector"], -abs(x["t"])))
    return found[:limit]


def check_map(graph, prices, symbol_of, benchmarks):
    """Measure every map edge whose both ends have prices."""
    raw, adj = build_series(graph, prices, symbol_of, benchmarks)
    out, seen = [], set()
    for src, edges in graph.out.items():
        for e in edges:
            dst = e["to"]
            if src not in raw or dst not in adj or (src, dst) in seen:
                continue
            seen.add((src, dst))
            best = None
            for lag in (0, 1):
                m = measure(raw[src], adj[dst], lag)
                if m and (best is None or abs(m["t"]) > abs(best["t"])):
                    best, best["lag"] = m, lag
            if not best:
                continue
            measured = 1 if best["t"] > 0 else -1
            if abs(best["t"]) < T_CONFIRM:
                status = "weak"
            elif e["sign"] == 0:
                status = "direction found"
            else:
                status = "confirmed" if measured == e["sign"] else "contradicted"
            out.append({
                "from": graph.entities[src]["name"], "to": graph.entities[dst]["name"],
                "expected": e["sign"], "measured": measured, "t": round(best["t"], 2), "r": round(best["r"], 3),
                "n": best["n"], "timing": "same day" if best["lag"] == 0 else "next day",
                "status": status, "why": e["why"],
            })
    order = {"contradicted": 0, "confirmed": 1, "direction found": 2, "weak": 3}
    out.sort(key=lambda x: (order[x["status"]], -abs(x["t"])))
    return out
