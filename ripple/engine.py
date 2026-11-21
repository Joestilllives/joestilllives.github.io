"""Ripple engine: find second-order (hidden) effects of news across US and Indian markets.

A headline mentions an event (A). The link map says A affects B, and B affects C.
If the headline never mentions C, then C is a "hidden link" worth flagging.
"""
import hashlib
import json
import re
from collections import deque
from pathlib import Path

HERE = Path(__file__).parent
MAX_HOPS = 3
MIN_SCORE = 0.12

UP_WORDS = [
    "surge", "surges", "surged", "soar", "soars", "soared", "jump", "jumps", "jumped",
    "rise", "rises", "rising", "rose", "climb", "climbs", "climbed", "rally", "rallies",
    "spike", "spikes", "spiked", "hike", "hikes", "hiked", "raise", "raises", "raised",
    "boost", "boosts", "boosted", "record high", "beat", "beats", "strong", "strengthens",
    "strengthened", "gain", "gains", "gained", "expand", "expands", "increase", "increases",
    "higher", "tighten", "tightens", "tougher", "escalate", "escalates", "escalation",
    "impose", "imposes", "imposed", "above normal", "above-normal", "upgrade", "upbeat",
    "accelerate", "accelerates", "doubles", "fee hike", "inflows", "lift", "lifts", "lifted",
    "ramps up", "boom", "booms", "record",
]
DOWN_WORDS = [
    "fall", "falls", "fell", "drop", "drops", "dropped", "plunge", "plunges", "plunged",
    "slump", "slumps", "slumped", "tumble", "tumbles", "tumbled", "slide", "slides", "slid",
    "decline", "declines", "declined", "cut", "cuts", "lower", "lowers", "weak", "weaker",
    "weakens", "weakened", "miss", "misses", "missed", "ease", "eases", "eased", "easing",
    "calm", "ceasefire", "truce", "reopen", "reopens", "deficient", "below normal",
    "below-normal", "delayed", "scrap", "scraps", "removes", "rollback", "rolls back",
    "pause", "pauses", "exempt", "exempts", "exemption", "downgrade", "warns", "warning",
    "slash", "slashes", "reduce", "reduces", "outflows", "sell-off", "selloff", "record low",
    "shrinks", "contracts", "halts", "halt", "strike", "recall", "probe", "slowdown",
]

DISCLAIMER = "Research & education only. Not investment advice."


def _compile(words):
    alts = sorted((re.escape(w) for w in words), key=len, reverse=True)
    return re.compile(r"\b(" + "|".join(alts) + r")\b", re.IGNORECASE)


UP_RE = _compile(UP_WORDS)
DOWN_RE = _compile(DOWN_WORDS)


class Graph:
    def __init__(self, path=HERE / "data" / "graph.json"):
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        self.entities = {e["id"]: e for e in raw["entities"]}
        groups = raw.get("groups", {})
        self.out = {eid: [] for eid in self.entities}
        for e in raw["edges"]:
            targets = groups[e["to"][1:]] if e["to"].startswith("@") else [e["to"]]
            for t in targets:
                if e["from"] not in self.entities or t not in self.entities:
                    raise ValueError(f"Unknown entity in edge {e}")
                self.out[e["from"]].append({**e, "to": t})
        self.matchers = []
        for eid, ent in self.entities.items():
            for alias in ent["aliases"]:
                cs = alias.startswith("=")
                text = alias[1:] if cs else alias
                pat = re.compile(r"(?<![\w-])" + re.escape(text) + r"(?![\w-])", 0 if cs else re.IGNORECASE)
                self.matchers.append((eid, pat))

    def find_mentions(self, text):
        """Return {entity_id: (start, end)} for entities mentioned in text (longest alias wins)."""
        hits = []
        for eid, pat in self.matchers:
            for m in pat.finditer(text):
                hits.append((m.start(), m.end(), eid))
        hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
        found, last_end = {}, -1
        for s, e, eid in hits:
            if s < last_end:
                continue  # overlapped by a longer alias
            last_end = e
            found.setdefault(eid, (s, e))
        return found


def direction_near(text, start, end):
    """Look for up/down words close to the mention; prefer words right after it."""
    best = None
    windows = [(text[end:end + 45], 0), (text[max(0, start - 30):start], 1)]
    for chunk, side in windows:
        for regex, sign in ((UP_RE, 1), (DOWN_RE, -1)):
            for m in regex.finditer(chunk):
                dist = m.start() if side == 0 else len(chunk) - m.end()
                cand = (side, dist, sign)
                if best is None or cand < best:
                    best = cand
    return best[2] if best else 0


def propagate(graph, seed, seed_dir):
    """BFS from a seed entity. Returns {target: best_path_info}."""
    results = {}
    queue = deque([(seed, seed_dir, 1.0, [])])
    while queue:
        node, d, score, path = queue.popleft()
        if len(path) >= MAX_HOPS:
            continue
        for edge in graph.out[node]:
            t = edge["to"]
            if t == seed or any(step["to"] == t for step in path):
                continue
            nd = d * edge["sign"]
            ns = score * edge["w"] * (0.85 if len(path) else 1.0)
            if ns < MIN_SCORE:
                continue
            npath = path + [{"from": node, "to": t, "why": edge["why"], "sign": edge["sign"]}]
            if t not in results or ns > results[t]["score"]:
                results[t] = {"dir": nd, "score": ns, "path": npath}
            queue.append((t, nd, ns, npath))
    return results


