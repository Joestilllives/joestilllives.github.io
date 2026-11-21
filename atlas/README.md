# Atlas

An end-to-end, automated, systematic multi-asset trading framework. It takes
you from raw prices to orders at a broker, and puts every result through
validation before any money is risked.

Dependencies: `numpy` and `pandas`. That's all.

```
 data ─► signals ─► blend ─► regime ─► portfolio ─► risk ─► buffer/costs ─► orders ─► broker
  │        │          │         │           │          │           │            │
 clean   5 alphas   static/   vol shock,  risk-budget  drawdown    sqrt-impact  pre-trade checks,
 + QC    (+carry)   IC-tilt   corr spike  or mean-var  ladder,     cost model,  throttle, kill
                                          vol target   kill, vol   no-trade     switch, journal
                                                       breach      band
```

The backtester and the live loop call **the same functions**, so what you
validated is what trades.

## Quick start

```bash
cd atlas
python -m atlas backtest            # simulate + reports/tearsheet.html
python -m atlas validate            # walk-forward, deflated Sharpe, stress tests -> PASS/FAIL gate
python -m atlas rebalance           # one paper-trading cycle, dry run
python -m atlas rebalance --execute # send the orders to the paper broker
python -m unittest discover -s tests -t .
```

All settings live in [`config/default.toml`](config/default.toml). Copy the
file and pass `--config my.toml`.

## The modules

