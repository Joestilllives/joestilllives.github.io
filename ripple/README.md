# 🌊 Ripple — hidden market links

News hits one company. Ripple finds who else gets hit, across US and Indian markets.

It applies the "A → B → C" idea (literature-based discovery) to market news:
a headline mentions **A** (e.g. *US auto tariffs*), the link map knows **A → B**
(*JLR builds no cars in the US*) and **B → C** (*JLR is Tata Motors' biggest profit
driver*), so **C** (Tata Motors) is flagged even though the headline never names it.

## How it runs

- `.github/workflows/ripple.yml` runs every 3 hours on GitHub Actions (free).
- `fetch.py` reads public RSS feeds (`data/feeds.json`).
- `engine.py` finds events, reads their direction (rising/falling), walks the link
  map up to 3 hops and ranks the affected companies. Cross-market links get a boost.
- Results go to `output/alerts.json` (shown on `index.html`) and `output/posts.md`
  (ready-to-post social and Telegram text).

```bash
python ripple/tests/test_engine.py   # tests
cd ripple && python run.py --sample   # offline demo
cd ripple && python run.py            # live (needs internet)
```

## Growing the link map

Everything lives in `data/graph.json`. Add an entity (with aliases people use in
headlines) and edges with a one-line `why`. `sign`: +1 moves together, -1 moves
opposite, 0 exposed but unclear. `w`: how strong the link is (0–1). Keep each `why`
factual and checkable; it is shown to readers.

**Research & education only. Not investment advice.** In India, paid stock
*recommendations* need SEBI registration, so keep wording to "exposed to",
never "buy/sell" or price targets.
