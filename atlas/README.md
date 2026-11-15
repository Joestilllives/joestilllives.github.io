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