| Module | What it does |
| --- | --- |
| `data.py` | CSV / Yahoo loaders, a synthetic market (fat tails, vol regimes, factor correlation, drift regimes, staggered listings), and defensive cleaning (spikes, stale gaps, short histories). |
| `signals.py` | **Trend** (multi-speed EWMA crossover), **time-series momentum** (12-1), **cross-sectional momentum**, **short-term reversal**, **low-volatility**, **carry** (needs your carry data). Each signal is risk-normalised so 1.0 means "normal conviction", capped at ±2. Signals are blended with static weights, or with adaptive weights tilted toward signals whose recent out-of-sample IC is positive (shrunk 50% toward the prior). |
| `regime.py` | A risk-appetite multiplier: cuts exposure when short-term vol spikes against its 2-year level or when average cross-asset correlation jumps (diversification is disappearing). Optional breadth filter for long-only books. |
| `portfolio.py` | Recursive risk model: fast EWMA vols, slow EWMA correlations shrunk toward the average. **Risk-budget** sizing (forecast × target vol ÷ instrument vol × diversification multiplier) or **mean-variance** (ridge-regularised Σ⁻¹μ). Constraints: per-asset cap, gross and net caps, long-only, ex-ante vol ceiling. |
| `risk.py` | **Drawdown ladder**: from a 10% drawdown, exposure scales down linearly; at 25% the book goes flat for 21 days, then re-arms at half size and grows back. **Lifetime kill** at 35% below the all-time high: permanent until a human resets it. **Vol-breach** cut when realised vol exceeds 2× target. **Pre-trade checks** (NaN, caps, max order size, a `KILL` file). |
| `execution.py` | Costs: commission + half-spread + square-root market impact. A no-trade buffer that trades only to the band edge (roughly halves turnover). Share-rounded order generation. `PaperBroker` (file-backed) and `AlpacaBroker` (stdlib REST, paper endpoint by default). |
| `backtest.py` | Event-driven daily loop with an execution lag (default: decide at the close, trade at the next close). Costs are charged on every trade, and financing is charged daily (cash interest, margin interest, short fees). |
| `metrics.py` | CAGR, vol, Sharpe, Sortino, Calmar, max drawdown, VaR/CVaR, hit rates, **Probabilistic Sharpe**, and the **Deflated Sharpe**, which corrects for how many variants you tried. |
| `validation.py` | Walk-forward selection (choose on the past, trade the unseen next year), stationary block-bootstrap Sharpe CI, 1×/2×/3× cost stress, per-signal ablation, and a **look-ahead probe** (scramble the future and check that past weights don't move). |
| `live.py` | One daily cycle: freshness check → model → account equity → risk controls → targets → buffer → throttle → checks → submit → persist state → append to `state/journal.jsonl`. Re-running on the same day is safe. |
| `report.py` | A self-contained HTML tearsheet (inline SVG, light and dark). |

## The deployment gate

`validate` exits non-zero unless **all** of these hold:

1. The look-ahead probe passes.
2. The walk-forward out-of-sample Deflated Sharpe is above 95%.
3. Sharpe is still positive at 3× the assumed costs.

The framework is built to block unproven strategies from trading, and it
does. On the default synthetic market (a weak, noisy trend edge) the gate
**FAILS**: OOS Sharpe ≈ 0.40 but DSR ≈ 76%, and the full-history run loses
money and trips the 35% lifetime kill. With `trend_strength = 1.0` (a real
edge) the default blend makes Sharpe about 0.7–1.2 across seeds and DSR rounds
to 100%. With `trend_strength = 0` (pure noise) the
unit tests require the gate to fail on every seed. A system that reports good
results on noise is broken.

## Real-data results (default config, nothing tuned on this data)

Financing is in the simulation: idle cash earns the 13-week T-bill rate, and
leverage pays T-bills + 0.5%. Shorts pay 0.5% a year. Sharpe, PSR, DSR and
walk-forward are all measured on **returns above cash**.

| Universe | CAGR | Sharpe above cash | Max DD | OOS DSR | Gate |
| --- | --- | --- | --- | --- | --- |
| 28 ETFs, 2005 – Nov 2026 (`config/etf_broad.toml`, Yahoo) | 3.3% | 0.19 | −30% | 62% | **FAIL** |
| 5 ETFs, 2006 – Aug 2026 (`config/etf5.toml`) | 4.7% | 0.33 | −25% | 91% | **FAIL** |
| SPY buy & hold, 2005 – 2026 | 11.0% | 0.55 | −55% | | |
| 60/40 SPY/IEF, 2005 – 2026 | 8.1% | 0.62 | −33% | | |

What the tests say:

- **Before financing was modelled, both universes passed the gate.** The
  28-ETF book holds ~1.65× long and ~0.5× short on average. Paying for that
  leverage costs ~1.7% a year, which turns a Sharpe of 0.49 into 0.19.
  Leveraged ETFs are an expensive way to run a diversified risk-parity trend
  book. Futures carry the leverage almost for free, which is why CTAs use them.
- **Trend and time-series momentum are real but modest** (Sharpe above cash
  0.3–0.5 on both universes). **Low-vol loses money in every test** (synthetic,
  5 ETFs, 28 ETFs). Cross-sectional momentum is weak.
- **It hedges.** Daily correlation with SPY is about 0; it made money in 2008 and 2022.
- **The drawdown ladder is path-dependent.** On the 5-ETF set, switching it
  off raises CAGR from 4.7% to 5.7% and the max drawdown from 25% to 33%.
  Small changes in daily P&L shift when it triggers.
- Survivorship: the ETF lists contain funds that still exist today.

## India: Atlas v2-IN (current target market)

The same pre-registration discipline: rules and criteria were committed before
any strategy ran on Indian data ([`PREREGISTRATION.md`](PREREGISTRATION.md),
India section; [`config/india_v2.toml`](config/india_v2.toml)). India forces
three changes: **long-only** (no overnight shorts in the cash segment),
**6% cash rate**, and Indian costs. The universe is 15 NSE ETFs
([`atlas/india.py`](atlas/india.py)) with NSE index history before listing.
Yahoo's Indian data has mishandled unit splits (−90% … +900%, Dec 2019) and
bad prints. These are removed by the cleaner.

`python scripts/india_holdout.py`, Jun 2009 – Nov 2026:

| | CAGR | Vol | Sharpe above 6% cash | Max DD |
| --- | --- | --- | --- | --- |
| **v2-IN** | **12.4%** | 8.8% | **0.68** | **−13%** |
| Nifty 50 (NIFTYBEES) | 11.6% | 16.0% | 0.39 | −36% |
| 80% Nifty + 20% v2-IN | 11.9% | 14.0% | 0.45 | −31% |

**Tier 1 PASS and Tier 2 statistical test PASS** (Deflated Sharpe 0.959, just
over 0.95). Still Sharpe 0.57 at 3× costs. Profits are spread across all 15
ETFs, led by gold, Nasdaq 100 and IT. The ten best days give only 9% of the gain.

Before real money:
- **Taxes are not modelled.** At 3.6× turnover most gains are short-term
  (20% STCG), while a Nifty holder defers tax. A rough estimate puts v2-IN at
  ~10% a year after tax against ~11% for buy-and-hold Nifty. The
  advantage after tax is the much lower risk, not higher return.
- The 6% cash rate is above what a liquid ETF actually pays (~4% net), so
  CAGR is overstated by roughly 0.5% a year. Sharpe above cash is not affected.
- Index proxies before ETF listing exclude dividends. The ETFs are survivors.
- A Deflated Sharpe of 0.959 passes by a small margin.
- **3 months of paper trading must track the backtest** (`paper_india/`,
  `python scripts/paper_report.py config/india_v2.toml`).

Daily run after NSE publishes its bhavcopy (~18:00 IST; the run refuses to
trade until the official closes are out and match):
`python -m atlas rebalance --config config/india_v2.toml --execute`.

### Audit (2026-11-21)

| Check | Result |
| --- | --- |
| Independent rebuild of the equity curve from weights, returns, costs, financing and tax | Matches the engine to 1e-15. The P&L accounting is correct. |
| Data cleaning | **Bias found and fixed.** The cleaner erased any move that round-tripped within 5 days, including real crashes (Nifty −13% on 23 Mar 2020, −12% on 24 Oct 2008). Now only split glitches and one-day bad quotes on ETF prices are masked; exchange index data never is. |
| No-leverage rule | **Bug found and fixed.** Partial rebalancing let the long-only book reach 110% of capital on 17% of days, which a delivery account can't do. Buys are now trimmed at execution. |
| Universe selection | Without the foreign and precious-metal ETFs, Sharpe above cash falls from 0.65 to 0.42–0.55. The edge survives, but the realistic forward estimate is ~0.4–0.5, not 0.68. |
| v2-IN after all fixes | Sharpe above cash 0.68, max DD −13%, both tiers still pass (DSR 0.956). |

### Framework upgrades for live trading in India

| Added | What it does | What it found |
| --- | --- | --- |
| `atlas/tax.py` | FIFO tax lots, Indian STCG/LTCG/slab rules by asset class, loss set-off and carry-forward, ₹1.25 lakh exemption, tax paid each 31 March (`[tax] enabled = true`) | v2-IN **10.3% a year after tax** vs Nifty buy-and-hold **10.9%**. Tax costs v2-IN 2.1% a year. After tax its edge is lower risk (−13% vs −36% worst loss), not return. |
| `atlas/crosscheck.py` | Before any order, last prices must match NSE's official bhavcopy within 0.5%, or nothing trades. Fails closed if NSE is unreachable. | Caught on first use that the India data builder sent index-level prices (e.g. PHARMABEES ₹623 vs real ₹29.32). Order quantities would have been wrong. Fixed; all 15 now match exactly. |
| `atlas/monitor.py`, `scripts/paper_report.py` | Bootstrapped expectation bands from the backtest and paper-vs-backtest tracking | Pre-committed stop rules for v2-IN: after 3 months, WARNING below −4.0%, STOP below −6.6%. After 1 year: −2.4% / −8.2%. |
| `scripts/robustness.py` | One-at-a-time parameter perturbation (diagnostic, never used to pick settings) | Sharpe above cash 0.61–0.75 across 15 perturbations (0.65 as validated), all positive: a plateau, not a spike. The regime overlay and drawdown ladder never triggered in India. |
| `ZerodhaBroker` | Kite Connect v3: CNC delivery orders, after-market orders after hours (fills at the next open, like the one-day lag), sells before buys | Untested against a real account. Kite tokens need a daily manual login. |
| `buffer_floor` | Configurable minimum no-trade band (v2/v2-IN keep the validated 0.25) | A v3 candidate. Changing it needs a fresh test. |

## Atlas v2 (US): pre-registered holdout test → paper trading

Rules, universes and pass criteria were committed **before** the holdout run
([`PREREGISTRATION.md`](PREREGISTRATION.md), [`config/v2.toml`](config/v2.toml)):
no leverage, trend + time-series momentum only, static weights, 10% target
vol, intended as a 20% sleeve next to 60/40.

| Holdout (never used before) | CAGR | Sharpe above cash | Max DD | Corr. to SPY |
| --- | --- | --- | --- | --- |
| A: 35 new ETFs, 2005 – Nov 2026 | 3.9% | 0.42 | −10% | 0.33 |
| B: 36 ETFs, unseen years 1999 – 2004 | 4.9% | 0.27 | −10% | |
| 60/40 SPY/IEF, 2005 – 2026 | 8.2% | 0.62 | −31% | |
| **80% 60/40 + 20% v2 (on A)** | 7.4% | **0.64** | **−24%** | |

**Tier 1 PASS** (all four criteria) → paper trading. **Tier 2 FAIL** so far
(Deflated Sharpe 86% < 95%): no real money yet. Holdout A shares the same calendar
years as the earlier tests, so it is not fully independent.

Paper trading runs on the 28-ETF universe after each US close:
`python -m atlas rebalance --config config/v2.toml --execute`. The record is
committed in `paper/`. Orders decided at one close fill at the next run's
close, as in the backtest. Cash earns T-bills, and shorts pay a fee.
`python scripts/paper_report.py` compares paper with the backtest (target:
correlation > 0.9, tracking error < 3%, over ≥ 63 trading days).

Known v2 weakness, for a future v3 (needs new holdout data): the no-trade buffer
has an absolute floor of 2.5% of equity, which is large next to v2's small,
unlevered positions. Live deployment therefore starts from the backtest's
current book rather than building up from flat.

## Going live: checklist

1. **Real data.** Set `[data] source = "csv"` (or `"yfinance"` with a
   diversified ETF / futures list; an example list is in the config). Use
   total-return-adjusted prices.
2. **Run `validate`** on that data. If it fails, do not deploy. Change the
   *idea*, not the parameters, or the DSR will rightly punish you.
3. **Realistic costs.** Set `commission_bps`, `half_spread_bps` and `adv_usd` for
   your instruments and size.
4. **Paper trade for at least 3 months**: schedule
   `python -m atlas rebalance --execute` after each close, then compare the journal with
   the backtest over the same dates. Live-vs-backtest tracking error is the
   most important number you will look at.
5. **Go live with small size**: `[live] broker = "alpaca"`, export
   `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY`, and only then
   `ALPACA_BASE_URL=https://api.alpaca.markets`. Scale up slowly.
6. **Operations**: `touch KILL` stops all trading immediately. A lifetime-kill
   trip requires a human to edit `state/risk_state.json`.

Scheduling example (cron, 22:15 UTC on weekdays):

```
15 22 * * 1-5  cd /path/to/atlas && python -m atlas rebalance --execute >> state/cron.log 2>&1
```

To add a broker, subclass `execution.Broker` (`equity`, `positions`,
`submit`). To add a signal, write a causal function `prices -> forecasts`,
register it in `signals.REGISTRY`, and give it a weight in the config. The
look-ahead test then checks it automatically.

## Honest limits

- No framework guarantees profits. Atlas is designed to size risk well,
  survive bad periods, and stop you from deploying overfit ideas. The
  edge has to come from the signals, and the classic ones here are well known
  and crowded.
- Daily bars only. It does not model intraday execution, borrow costs for
  shorts, futures rolls, FX translation, taxes, or corporate actions beyond
  adjusted prices.
- The `AlpacaBroker` adapter follows Alpaca's public REST API but has not been
  run against a live account in this repository. Prove it on the paper
  endpoint first.
- This is software, not investment advice.
