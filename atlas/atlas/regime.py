"""Market-regime overlay: a single risk-appetite multiplier in [floor, 1].

Volatility targeting already shrinks positions as vol rises, but only after
vol shows up in the estimator. The regime overlay reacts to *structural*
stress signals that precede or accompany crises:

  * vol shock      - short-term vol far above its long-run level
  * correlation    - average pairwise correlation spiking (diversification
                     evaporating: everything falls together)
  * breadth        - most instruments below their long moving average

All inputs are causal. The output is smoothed so it does not whipsaw.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def avg_pairwise_corr(returns: pd.DataFrame, window: int = 63) -> pd.Series:
    """Average off-diagonal correlation, via the variance-of-sum identity (fast)."""
    z = (returns - returns.rolling(window).mean()) / returns.rolling(window).std()
    n = z.notna().sum(axis=1)
    var_sum = z.fillna(0).sum(axis=1).rolling(window).var()
    return ((var_sum - n) / (n * (n - 1)).replace(0, np.nan)).clip(-1, 1)


def regime_multiplier(prices: pd.DataFrame, cfg: dict) -> pd.Series:
    rc = cfg.get("regime", {})
    idx = prices.index
    if not rc.get("enabled", True):
        return pd.Series(1.0, index=idx)
    rets = np.log(prices).diff()
    ew = rets.mean(axis=1)  # equal-weight "market"

    # 1) vol shock
    short = ew.rolling(20, min_periods=10).std()
    long = ew.rolling(504, min_periods=126).std()
    ratio = short / long
    vol_m = np.clip(1.0 - (ratio - rc.get("vol_ratio_start", 1.5)) * 0.5, 0.5, 1.0)

    # 2) correlation spike (z-score of avg correlation vs its own history)
    c = avg_pairwise_corr(rets)
    cz = (c - c.expanding(252).mean()) / c.expanding(252).std()
    corr_m = np.clip(1.0 - (cz - rc.get("corr_z_start", 1.5)) * 0.15, 0.6, 1.0)

    # 3) breadth: share of instruments above their 200d average. Only useful
    #    for long-biased books (a long/short trend book profits in selloffs),
    #    so it is off by default.
    if rc.get("use_breadth", False):
        above = (prices > prices.rolling(200, min_periods=150).mean()).where(prices.notna())
        breadth_m = np.clip(0.7 + above.mean(axis=1), 0.7, 1.0)
    else:
        breadth_m = pd.Series(1.0, index=idx)

    m = (pd.Series(vol_m, index=idx).fillna(1.0)
         * pd.Series(corr_m, index=idx).fillna(1.0)
         * pd.Series(breadth_m, index=idx).fillna(1.0))
    m = m.ewm(span=rc.get("smooth_span", 5)).mean()
    return m.clip(lower=rc.get("floor", 0.35), upper=1.0)
