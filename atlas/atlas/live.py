"""Live / paper trading cycle. Run once per day after the close (cron, systemd
timer, GitHub Actions, Airflow...). Idempotent per day and fully journaled.

Cycle:
  data -> freshness check -> forecasts -> risk model -> regime ->
  account equity -> drawdown/vol controls -> target weights -> buffer ->
  orders -> pre-trade checks -> submit (or dry-run) -> persist state + journal

It reuses exactly the same functions as the backtester, so live behaviour
matches what was tested.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import make_risk_model
from .data import get_rates
from .execution import Broker, Order, PaperBroker, apply_buffer, make_orders
from .portfolio import ex_ante_vol, target_weights
from .regime import regime_multiplier
from .risk import RiskManager, RiskState, pre_trade_checks
from .signals import build_forecasts


class StaleDataError(RuntimeError):
    pass


def rebalance(prices: pd.DataFrame, cfg: dict, broker: Broker, dry_run: bool = True,
              state_dir: str | Path = "state", today: date | None = None) -> dict:
    pcfg, rcfg, ecfg = cfg.get("portfolio", {}), cfg.get("risk", {}), cfg.get("execution", {})
    lcfg = cfg.get("live", {})
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)

    # 1) Data freshness: never trade on stale prices.
    max_stale = lcfg.get("max_staleness_days")
    if max_stale is not None:
        age = ((today or date.today()) - prices.index[-1].date()).days
        if age > max_stale:
            raise StaleDataError(f"latest price is {age} days old (limit {max_stale})")

    symbols = list(prices.columns)
    last_px = prices.iloc[-1].to_numpy()

    # 1b) Second-source check: official exchange closes must match (fails closed).
    crosscheck = None
    if lcfg.get("crosscheck") == "nse_bhavcopy":
        from .crosscheck import verify_nse
        crosscheck = verify_nse(prices.iloc[-1], prices.index[-1], lcfg.get("crosscheck_tol", 0.005))
    accrued = 0.0
    if isinstance(broker, PaperBroker):
        # Interest accrues on the book held since the last run, at the old marks.
        fcfg = cfg.get("financing", {})
        rate = float(get_rates(cfg, prices.index).iloc[-1])
        accrued = broker.accrue_financing(rate, str(prices.index[-1].date()),
                                          fcfg.get("short_fee_bps", 50) / 1e4,
                                          fcfg.get("borrow_spread_bps", 50) / 1e4)
        broker.mark(dict(zip(symbols, last_px)))

    # Paper fidelity with the backtest's lag: orders decided at the previous
    # run's close fill now, at today's close. Same-day re-runs never fill.
    as_of = str(prices.index[-1].date())
    lagged_paper = isinstance(broker, PaperBroker) and ecfg.get("lag", 1) >= 1
    prior_fills = []
    if lagged_paper and not dry_run:
        pend = broker.state.get("pending", {"as_of": "", "orders": []})
        if pend["orders"] and pend["as_of"] < as_of:
            px_map = dict(zip(symbols, last_px))
            prior_fills = broker.submit([Order(o["symbol"], o["qty"], float(px_map[o["symbol"]]))
                                         for o in pend["orders"] if np.isfinite(px_map.get(o["symbol"], np.nan))])
            broker.state["pending"] = {"as_of": "", "orders": []}

    # 2) Model state rebuilt from history (deterministic, no hidden drift).
    forecasts, _ = build_forecasts(prices, cfg)
    regime = regime_multiplier(prices, cfg)
    model = make_risk_model(len(symbols), cfg)
    for row in np.log(prices).diff().to_numpy():
        model.update(row)

    # 3) Account + risk controls with persisted state.
    equity = broker.equity()
    rs_path = state_dir / "risk_state.json"
    rm = RiskManager(rcfg, pcfg.get("target_vol", 0.12), RiskState.load(rs_path))
    if rm.state.last_as_of != as_of:  # idempotent: one risk update per trading day
        prev = rm.state.last_equity
        rm.on_equity(equity, equity / prev - 1 if prev > 0 else None)
        rm.state.last_equity = equity
        rm.state.last_as_of = as_of
    scale = rm.exposure_scale(equity)

    target = target_weights(forecasts.iloc[-1].to_numpy(), model, pcfg) * float(regime.iloc[-1]) * scale
    target[~np.isfinite(last_px)] = 0.0

    pos = broker.positions()
    cur_qty = np.array([pos.get(s, 0.0) for s in symbols])
    cur_w = np.nan_to_num(cur_qty * last_px / equity) if equity > 0 else np.zeros(len(symbols))
    seeded = False
    if not np.any(cur_qty) and lcfg.get("seed_from_backtest", True):
        # First deployment: buy the book the backtest holds today, so live
        # follows the validated path. (Building up through the no-trade buffer
        # from flat would open only part of a low-gross book.)
        from .backtest import run_backtest
        new_w = run_backtest(prices, cfg).weights.iloc[-1].to_numpy() * scale
        new_w[~np.isfinite(last_px)] = 0.0
        seeded = True
    else:
        new_w = apply_buffer(cur_w, target, ecfg.get("buffer", 0.1), ecfg.get("buffer_floor", 0.25))
    # Throttle: no single trade above max_order_frac of equity per day. Large
    # moves (first deployment, regime flips) are worked over several days.
    lim = rcfg.get("max_order_frac", 0.25) * 0.98
    dw = new_w - cur_w
    throttled = [s for s, d in zip(symbols, dw) if abs(d) > lim]
    new_w = cur_w + np.clip(dw, -lim, lim)
    orders = make_orders(symbols, cur_qty, new_w, last_px, equity,
                         min_notional=lcfg.get("min_order_notional", 100.0),
                         fractional=lcfg.get("fractional", False))

    pre_trade_checks(new_w, np.array([o.notional for o in orders]), equity, pcfg, rcfg)

    if dry_run:
        fills = []
    elif lagged_paper:
        broker.state["pending"] = {"as_of": as_of, "orders": [
            {"symbol": o.symbol, "qty": o.qty} for o in orders]}
        fills = prior_fills
    else:
        fills = broker.submit(orders)
    if not dry_run:
        rm.state.save(rs_path)
        if isinstance(broker, PaperBroker):
            broker.save()

    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "dry_run": dry_run,
        "equity": equity,
        "financing_accrued": accrued,
        "exposure_scale": scale,
        "killed": rm.state.killed,
        "regime": float(regime.iloc[-1]),
        "ex_ante_vol": ex_ante_vol(new_w, model.covariance()),
        "gross": float(np.abs(new_w).sum()),
        "throttled": throttled,
        "seeded_from_backtest": seeded,
        "crosscheck_max_dev": max((v["dev"] for v in crosscheck.values()), default=None) if crosscheck else None,
        "targets": {s: round(float(w), 5) for s, w in zip(symbols, new_w) if abs(w) > 1e-6},
        "orders": [{"symbol": o.symbol, "qty": o.qty, "price": o.price} for o in orders],
        "fills": fills,
    }
    with open(state_dir / "journal.jsonl", "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
