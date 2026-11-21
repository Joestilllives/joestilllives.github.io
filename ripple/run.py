"""Run Ripple: fetch news, find hidden links, write output/alerts.json and output/posts.md.

    python ripple/run.py            # live news (used by GitHub Actions)
    python ripple/run.py --sample   # offline demo using data/sample_news.json
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from engine import Graph, analyze
from fetch import fetch_all

HERE = Path(__file__).parent
OUT = HERE / "output"
KEEP_DAYS = 3
MAX_ALERTS = 60


def main():
    sample = "--sample" in sys.argv
    now = datetime.now(timezone.utc)
    if sample:
        items = json.loads((HERE / "data" / "sample_news.json").read_text(encoding="utf-8"))
        for it in items:
            it["sample"] = True
            it.setdefault("published", now.isoformat())
        errors = []
    else:
        items, errors = fetch_all()

    graph = Graph()
    alerts = {}
    # Keep recent live alerts from earlier runs so the feed doesn't empty between runs.
    prev_path = OUT / "alerts.json"
    if prev_path.exists() and not sample:
        for a in json.loads(prev_path.read_text(encoding="utf-8")).get("alerts", []):
            if not a.get("sample"):
                alerts[a["id"]] = a
    for it in items:
        a = analyze(graph, it)
        if a:
            alerts[a["id"]] = a

    cutoff = (now - timedelta(days=KEEP_DAYS)).isoformat()
    kept = [a for a in alerts.values() if (a.get("published") or now.isoformat()) >= cutoff]
    kept.sort(key=lambda a: (-a["score"], a.get("published") or ""))
    kept = kept[:MAX_ALERTS]

    OUT.mkdir(exist_ok=True)
    payload = {
        "generated": now.isoformat(), "sample": sample, "headlines_scanned": len(items),
        "feed_errors": len(errors), "alerts": kept,
    }
    prev_path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")

    md = [f"# Ripple posts — {now:%Y-%m-%d %H:%M} UTC", ""]
    for a in kept[:10]:
        md += [f"## {a['title']}", "", "### Post", "", a["post"], "", "### Telegram", "", a["telegram"], "", "---", ""]
    (OUT / "posts.md").write_text("\n".join(md), encoding="utf-8")

    print(f"Scanned {len(items)} headlines, {len(errors)} feed errors, {len(kept)} alerts.")
    for e in errors[:5]:
        print("  feed error:", e)


if __name__ == "__main__":
    main()
