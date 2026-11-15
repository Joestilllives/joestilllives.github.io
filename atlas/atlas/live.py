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
from .execution import Broker, PaperBroker, apply_buffer, make_orders
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
    if isinstance(broker, PaperBroker):
        broker.mark(dict(zip(symbols, last_px)))

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
    as_of = str(prices.index[-1].date())
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
    new_w = apply_buffer(cur_w, target, ecfg.get("buffer", 0.1))
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

    fills = [] if dry_run else broker.submit(orders)
    if not dry_run:
        rm.state.save(rs_path)

    record = {
        "time": datetime.now(timezone.utc).isoformat(),
        "as_of": as_of,
        "dry_run": dry_run,
        "equity": equity,
        "exposure_scale": scale,
        "killed": rm.state.killed,
        "regime": float(regime.iloc[-1]),
        "ex_ante_vol": ex_ante_vol(new_w, model.covariance()),
        "gross": float(np.abs(new_w).sum()),
        "throttled": throttled,
        "targets": {s: round(float(w), 5) for s, w in zip(symbols, new_w) if abs(w) > 1e-6},
        "orders": [{"symbol": o.symbol, "qty": o.qty, "price": o.price} for o in orders],
        "fills": fills,
    }
    with open(state_dir / "journal.jsonl", "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return record
