"""Execution: cost model, no-trade buffer, order generation, brokers.

Costs are what turn paper alpha into real losses. The model charges
  commission + half-spread  (linear in traded notional)
  + market impact            (square-root law: k * sigma * sqrt(Q / ADV) per $)
and the buffer suppresses small rebalances whose expected benefit is below
their cost.
"""
from __future__ import annotations

import json
import os
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


@dataclass
class CostModel:
    commission_bps: float = 0.5
    half_spread_bps: float = 1.0
    impact_k: float = 0.5
    adv_usd: float = 5e8  # default average daily dollar volume per instrument

    def cost_frac(self, dw: np.ndarray, daily_vol: np.ndarray, equity: float) -> float:
        """Total cost as a fraction of equity for weight changes `dw`."""
        a = np.abs(np.nan_to_num(dw))
        linear = (self.commission_bps + self.half_spread_bps) / 1e4 * a.sum()
        notional = a * equity
        impact = self.impact_k * np.nan_to_num(daily_vol) * np.sqrt(notional / self.adv_usd) * a
        return float(linear + impact.sum())


def apply_buffer(current: np.ndarray, target: np.ndarray, buffer: float) -> np.ndarray:
    """Trade only when outside a +/- buffer band, and then only to the band edge.

    Buffer is in weight units, scaled by |target| so big positions get wider
    bands (absolute floor 0.25*buffer). This roughly halves turnover for a
    small loss in tracking.
    """
    if buffer <= 0:
        return target.copy()
    band = np.maximum(buffer * np.abs(target), buffer * 0.25)
    diff = target - current
    out = current.copy()
    hi = diff > band
    lo = diff < -band
    out[hi] = target[hi] - band[hi]
    out[lo] = target[lo] + band[lo]
    # Always close positions fully when the target is exactly flat.
    flat = (target == 0) & (current != 0) & (np.abs(current) > band)
    out[flat] = 0.0
    return out


@dataclass
class Order:
    symbol: str
    qty: float          # signed shares
    price: float
    @property
    def notional(self) -> float:
        return self.qty * self.price


def make_orders(symbols, current_qty: np.ndarray, target_w: np.ndarray, prices: np.ndarray,
                equity: float, lot: float = 1.0, min_notional: float = 100.0,
                fractional: bool = False) -> list[Order]:
    orders = []
    for s, q0, w, p in zip(symbols, current_qty, target_w, prices):
        if not np.isfinite(p) or p <= 0:
            continue
        q = w * equity / p
        if not fractional:
            q = np.round(q / lot) * lot
        dq = q - q0
        if abs(dq * p) >= min_notional:
            orders.append(Order(s, float(dq), float(p)))
    return orders


# ------------------------------------------------------------------ brokers

class Broker(ABC):
    @abstractmethod
    def equity(self) -> float: ...
    @abstractmethod
    def positions(self) -> dict[str, float]: ...
    @abstractmethod
    def submit(self, orders: list[Order]) -> list[dict]: ...


class PaperBroker(Broker):
    """File-backed simulated account. Fills at the given price +/- slippage."""

    def __init__(self, state_path: str | Path, starting_cash: float = 1_000_000.0,
                 slippage_bps: float = 2.0):
        self.path = Path(state_path)
        self.slip = slippage_bps / 1e4
        if self.path.exists():
            self.state = json.loads(self.path.read_text())
        else:
            self.state = {"cash": starting_cash, "positions": {}, "last_prices": {}}

    def mark(self, prices: dict[str, float]) -> None:
        self.state["last_prices"].update({k: float(v) for k, v in prices.items() if np.isfinite(v)})

    def equity(self) -> float:
        lp = self.state["last_prices"]
        return self.state["cash"] + sum(q * lp.get(s, 0.0) for s, q in self.state["positions"].items())

    def positions(self) -> dict[str, float]:
        return dict(self.state["positions"])

    def submit(self, orders: list[Order]) -> list[dict]:
        fills = []
        for o in orders:
            px = o.price * (1 + self.slip * np.sign(o.qty))
            self.state["cash"] -= o.qty * px
            self.state["positions"][o.symbol] = self.state["positions"].get(o.symbol, 0.0) + o.qty
            fills.append({"symbol": o.symbol, "qty": o.qty, "price": px,
                          "time": datetime.now(timezone.utc).isoformat()})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.state, indent=2))
        return fills


class AlpacaBroker(Broker):
    """Minimal Alpaca REST adapter (stdlib only). Defaults to the PAPER endpoint.

    Keys come from ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY. Set
    ALPACA_BASE_URL=https://api.alpaca.markets only when you mean it.
    """

    def __init__(self):
        self.base = os.environ.get("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")
        self.headers = {
            "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
            "Content-Type": "application/json",
        }

    def _req(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, headers=self.headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read() or b"null")

    def equity(self) -> float:
        return float(self._req("GET", "/v2/account")["equity"])

    def positions(self) -> dict[str, float]:
        return {p["symbol"]: float(p["qty"]) for p in self._req("GET", "/v2/positions")}

    def submit(self, orders: list[Order]) -> list[dict]:
        out = []
        for o in orders:
            out.append(self._req("POST", "/v2/orders", {
                "symbol": o.symbol, "qty": str(abs(round(o.qty, 6))),
                "side": "buy" if o.qty > 0 else "sell",
                "type": "market", "time_in_force": "day",
            }))
        return out
