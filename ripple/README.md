# 🌊 Ripple — hidden market links

> **Goal (from the owner):** use this for my own trading in Indian and US markets.
> Social content is a maybe-later. Prioritise accuracy, tradable timing (before the
> 9:15 IST open) and honest tests over reach.

## Morning trade signal

`signal_today.py` runs ~6:45 IST on weekdays. Rule, from `backtest.py`: if Accenture
beat (or lagged) the S&P 500 by ≥ 1.5% at the last US close, go long (or intraday
short) the Indian IT basket — TCS, Infosys, Wipro, HCLTech, Tech Mahindra — at the
9:15 open and exit by the close. On the unseen newer half of 5 years of data this
made about +0.3% per trade after ~0.06% costs. `backtest.py` re-tests it daily
alongside controls and ideas that failed (crude → fuel retailers, ADR gaps).
Paper-trade before using real money; edges fade.

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

Once a day, `stats.py` also downloads 2 years of daily prices (Yahoo Finance) and:

- **Scorecard** (`outcomes.py` → `output/scorecard.json`): every live alert is kept in
  `output/alert_log.json`. Each ▲/▼ call is checked 1, 3 and 7 trading days later:
  did the company beat / lag its own market (Nifty or S&P 500), starting from the last
  close before the news? Shown overall, by type and by link.
- **Discoveries** (`discover.py` → `output/discoveries.json`): tests every pair for
  "when X moves, Y beats/lags its market the next trading day". Only links that are
  strong (t ≥ 3.5) **and** hold in both halves of the history are shown; on pure
  random data this finds about one false link every two runs. It also checks every
  link already in the map against real prices (confirmed / weak / contradicted).

```bash
python ripple/tests/test_engine.py   # tests
python ripple/tests/test_stats.py
cd ripple && python run.py --sample   # offline demo
cd ripple && python run.py            # live news (needs internet)
cd ripple && python stats.py          # prices, scorecard, discoveries
```

## Growing the link map

Everything lives in `data/graph.json`. Add an entity (with aliases people use in
headlines) and edges with a one-line `why`. `sign`: +1 moves together, -1 moves
opposite, 0 exposed but unclear. `w`: how strong the link is (0–1). Keep each `why`
factual and checkable; it is shown to readers.

**Research & education only. Not investment advice.** In India, paid stock
*recommendations* need SEBI registration, so keep wording to "exposed to",
never "buy/sell" or price targets.
