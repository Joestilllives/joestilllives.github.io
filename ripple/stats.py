"""Daily job: fetch prices, score past alerts (#1) and discover links from prices (#2).

    python stats.py           # live (needs internet; run by GitHub Actions once a day)
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from discover import check_map, discover
from engine import Graph
from outcomes import build_scorecard
from prices import fetch_many, yahoo_symbol

HERE = Path(__file__).parent
OUT = HERE / "output"


def symbol_lookup(graph):
    return lambda eid: yahoo_symbol(graph.entities[eid]) if eid in graph.entities else None


def run(prices, graph, errors=()):
    now = datetime.now(timezone.utc).isoformat()
    sym = symbol_lookup(graph)
    log_path = OUT / "alert_log.json"
    log = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []

    scorecard = build_scorecard(log, prices, sym, graph.benchmarks)
    scorecard.update({"generated": now, "alerts_logged": len(log)})
    (OUT / "scorecard.json").write_text(json.dumps(scorecard, indent=1, ensure_ascii=False), encoding="utf-8")

    disc = {
        "generated": now, "symbols_priced": len(prices), "price_errors": len(errors),
        "discoveries": discover(graph, prices, sym, graph.benchmarks),
        "map_check": check_map(graph, prices, sym, graph.benchmarks),
    }
    (OUT / "discoveries.json").write_text(json.dumps(disc, indent=1, ensure_ascii=False), encoding="utf-8")
    return scorecard, disc


def main():
    graph = Graph()
    sym = symbol_lookup(graph)
    symbols = {s for s in (sym(e) for e in graph.entities) if s} | set(graph.benchmarks.values())
    prices, errors = fetch_many(symbols)
    if len(prices) < len(symbols) / 2:
        print(f"Only got {len(prices)}/{len(symbols)} price series; not overwriting results.")
        for e in errors[:10]:
            print("  ", e)
        sys.exit(1)
    scorecard, disc = run(prices, graph, errors)
    o = scorecard["overall"].get("1", {})
    print(f"Prices: {len(prices)}/{len(symbols)} symbols. Alerts logged: {scorecard['alerts_logged']}. "
          f"1-day hit rate: {o.get('hit_rate')} (n={o.get('n', 0)}). "
          f"New links: {sum(not d['in_map'] for d in disc['discoveries'])}. "
          f"Map links checked: {len(disc['map_check'])}.")
    for e in errors[:10]:
        print("  price error:", e)


if __name__ == "__main__":
    main()
