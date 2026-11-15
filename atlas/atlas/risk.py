"""Risk management: the layer that keeps the fund alive.

Survival first. A strategy with a positive edge only compounds if it never
takes a loss it cannot come back from, so every target passes through:

  1. Drawdown control - exposure scales down linearly between a soft and a
     hard drawdown limit; at the hard limit the book goes flat for a cooldown
     period, then re-arms at reduced size (peak resets to current equity).
  2. Realised-vol breach - if the strategy's own realised vol runs far above
     target (model is wrong), cut exposure proportionally.
  3. Pre-trade checks - NaN/inf, per-asset caps, gross caps, max single
     order notional, kill-switch file. Failures block trading, never "fix"
     silently.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class RiskState:
    peak: float = 0.0
    halted_days_left: int = 0
    rearm_scale: float = 1.0
    last_equity: float = 0.0
    hwm: float = 0.0
    killed: bool = False
    last_as_of: str = ""
    recent_returns: list = field(default_factory=list)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls, path: str | Path) -> "RiskState":
        p = Path(path)
        return cls(**json.loads(p.read_text())) if p.exists() else cls()


class RiskManager:
    def __init__(self, rcfg: dict, target_vol: float, state: RiskState | None = None):
        self.cfg = rcfg
        self.target_vol = target_vol
        self.state = state or RiskState()

    def on_equity(self, equity: float, daily_return: float | None = None) -> None:
        s = self.state
        s.peak = max(s.peak, equity)
        s.hwm = max(s.hwm, equity)
        if s.hwm > 0 and 1.0 - equity / s.hwm >= self.cfg.get("dd_kill", 0.35):
            s.killed = True
        if daily_return is not None and np.isfinite(daily_return):
            s.recent_returns.append(float(daily_return))
            s.recent_returns = s.recent_returns[-self.cfg.get("vol_window", 21):]
        if s.halted_days_left > 0:
            s.halted_days_left -= 1
            if s.halted_days_left == 0:
                s.peak = equity  # re-arm from here
                s.rearm_scale = self.cfg.get("rearm_scale", 0.5)

    def exposure_scale(self, equity: float) -> float:
        s, c = self.state, self.cfg
        if s.killed or s.halted_days_left > 0:
            return 0.0
        dd = 1.0 - equity / s.peak if s.peak > 0 else 0.0
        soft, hard = c.get("dd_soft", 0.10), c.get("dd_hard", 0.25)
        if dd >= hard:
            s.halted_days_left = c.get("halt_days", 21)
            return 0.0
        dd_scale = 1.0 if dd <= soft else 1.0 - (dd - soft) / (hard - soft) * (1 - c.get("dd_min_scale", 0.3))

        vol_scale = 1.0
        if len(s.recent_returns) >= 10:
            realised = float(np.std(s.recent_returns, ddof=1) * np.sqrt(252))
            breach = self.target_vol * c.get("vol_breach_mult", 2.0)
            if realised > breach:
                vol_scale = breach / realised

        # Re-armed books grow back to full size gradually (5%/day).
        scale = dd_scale * vol_scale * s.rearm_scale
        s.rearm_scale = min(1.0, s.rearm_scale + 0.05)
        return float(scale)


class PreTradeCheckError(RuntimeError):
    pass


def pre_trade_checks(weights: np.ndarray, orders_notional: np.ndarray, equity: float,
                     pcfg: dict, rcfg: dict) -> None:
    if not np.all(np.isfinite(weights)):
        raise PreTradeCheckError("non-finite target weight")
    cap = pcfg.get("max_weight", 0.5) + 1e-9
    if np.any(np.abs(weights) > cap):
        raise PreTradeCheckError(f"weight above cap {cap}")
    if np.abs(weights).sum() > pcfg.get("max_gross", 3.0) + 1e-6:
        raise PreTradeCheckError("gross leverage above cap")
    max_order = rcfg.get("max_order_frac", 0.25) * equity
    if np.any(np.abs(orders_notional) > max_order):
        raise PreTradeCheckError(f"single order above {rcfg.get('max_order_frac', 0.25):.0%} of equity")
    ks = rcfg.get("kill_switch_file", "KILL")
    if ks and Path(ks).exists():
        raise PreTradeCheckError(f"kill switch file '{ks}' present - trading disabled")
