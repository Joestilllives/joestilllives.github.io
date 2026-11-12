# Wikipedia surge detector

Finds pages that suddenly started getting far more readers than usual, across every
language of Wikipedia, using Wikimedia's public hourly pageview dumps.

```
python3 detect.py                 # last 3 hours vs the 24 before, top 60
python3 detect.py --recent 2 --baseline 48 --top 100 --out results.json
```

How it scores a page:
- adds desktop + mobile views per hour
- divides the recent rate by the baseline rate (+3 smoothing)
- corrects for each language's normal daily rhythm (whole-language traffic swing)
- needs at least 40 views/hour; skips admin namespaces and main pages
- labels the curve: **climbing** (still rising each hour, the early-warning case),
  **holding** (jumped and stayed up) or **fading** (short burst)
- groups English pages with their other-language versions (via the Wikipedia API)
  to tell **global** surges from **local** ones

Downloads (~55 MB per hour) are cached in `.cache/`. A full run takes ~2 minutes.
