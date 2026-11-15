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
| `backtest.py` | Event-driven daily loop with an execution lag (default: decide at the close, trade at the next close). Costs are charged on every trade. |
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

## Real-data backtest: 5 ETFs, Nov 2006 – Aug 2026

Universe: SPY, TLT, IEF, GLD, DBC (dividend-adjusted, built by
`python scripts/build_etf5.py data/etf5.csv`; then
`python -m atlas validate --config config/etf5.toml`). The default config
ran **unchanged**. Nothing was tuned on this data.

| | CAGR | Vol | Sharpe | Max DD |
| --- | --- | --- | --- | --- |
| **Atlas** | 5.7% | 11.7% | 0.53 | −27% |
| Atlas walk-forward out-of-sample | 5.3% | 10.5% | 0.54 | −25% |
| SPY buy & hold | 11.1% | 19.5% | 0.64 | −55% |
| 60/40 SPY/IEF | 8.1% | 11.0% | 0.77 | −33% |
| Equal-weight 5 ETFs | 6.5% | 8.5% | 0.79 | −22% |
| 50% Atlas + 50% 60/40 | 7.4% | 7.4% | 1.00 | −13% |

The gate **passes**: no look-ahead, Deflated Sharpe 97%, Sharpe 0.50 at
3× costs, bootstrap 90% CI on Sharpe [0.12, 0.94].

How to read this: on its own, Atlas earned less than simply holding the
ETFs. Its value is as a **diversifier**: daily correlation with SPY is −0.19,
and it made +24% in 2008 and +15% in 2022, years when stocks and 60/40 fell
hard. Trend and time-series momentum carry the result (Sharpe 0.51 and 0.67
alone). Cross-sectional momentum and low-vol lose money on a 5-asset universe
and should be dropped for it, but dropping them after seeing these results
is overfitting until it is confirmed on other data. Caveats: only 5 assets;
interest on cash and margin is not in the simulation (a rough estimate at
1.6% T-bills puts its effect at about zero); some IEF dividends are missing
in 2005–09; the 50/50 blend was chosen after the fact.

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
