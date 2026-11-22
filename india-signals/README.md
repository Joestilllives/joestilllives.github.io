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

## Sentiment and mood

| Signal | Result |
|---|---|
| Headline tone (FinBERT on 24,472 Moneycontrol headlines, Sep 2024-Jan 2025; `news_sentiment.py`) | Priced the same day (very positive +0.9%, very negative -0.8% vs market) but no edge after: next-week rank correlation 0.00. Very negative news drifts a little lower (-0.65% next week); very positive fades (-0.5%) |
| Day's overall headline tone -> next day's market | corr -0.14 over 80 days (weak, contrarian) |
| Mumbai sunshine (`mood.py`) | Clear days +0.09 to +0.13%/day better than cloudy, both periods; t about 1 |
| Mumbai air pollution | Clean days +0.25%/day better in 2023-26 (t 1.7); data from Aug 2022 only |
| Moon phase, pre-holiday | Inconsistent |

## The simple algorithm (`algorithm.py`)

Monthly, no machine learning: liquid companies listed 1+ year, ETFs out, most-traded fifth out;
remove stocks with 3+ frenzy days last month; rank by steadiness of the 12-month climb
(12-month return / daily volatility); buy the top 20% in each size group; hold one month.
69 months (Mar 2021-Oct 2026), after 0.3% costs: **+9.4%/yr vs the average company, t = 3.8,
ahead in 74% of months; 2021-23 +10.7%/yr, 2023-26 +8.4%/yr; deepest slide -7.3%.**
Tested pieces: momentum alone +7.7%/yr; global-reversal alone -1.9%/yr (dropped); filtering
any frenzy day hurt (removes a third of stocks). The final recipe was picked from these tests.

### How to use it (the practical version)

- Hold the **top 25 by score in each of the 4 size groups (~100 stocks), equal amounts**,
  and **rebalance every month** (about 44 of 100 change). 69 months: **+9.7%/yr vs the
  average company** (2021-23 +10.0%, 2023-26 +9.5%), t = 3.1, deepest slide -10.4%.
- Fewer stocks (40-60) kept the average but were far less reliable; rebalancing every
  3 months roughly halved the edge.
- NSE momentum / low-volatility / alpha ETFs did NOT capture this: e.g. Nifty200 Momentum 30
  +1.4%/yr and Alpha Low-Vol 30 +1.2%/yr over their 32 months vs +14.2%/yr for the algorithm.
- This month's basket: `results/algorithm/basket_2026-11.csv`; removed for heavy frenzy:
  `results/algorithm/red_flags_2026-11.csv`.

## Findings so far (data to 13 Nov 2026)

- **Frenzy days** (volume 3x+ usual, delivery % 15+ points below usual) are followed by
  underperformance vs similar-sized stocks: about -1.35% a month in a portfolio held one
  month, lagging in 86% of months and in every year 2020–2026.
- **Accumulation patterns** (high delivery, flat price) show no reliable edge once
  tested properly.
- An early version of `backtest.py` averaged log returns for the benchmark, which
  understated it by ~2-3% over 60 days and made buy signals look good. Fixed.

Research on past data, not financial advice.
