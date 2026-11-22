"""Fetch headlines from public RSS feeds (standard library only)."""
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

HERE = Path(__file__).parent
UA = "Mozilla/5.0 (compatible; RippleBot/1.0; +https://github.com)"


def feed_urls():
    cfg = json.loads((HERE / "data" / "feeds.json").read_text(encoding="utf-8"))
    urls = list(cfg["rss"])
    for q in cfg["google_news_queries"]:
        qs = urllib.parse.quote(f"{q} when:1d")
        urls.append(f"https://news.google.com/rss/search?q={qs}&hl=en-IN&gl=IN&ceid=IN:en")
    return urls


def _iso(date_text):
    try:
        return parsedate_to_datetime(date_text).astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def parse_rss(xml_bytes, feed_url):
    items = []
    root = ET.fromstring(xml_bytes)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        if not title:
            continue
        source = it.findtext("source")
        if "news.google.com" in feed_url:
            # Google News titles end with " - Publisher"
            m = re.match(r"^(.*)\s+-\s+([^-]+)$", title)
            if m:
                title, source = m.group(1).strip(), source or m.group(2).strip()
        if not source:
            source = urllib.parse.urlparse(feed_url).netloc.replace("www.", "")
        items.append({
            "title": title,
            "url": (it.findtext("link") or "").strip(),
            "source": source,
            "published": _iso(it.findtext("pubDate") or ""),
        })
    return items


GDELT = ("https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist&format=json"
         "&maxrecords=75&timespan=1d&sort=datedesc")


def fetch_gdelt(timeout=30):
    """GDELT: free global news index. Rate limit is ~1 request per 5 seconds."""
    cfg = json.loads((HERE / "data" / "feeds.json").read_text(encoding="utf-8"))
    items, errors = [], []
    for q in cfg.get("gdelt_queries", []):
        url = GDELT.format(q=urllib.parse.quote(q + " sourcelang:english"))
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    data = json.loads(r.read().decode("utf-8", "replace"), strict=False)
                for a in data.get("articles", []):
                    sd = a.get("seendate", "")
                    pub = (f"{sd[0:4]}-{sd[4:6]}-{sd[6:8]}T{sd[9:11]}:{sd[11:13]}:{sd[13:15]}+00:00"
                           if len(sd) >= 15 else None)
                    if a.get("sourcecountry") and a["sourcecountry"] not in cfg.get("gdelt_countries", [a["sourcecountry"]]):
                        continue
                    items.append({"title": a.get("title", "").strip(), "url": a.get("url"),
                                  "source": a.get("domain"), "published": pub})
                break
            except Exception as e:
                if attempt == 2:
                    errors.append(f"gdelt {q[:40]}: {e}")
                time.sleep(8 * (attempt + 1))
        else:
            break  # GDELT is throttling us; skip the rest instead of waiting minutes
        time.sleep(6)
    return [i for i in items if i["title"]], errors


def fetch_all(timeout=20):
    items, errors = fetch_gdelt()
    for url in feed_urls():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                items.extend(parse_rss(r.read(), url))
        except Exception as e:  # one bad feed shouldn't stop the run
            errors.append(f"{url[:80]}: {e}")
    cfg = json.loads((HERE / "data" / "feeds.json").read_text(encoding="utf-8"))
    skip = re.compile(r"\b(" + "|".join(map(re.escape, cfg.get("skip_if_title_mentions", ["$^"]))) + r")\b", re.I)
    items = [it for it in items if not skip.search(it["title"])]
    seen, unique = set(), []
    for it in items:
        key = re.sub(r"\W+", " ", it["title"].lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return unique, errors
