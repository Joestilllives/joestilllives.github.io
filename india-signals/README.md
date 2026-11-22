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

### With only a few holdings

- **10-20 stocks:** 24 variants tested over the model's 44 out-of-sample months (steady score,
  ML score, both agreeing, larger stocks only, spread across peer groups). Results swung from
  -1% to +17%/yr with no consistent winner; t-stats mostly below 2. The edge needs breadth.
- **Index-fund rotation on real NSE ETFs, 70 months (2021-26):**

| Strategy | per year | worst fall | 2021-23 | 2023-26 |
|---|---|---|---|---|
| Hold Nifty 50 (NIFTYBEES) | +10.4% | -13.7% | +15.2% | +6.8% |
| Hold Midcap 150 / Next 50 | +16.2% | -20.2% | +19.0% | +14.0% |
| Trend filter: best equity ETF, else cash | +13.7% | -9.5% | +16.4% | +11.7% |
| Trend filter: midcap, else gold | +20.2% | -26.5% | +16.8% | +22.9% |
| Dual momentum (best of 5 incl. gold, else cash) | +23.3% | -20.8% | +7.8% | +37.3% (gold rally) |

Trend filter = more than half of stocks above their 200-day average and Nifty 50 up over
3 months. Cash assumed at 6.5%/yr.

## Ten-year test (2016-2026, `download_old.py` adds 2016-2019 prices + delivery)

Combined model, 92 out-of-sample months (Feb 2019-Sep 2026): **+8.4%/yr vs the average
company, t = 3.9, beat the market in all 8 years**, deepest slide vs market -3.7%.
Simple algorithm, 117 months (2017-2026): +9.0%/yr, t = 3.8, beat the market 9 of 10 years
(2018 crash: -22% vs market -30%; lost only in 2022, -5.4%).

| Year | Market | Model vs market | Algorithm vs market |
|---|---|---|---|
| 2017 | +42% | (training) | +16.6% |
| 2018 | -30% | (training) | +7.6% |
| 2019 | -2% | +7.5% | +4.2% |
| 2020 | +24% | +21.7% | +10.1% |
| 2021 | +67% | +11.0% | +39.1% |
| 2022 | 0% | +7.1% | -5.4% |
| 2023 | +68% | +2.5% | +15.2% |
| 2024 | +5% | +8.9% | +7.2% |
| 2025 | -6% | +11.3% | +10.6% |
| 2026 (9 mo) | +9% | +7.9% | +12.6% |

Improvements on the same 94 months (`improve.py`): **blend of steady-climb rank and model rank
+12.6%/yr (t 5.0); with the buffer rule +11.9%/yr, t 5.2, ahead 72% of months, turnover 31%**.
Worst absolute fall of the simple rule over 2016-2026 was -47% (2018 crash into COVID); 50% cash
when the market is unhealthy cut it to -23% for ~1-2%/yr less excess return.

## Signal factory (`signal_factory.py`) and odds tests (`odds.py`)

115 candidate signals generated from daily open/high/low/close, volume, trades and delivery
(windows 5-252 days), each judged by its monthly rank correlation with next month's return
(size groups 1-4). 67 pass |t| >= 3 with the same sign in 2017-19, 2020-22 and 2023-26. They form
about seven families: delivery level (t 7.8) and delivery rising (6.9); lottery/jumpiness, worse
(-6.2); closing near the day's high over months (5.1); rising intraday rather than overnight (5.1);
steady up-days (5.7); large average trade size (4.2).

Honest test (signals chosen on 2017-21 only, model tested on 2022-26): blend +10.7%/yr (t 5.2) vs
+10.3% without them; model alone +9.1% vs +8.1%. Real but overlapping with existing signals.
(Choosing them on all years showed +13.4%: inflated by look-ahead.)

Odds: share of picked stocks that beat the market stays 47-50% for every variant (the edge comes
from winners winning by more); share of months ahead 65-77%. A high-conviction basket (both scores
in the top 20%, ~50 stocks): +15.5%/yr, t 4.5, both halves positive.