def effect_label(d):
    return {1: "tailwind", -1: "headwind"}.get(d, "exposed")


def analyze(graph, item):
    """Analyze one news item -> alert dict or None."""
    title = item["title"]
    mentions = graph.find_mentions(title)
    if not mentions:
        return None
    seeds = []
    for eid, (s, e) in mentions.items():
        d = direction_near(title, s, e)
        if d == 0:
            d = graph.entities[eid].get("default_dir", 0)
        seeds.append({"id": eid, "name": graph.entities[eid]["name"], "dir": d})

    impacts = {}
    for seed in seeds:
        for t, info in propagate(graph, seed["id"], seed["dir"]).items():
            ent = graph.entities[t]
            if t in mentions or ent["type"] != "company":
                continue  # already in the headline, or not an investable company
            seed_market = graph.entities[seed["id"]]["market"]
            cross = seed_market != ent["market"] and "Global" not in (seed_market, ent["market"]) \
                or (seed_market == "Global" and ent["market"] == "IN")
            score = info["score"] * (1.25 if cross else 1.0) * (1.0 if info["dir"] else 0.75)
            prev = impacts.get(t)
            if prev and prev["dir"] != info["dir"] and prev["dir"] != 0 and info["dir"] != 0:
                prev["dir"] = 0
                prev["mixed"] = True
            if prev and prev["score"] >= score:
                continue
            impacts[t] = {
                "id": t, "name": ent["name"], "market": ent["market"], "ticker": ent.get("ticker"),
                "unlisted": ent.get("unlisted", False), "dir": info["dir"] if not (prev and prev.get("mixed")) else 0,
                "mixed": bool(prev and prev.get("mixed")), "score": round(score, 3), "cross_market": cross,
                "path": [{"from": graph.entities[p["from"]]["name"], "to": graph.entities[p["to"]]["name"],
                          "why": p["why"]} for p in info["path"]],
            }
    if not impacts:
        return None
    ranked = sorted(impacts.values(), key=lambda x: -x["score"])
    for r in ranked:
        r["effect"] = effect_label(r["dir"])
    alert = {
        "id": hashlib.sha1(title.lower().encode()).hexdigest()[:12],
        "title": title, "url": item.get("url"), "source": item.get("source"),
        "published": item.get("published"), "sample": item.get("sample", False),
        "seeds": [{"name": s["name"], "dir": {1: "rising", -1: "falling"}.get(s["dir"], "in the news")} for s in seeds],
        "impacts": ranked[:8],
        "score": round(ranked[0]["score"] + 0.05 * min(len(ranked), 6), 3),
        "cross_market": any(r["cross_market"] for r in ranked),
    }
    alert["post"] = make_post(alert)
    alert["telegram"] = make_telegram(alert)
    return alert


def _arrow(effect):
    return {"tailwind": "▲", "headwind": "▼"}.get(effect, "◆")


def make_post(alert):
    """Short social-media post (Reels caption / X / LinkedIn)."""
    # Lead with the least obvious link: clear direction, cross-market, longest chain.
    top = max(alert["impacts"], key=lambda i: (i["dir"] != 0, i["cross_market"], len(i["path"]), i["score"]))
    chain = " → ".join([top["path"][0]["from"]] + [p["to"] for p in top["path"]])
    lines = [f"🌊 The news: {alert['title']}", "", "The hidden link nobody's talking about:", chain, ""]
    for p in top["path"]:
        lines.append(f"• {p['why']}.")
    others = [i for i in alert["impacts"] if i is not top][:4]
    if others:
        lines += ["", "Also in the ripple: " + ", ".join(f"{i['name']} {_arrow(i['effect'])}" for i in others)]
    lines += ["", "▲ possible tailwind ▼ possible headwind ◆ exposed", DISCLAIMER, "#stockmarket #nifty #wallstreet #ripple"]
    return "\n".join(lines)


def make_telegram(alert):
    """Compact alert for a Telegram channel."""
    lines = [f"⚡ RIPPLE ALERT{' · cross-market' if alert['cross_market'] else ''}", f"📰 {alert['title']}"]
    if alert.get("source"):
        lines.append(f"Source: {alert['source']}")
    lines.append("")
    for i in alert["impacts"][:5]:
        tick = f" ({i['ticker']})" if i.get("ticker") else (" (unlisted)" if i.get("unlisted") else "")
        via = " → ".join([i["path"][0]["from"]] + [p["to"] for p in i["path"][:-1]])
        lines.append(f"{_arrow(i['effect'])} {i['name']}{tick} [{i['market']}] — {i['effect']}, via {via}")
    if alert.get("url"):
        lines += ["", alert["url"]]
    lines += ["", DISCLAIMER]
    return "\n".join(lines)
