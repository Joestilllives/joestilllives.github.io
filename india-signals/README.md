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

## Data sources tested and what they added (44 months out-of-sample, after costs)

| Added to the model | Ahead/yr | t | Verdict |
|---|---|---|---|
| Base model (trend, flow, frenzy, IPO, Wikipedia company attention) | +4.2% | 2.3 | |
| + peers that move together (Swanson-style links) | +5.1% | 2.9 | helps a little |
| + 50 global outside forces, per-stock links only (`FACTORS`) | **+5.6%** | **3.3** | **best; main model** |
| + raw monthly factor moves | +2.2% | 1.1 | overfits, removed |
| + NSE futures & options (`FO_DIR`) | +4.9% | 3.0 | no gain; large caps price it in |
| + Wikipedia topic attention and weather (`TOPIC_VIEWS`, `WEATHER`) | +4.5% | 2.4 | no gain |

- Indian stocks overreact to global factor moves (oil, metals, US tech): the factor-driven part of
  last month's move reverses next month (top-bottom -0.81%/month, t = -2.9).
- Rising Wikipedia attention to inflation, trade war, tariffs, layoffs and the Fed comes before weaker
  Indian market weeks in both periods, but too weakly to time the market (`wiki_market.py`).
- GDELT news tone could not be collected: its 1-request-per-5-seconds limit is shared by this
  environment's network.

## Swanson-style chains tested (A -> B -> C)

| Chain | Result |
|---|---|
| US-listed version (ADR) moves overnight -> same Indian stock next day (`leadlag.py`) | Strong but priced in at the open (Infosys gaps +1.9%, then +0.3%) |
| Foreign parent moves -> Indian subsidiary next day (`leadlag.py`) | Some drift after the open: HUL +0.6% open-to-close after big Unilever moves (65% right); small |
| Bad results (5%+ drop, 3x volume, results season) -> keeps falling (`results_drift.py`) | Yes, modestly, for about a month |
| Good results -> keeps rising | No; speculative jumps fade |
| Hot IPO (40%+ day 1) -> listed sector peers (`ipo_peers.py`) | Peers +0.4-0.6% next week, fading to -1-1.6% over 3 months; small samples |
| NIFTY 50 additions/removals (`index_changes.py`) | Added stocks lag after (median -3.8% in 3 months); removed ones rebound (+5% next month); only 28 events |
| Small-cap fund inflows -> small caps beat large (`fund_flows.py`) | No |
| Thematic fund inflow surges -> market | Market did better after (+12.7% vs +5.7% over 3 months); weak evidence |
| NSE moves stock into trade-for-trade (`surveillance.py`) | Typical stock lags the market ~15% over 3-6 months; 4,200 events |

## Findings so far (data to 13 Nov 2026)

- **Frenzy days** (volume 3x+ usual, delivery % 15+ points below usual) are followed by
  underperformance vs similar-sized stocks: about -1.35% a month in a portfolio held one
  month, lagging in 86% of months and in every year 2020–2026.
- **Accumulation patterns** (high delivery, flat price) show no reliable edge once
  tested properly.
- An early version of `backtest.py` averaged log returns for the benchmark, which
  understated it by ~2-3% over 60 days and made buy signals look good. Fixed.

Research on past data, not financial advice.
