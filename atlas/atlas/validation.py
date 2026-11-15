"""Validation: the difference between a strategy and a backtest artefact.

  * walk_forward     - pick the best config on past data only, trade it on the
                       next unseen year, repeat. The stitched out-of-sample
                       track is the honest estimate of live performance.
  * deflated Sharpe  - penalises the number of variants you tried.
  * block bootstrap  - confidence interval on Sharpe that respects
                       autocorrelation and volatility clustering.
  * cost stress      - does the edge survive 2-3x the assumed costs?
  * signal ablation  - what does each signal contribute on its own?
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .metrics import deflated_sharpe, summary


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _sharpe(r: pd.Series) -> float:
    r = r.dropna()
    return float(r.mean() / r.std() * np.sqrt(252)) if len(r) > 20 and r.std() > 0 else float("-inf")


@dataclass
class WalkForwardResult:
    oos_returns: pd.Series
    choices: pd.DataFrame
    variant_sharpes: dict
    dsr: float


def walk_forward(prices: pd.DataFrame, cfg: dict, grid: list[dict], train_years: int = 5,
                 test_years: int = 1) -> WalkForwardResult:
    """Every component is causal, so each variant is simulated once over the
    full history and selection uses only returns from *before* each test window."""
    runs = [run_backtest(prices, deep_merge(cfg, g)).excess for g in grid]
    idx = prices.index
    start = idx[0] + pd.DateOffset(years=train_years)
    pieces, rows = [], []
    t0 = start
    while t0 < idx[-1]:
        t1 = t0 + pd.DateOffset(years=test_years)
        train = slice(t0 - pd.DateOffset(years=train_years), t0 - pd.Timedelta(days=1))
        scores = [_sharpe(r.loc[train]) for r in runs]
        best = int(np.argmax(scores))
        test = runs[best].loc[t0: t1 - pd.Timedelta(days=1)]
        pieces.append(test)
        rows.append({"test_start": t0.date(), "chosen": best, "train_sharpe": scores[best],
                     "test_sharpe": _sharpe(test)})
        t0 = t1
    oos = pd.concat(pieces) if pieces else pd.Series(dtype=float)
    full = {i: _sharpe(r) for i, r in enumerate(runs)}
    daily_sr = [s / np.sqrt(252) for s in full.values() if np.isfinite(s)]
    return WalkForwardResult(oos, pd.DataFrame(rows), full,
                             deflated_sharpe(oos, len(grid), daily_sr))


def block_bootstrap_sharpe(returns: pd.Series, n_boot: int = 1000, block: int = 21,
                           seed: int = 0) -> tuple[float, float, float]:
    """Stationary-block bootstrap: (5th pct, median, 95th pct) of annualised Sharpe."""
    r = returns.dropna().to_numpy()
    r = r[np.argmax(r != 0):] if np.any(r != 0) else r
    n = len(r)
    rng = np.random.default_rng(seed)
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, n // block + 1)
        sample = np.concatenate([np.take(r, np.arange(s, s + block), mode="wrap") for s in starts])[:n]
        out[b] = sample.mean() / sample.std() * np.sqrt(252) if sample.std() > 0 else 0.0
    return tuple(np.percentile(out, [5, 50, 95]))


def cost_stress(prices: pd.DataFrame, cfg: dict, multipliers=(1, 2, 3)) -> pd.DataFrame:
    e = cfg.get("execution", {})
    rows = []
    for m in multipliers:
        over = {"execution": {k: e.get(k, d) * m for k, d in
                              (("commission_bps", 0.5), ("half_spread_bps", 1.0), ("impact_k", 0.5))}}
        s = run_backtest(prices, deep_merge(cfg, over)).stats
        rows.append({"cost_x": m, "sharpe": s["sharpe"], "cagr": s["cagr"], "cost_drag": s["cost_drag_ann"]})
    return pd.DataFrame(rows)


def signal_ablation(prices: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    weights = cfg.get("signals", {}).get("weights", {})
    rows = []
    for name, w in weights.items():
        if not w:
            continue
        solo = deep_merge(cfg, {"signals": {"weights": {name: 1.0}, "method": "static"}})
        solo["signals"]["weights"] = {name: 1.0}
        s = run_backtest(prices, solo).stats
        rows.append({"signal": name, "sharpe": s.get("sharpe"), "cagr": s.get("cagr"),
                     "max_dd": s.get("max_drawdown")})
    return pd.DataFrame(rows)


def lookahead_probe(prices: pd.DataFrame, cfg: dict, cut: int | None = None) -> float:
    """Scramble everything after `cut` and confirm weights before it are unchanged.
    Returns max abs weight difference (must be ~0)."""
    cut = cut or len(prices) * 2 // 3
    rng = np.random.default_rng(1)
    scrambled = prices.copy()
    tail = scrambled.iloc[cut:]
    scrambled.iloc[cut:] = tail.to_numpy() * rng.uniform(0.5, 1.5, tail.shape)
    a = run_backtest(prices, cfg).weights.iloc[:cut]
    b = run_backtest(scrambled, cfg).weights.iloc[:cut]
    return float((a - b).abs().to_numpy().max())
