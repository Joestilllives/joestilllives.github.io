"""Fetch headlines from public RSS feeds (standard library only)."""
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
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
        return parsedate_to_datetime(date_text).isoformat()
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


def fetch_all(timeout=20):
    items, errors = [], []
    for url in feed_urls():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                items.extend(parse_rss(r.read(), url))
        except Exception as e:  # one bad feed shouldn't stop the run
            errors.append(f"{url[:80]}: {e}")
    seen, unique = set(), []
    for it in items:
        key = re.sub(r"\W+", " ", it["title"].lower()).strip()
        if key not in seen:
            seen.add(key)
            unique.append(it)
    return unique, errors
