"""Event-driven daily backtester.

Timeline for each day i (all at the close):
  1. mark the book: P&L = held weights x today's returns; weights drift
  2. update the risk model with today's returns
  3. update the risk manager with today's equity
  4. execute any decision that is now due (decision day + `lag`), paying costs
  5. make today's decision from data up to and including today

With lag=1 (default) a signal computed at Monday's close trades at Tuesday's
close and first earns Wednesday's return. That is conservative; lag=0
assumes you can trade at the same close the signal was computed on.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import get_rates
from .execution import CostModel, apply_buffer
from .metrics import summary
from .portfolio import RiskModel, target_weights
from .regime import regime_multiplier
from .risk import RiskManager
from .signals import build_forecasts


@dataclass
class BacktestResult:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    costs: pd.Series
    turnover: pd.Series
    exposure_scale: pd.Series
    regime: pd.Series
    signals: dict
    rf: pd.Series          # daily cash rate
    financing: pd.Series   # daily financing P&L (fraction of equity)

    @property
    def excess(self) -> pd.Series:
        """Returns above cash: what Sharpe, PSR, DSR and walk-forward judge."""
        return self.returns - self.rf

    @property
    def stats(self) -> dict:
        s = summary(self.returns, self.rf)
        s["financing_ann"] = float(self.financing.mean() * 252)
        s["avg_gross"] = float(self.weights.abs().sum(axis=1).mean())
        s["turnover_ann"] = float(self.turnover.mean() * 252)
        s["cost_drag_ann"] = float(self.costs.mean() * 252)
        return s


def make_risk_model(n: int, cfg: dict) -> RiskModel:
    m = cfg.get("risk_model", {})
    return RiskModel(n, m.get("vol_span", 35), m.get("corr_halflife", 126),
                     m.get("shrink", 0.3), m.get("warmup", 60))


def make_cost_model(cfg: dict) -> CostModel:
    e = cfg.get("execution", {})
    return CostModel(e.get("commission_bps", 0.5), e.get("half_spread_bps", 1.0),
                     e.get("impact_k", 0.5), e.get("adv_usd", 5e8))


def run_backtest(prices: pd.DataFrame, cfg: dict, forecasts: pd.DataFrame | None = None,
                 regime: pd.Series | None = None) -> BacktestResult:
    pcfg, rcfg, ecfg = cfg.get("portfolio", {}), cfg.get("risk", {}), cfg.get("execution", {})
    individual: dict = {}
    if forecasts is None:
        forecasts, individual = build_forecasts(prices, cfg)
    if regime is None:
        regime = regime_multiplier(prices, cfg)

    px = prices.to_numpy()
    simple = prices.pct_change(fill_method=None).to_numpy()
    logr = np.log(prices).diff().to_numpy()
    F = forecasts.reindex_like(prices).to_numpy()
    G = regime.reindex(prices.index).fillna(1.0).to_numpy()
    T, n = px.shape
    fcfg = cfg.get("financing", {})
    rf_s = get_rates(cfg, prices.index) / 252.0
    RF = rf_s.to_numpy()
    borrow_spread = fcfg.get("borrow_spread_bps", 50.0) / 1e4 / 252
    short_fee = fcfg.get("short_fee_bps", 50.0) / 1e4 / 252
    FIN = np.zeros(T)

    model = make_risk_model(n, cfg)
    risk = RiskManager(rcfg, pcfg.get("target_vol", 0.12))
    cost_model = make_cost_model(cfg)
    lag, buf, every = ecfg.get("lag", 1), ecfg.get("buffer", 0.1), ecfg.get("rebalance_every", 1)

    equity = float(cfg.get("capital", 1_000_000.0))
    w = np.zeros(n)
    pending: deque = deque()
    eq = np.empty(T); W = np.zeros((T, n)); C = np.zeros(T); TO = np.zeros(T); S = np.ones(T)

    def execute(target: np.ndarray, i: int) -> None:
        nonlocal w, equity
        new = apply_buffer(w, target, buf)
        dw = new - w
        c = cost_model.cost_frac(dw, model.vol, equity)
        equity *= 1.0 - c
        w = new
        C[i] += c
        TO[i] += np.abs(dw).sum()

    for i in range(T):
        port_r = None
        if i > 0:
            r = np.nan_to_num(simple[i])
            # Financing on the book held overnight: idle cash earns the cash
            # rate, borrowed cash (longs > equity) pays rate + spread, shorts
            # pay a borrow fee (proceeds are posted as collateral).
            cash = 1.0 - w.clip(min=0).sum()
            fin = cash * RF[i] if cash >= 0 else cash * (RF[i] + borrow_spread)
            fin -= (-w.clip(max=0)).sum() * short_fee
            FIN[i] = fin
            port_r = float(w @ r) + fin
            equity *= 1.0 + port_r
            w = w * (1.0 + r) / (1.0 + port_r) if port_r > -1 else np.zeros(n)
        model.update(logr[i])
        risk.on_equity(equity, port_r)

        while pending and pending[0][0] <= i:
            execute(pending.popleft()[1], i)

        if i % every == 0:
            scale = risk.exposure_scale(equity)
            S[i] = scale
            tgt = target_weights(F[i], model, pcfg) * G[i] * scale
            tgt[~np.isfinite(px[i])] = 0.0
            if lag == 0:
                execute(tgt, i)
            else:
                pending.append((i + lag, tgt))
        else:
            S[i] = S[i - 1]
        eq[i] = equity
        W[i] = w

    idx = prices.index
    equity_s = pd.Series(eq, idx, name="equity")
    rets = equity_s.pct_change().fillna(0.0).rename("returns")
    return BacktestResult(
        returns=rets, equity=equity_s,
        weights=pd.DataFrame(W, idx, prices.columns),
        costs=pd.Series(C, idx), turnover=pd.Series(TO, idx),
        exposure_scale=pd.Series(S, idx), regime=pd.Series(G, idx),
        signals=individual, rf=rf_s, financing=pd.Series(FIN, idx),
    )