## Audit (`audit.py`, ensemble blend, 91 out-of-sample months, corrected returns)

| Check | Result | Verdict |
|---|---|---|
| Random picks from the same size groups and filters (20 draws) | -1.2%/yr vs market | No free edge from the universe choice; skill ~ +14%/yr |
| Placebo: scores shuffled within each month | -1.8%/yr | Pipeline creates no edge by itself |
| Picks that stop trading mid-month (frozen prices) | 0.25% of picks | Worst case -1.5%/yr if all had crashed; realistically small |
| Daily moves beyond 25% dropped while held | 62, all inspected: splits, bonuses, a special payout | Rule is correct; widened split/bonus detector (1,147 events) |
| Costs 0.3% / 0.6% / 1.0% per round trip | +13.0% / +11.0% / +8.5% per yr | Survives triple costs |
| Basket vs index funds, same months | ~+34%/yr vs Nifty 50 +10.5%, Midcap 150 +18.3%, Smallcap 250 +20.5% | Ahead in 62-70% of months |
| Scores used one month late | +9.6%/yr | Signal fades slowly: not a timing artifact |
| All Wikipedia inputs removed (survivor-leak check) | +12.9%/yr | No leak |
| Picks moved into BE/BZ surveillance while held (`gap2.py`) | 1.74% of picks; recorded +10.6% vs true +7.9% | Overstates the edge by ~0.6 points/yr |

Open issues: several design choices (blend, skipping the largest fifth, frenzy threshold, split/bonus
flag, ensemble) were made after seeing 2019-26 results, and no untouched holdout remains; only months
after Nov 2026 are truly unseen. Earlier bugs found and fixed: benchmark averaging (log vs simple),
ETFs counted as stocks, sector-list survivor leak, 893 unadjusted split/bonus days.

## Findings so far (data to 13 Nov 2026)

- **Frenzy days** (volume 3x+ usual, delivery % 15+ points below usual) are followed by
  underperformance vs similar-sized stocks: about -1.35% a month in a portfolio held one
  month, lagging in 86% of months and in every year 2020–2026.
- **Accumulation patterns** (high delivery, flat price) show no reliable edge once
  tested properly.
- An early version of `backtest.py` averaged log returns for the benchmark, which
  understated it by ~2-3% over 60 days and made buy signals look good. Fixed.

Research on past data, not financial advice.

## Very different signals (Nov 2026)

| Idea | Test | Result |
|---|---|---|
| Seasons | Small vs large companies by calendar month, 2016–2026 | Feb: small lagged large 10 of 10 years; Mar 9 of 11. Apr: market up 10 of 11, small ahead 10 of 11 (Indian fiscal year-end selling, then relief). A single stock's own past same-month returns: nothing |
| Western customers → Indian suppliers (`supplier_chain.py`) | 86 Western firms; each Indian stock linked to its closest co-mover over the past 36 months; partner's move this month vs the stock next month | No edge overall (rank corr +0.007, t 1.1). Auto partners +0.038 (t 2.0) is a hint only |
| US sector moves overnight (`us_spillover.py`) | Learned beta to 14 US sector funds; previous US session → next Indian day, 2,417 days | Real but priced in at the open: opening-gap rank corr +0.025 (t 11.5) for the largest firms, +0.005 for small. Tradable open→close part: top-minus-bottom fifth +0.055%/day (largest), +0.005%/day (small) — below trading costs |
| Major industry trends (`industry_trends.py`) | Theme = 20 closest co-movers, point-in-time | Theme trend alone weak (t 1.0). Leader in a hot theme +0.024 (t 2.3), mostly the stock's own trend already in the model. Laggard in a hot theme −0.016 (t −3.0) is a trap, but as a red flag on the money signal it helped to 2021 and hurt after (+13.0 → +13.4%/yr; after 2021 11.6 → 11.0): not adopted |
