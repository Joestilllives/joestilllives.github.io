# Atlas v2: pre-registration

Committed **before** the holdout data was downloaded or run. The git history
is the timestamp. Nothing in `config/v2.toml`, the universes or the criteria below
may change after the holdout run. If v2 fails, it fails. A v3 needs new
holdout data.

## Why v2 looks like this (lessons from data already used)

Tests on synthetic data, 5 ETFs (2006–2026) and 28 ETFs (2005–2026):

1. Leverage through ETFs costs ~1.7%/yr in financing and wiped out most of the edge. → **No leverage**: longs + shorts ≤ 100% of capital.
2. Trend and time-series momentum were positive everywhere (Sharpe above cash 0.3–0.5). Low-vol lost money everywhere; cross-sectional momentum was weak or negative. → **Only trend (0.6) and time-series momentum (0.4)**.
3. Adaptive weighting adds estimation noise. → **Static weights**.
4. Without leverage, 12% vol is not reachable on a diversified book. → **Target vol 10%**, max 25% in any one instrument.

Everything else (risk model, regime overlay, drawdown ladder, costs,
financing, lag) is unchanged from `config/default.toml`.

## Intended use

A **20% sleeve** next to a 60/40 portfolio, as a crisis hedge. Not a standalone
fund.

## Holdout data (never used before)

- **A: new instruments, 2005 – Nov 2026.** 35 ETFs: 9 US sectors, 12 single
  countries, 5 bond funds, 4 commodities, 4 currencies, international real
  estate. None of them is in the earlier tests, and none is a near-duplicate of
  one that is (e.g. IAU/GLD). Caveat: same calendar years as the earlier tests,
  so market regimes such as 2008 and 2022 are shared.
- **B: unseen years, 1999 – 2004** (data from 1998 for warm-up). The 36 ETFs
  that existed then, mostly equities. Short and equity-heavy, so it is secondary.

Source: Yahoo Finance adjusted closes. Cash rate: 13-week T-bill (^IRX).

## Criteria

**Tier 1: proceed to paper trading** (all must hold):

- P1. On A, 80% 60/40 (SPY/IEF) + 20% v2 has a higher Sharpe above cash than 60/40 alone.
- P2. On A, that blend's max drawdown is shallower than 60/40's.
- P3. On A, v2 alone has a positive Sharpe above cash at 3× assumed costs.
- S1. On B, v2 alone has a positive Sharpe above cash.

**Tier 2: eligible for real money** (in addition to Tier 1):

- On A, v2's Deflated Sharpe (above cash, 3 trials) > 95%.
- 3 months of paper trading whose daily returns track the backtest.

If Tier 1 fails: no paper trading of v2 and no tweaking v2 on this data.

---

# India: Atlas v2-IN (pre-registered 2026-11-15, before any strategy run on Indian data)

The user moved the target market from the US to India. No Indian price data
had been used in any test, so the whole Indian history is out of sample.
Only data-quality checks were run before this was written: listing dates,
volumes, bad prints and the cash-rate source. No returns of any strategy or
signal were looked at.

## Rules: v2 unchanged, except for what India forces

`config/india_v2.toml`: trend 0.6 + time-series momentum 0.4, static
weights, 10% target vol, ≤25% per ETF, no leverage. India-specific changes,
decided before testing:

- **Long-only**: retail investors can't hold overnight shorts in the NSE cash segment. Downtrending assets go to cash.
- **Cash earns 6%** (about the average 91-day T-bill since 2009). Sharpe is measured above the same 6%.
- **Indian costs**: 2 bps (stamp duty, STT, exchange, SEBI, GST, DP charges) + 10 bps half-spread + impact against ₹5 crore/day traded value.
- **Universe** (`atlas/india.py`): 15 NSE ETFs covering Nifty 50, Next 50, Bank, PSU Bank, IT, Pharma, Auto, CPSE, gold, silver, Nasdaq 100, US tech, Hang Seng, long gilts and 5-year gilts. NSE price indices stand in before an ETF listed. CONSUMBEES is excluded for erratic quotes and low liquidity.
- **Data cleaning**: bad prints that snap back within 5 days, and mishandled unit splits (−90% … +900%, e.g. 19 Dec 2019), are removed.

Intended use: a **20% sleeve next to a Nifty 50 holding**.

## Criteria (`python scripts/india_holdout.py`)

Tier 1, proceed to paper trading (all must hold):
- P1. 80% NIFTYBEES + 20% v2-IN has a higher Sharpe above cash than NIFTYBEES alone.
- P2. That blend's max drawdown is shallower than NIFTYBEES alone.
- P3. v2-IN alone has a positive Sharpe above cash at 3× assumed costs.

Tier 2, real money: Deflated Sharpe (4 trials) > 95%, and 3 months of paper
trading that tracks the backtest.

Known before running: the history is shorter than the US one (from 2008), so
Tier 2 is hard to reach. Proxy indices exclude dividends (~1–1.5%/yr),
which understates long returns before ETFs listed. Taxes (20% short-term
capital gains) are not modelled.

---

# India stocks: momentum sleeve (pre-registered 2026-11-21, before any strategy run on stock data)

Goal: add a second strategy that is **different** from v2-IN (ETF trend), so the
combination beats either alone. The best-documented equity anomaly in India
is cross-sectional momentum in individual stocks.

## Data (no strategy result has been looked at)

Every NSE EQ-series stock in every daily bhavcopy, 2005-01-03 → 2026-11-20:
4,506 symbols, including delisted, suspended and merged ones (no survivorship
bias). Built by `scripts/build_nse_stocks.py`, processed by `atlas/stocks.py`.
Bonuses and splits are inferred from prices (2,905 detected; e.g. RELIANCE
2017 and 2024, INFY 2018, TCS 2018, HDFCBANK 2019, ITC 2016 verified). Every
rule is chosen so that mistakes hurt the strategy. Delisted holdings exit 30%
below their last price.

## Split

- **Research window: 2006-01-01 → 2016-12-31.** Variants may be compared here.
- **Holdout: 2017-01-01 → 2026-11-20.** Run exactly once, on the single
  variant chosen in research, with the criteria below.

## Fixed design (all variants)

Monthly rebalance, at the month-end close, trading at the next close. Long-only,
fully invested (unless trend-filtered). Universe each month: the 200 most
traded stocks by 63-day median traded value, at least 273 days of history,
price ≥ ₹20. Signal: 12-1 month momentum. Costs: 12 bps fees per side (STT
10 bps + stamp/exchange/SEBI/GST/DP), 8 bps half-spread, square-root impact
on each stock's own traded value. Cash earns 6%.

## Variants compared in research (6, all count as trials)

1. Top 30, equal weight
2. Top 30, ranked on momentum ÷ volatility
3. Top 30, inverse-volatility weights
4. Top 30, equal weight, cash when the stock universe is below its 200-day average
5. Top 20, equal weight
6. Top 50, equal weight

Choice rule: highest research-window Sharpe above cash. If two are within
0.05, take the lower-numbered (simpler) one.

## Holdout criteria (2017-01-01 → 2026-11-20)

Tier 1, paper trading (all must hold):
- S1. Chosen variant's Sharpe above cash > 0 at 2× costs.
- S2. Chosen variant's Sharpe above cash > Nifty 50 (NIFTYBEES).
- S3. 50% chosen variant + 50% v2-IN (daily rebalanced) has a higher Sharpe
  above cash than v2-IN alone.

Tier 2, real money: Deflated Sharpe of the chosen variant > 95%, counting
10 trials project-wide. After-tax results are reported, not gated.
