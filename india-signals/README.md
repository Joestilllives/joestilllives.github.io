# India market signals (NSE)

Research on whether public NSE data (prices, volume, delivery %) predicts how a
stock does against similar-sized stocks over the next week to three months.

| Script | What it does |
|---|---|
| `download.py` | Downloads NSE's daily files with delivery data (2020 onwards) |
| `build_panel.py` | Combines them into one table |
| `backtest.py` | Tests six patterns per event, split 2020–Jun 2023 / Jul 2023–2026 |
| `refine.py` | Tunes the accumulation rule on the first half, tests once on the second |
| `portfolio.py` | Simulates holding every signalled stock, day by day, vs a size-matched benchmark |
| `scan.py` | Lists today's frenzy stocks |
| `match_wikipedia.py`, `wiki_signals.py` | Wikipedia attention signals (blocked by Wikimedia rate limits so far) |

## The combined money signal (`combined.py`)

One score per company, weighing ~30 signals together (trend, money flow, frenzy, IPO history,
Wikipedia attention, market mood), learned by a gradient-boosted model and tested walk-forward
(trained only on months already known). Companies only, ETFs excluded (`funds_exclude.txt`),
no survivorship leaks. Out-of-sample Feb 2023 – Sep 2026 (44 months), buy list = top 20%
within each size group, after 0.3% costs: **+0.35%/month vs the market (~+4%/yr), t = 2.3,
correct ranking direction in 86% of months, deepest slide vs market -2.4%.**

Run: `BHAVCOPY=<latest BhavCopy csv> python3 combined.py PANEL.pkl INDUSTRY.csv IPOS.csv VIEWS.pkl OUTDIR`

## Findings so far (data to 13 Nov 2026)

- **Frenzy days** (volume 3x+ usual, delivery % 15+ points below usual) are followed by
  underperformance vs similar-sized stocks: about -1.35% a month in a portfolio held one
  month, lagging in 86% of months and in every year 2020–2026.
- **Accumulation patterns** (high delivery, flat price) show no reliable edge once
  tested properly.
- An early version of `backtest.py` averaged log returns for the benchmark, which
  understated it by ~2-3% over 60 days and made buy signals look good. Fixed.

Research on past data, not financial advice.
