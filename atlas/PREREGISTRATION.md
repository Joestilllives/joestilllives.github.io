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
