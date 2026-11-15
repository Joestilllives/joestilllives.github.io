"""Live monitoring: is live trading behaving like the strategy we validated?

Two questions, answered with numbers fixed *before* going live:

1. Expectation bands - block-bootstrap the backtest's daily returns into many
   alternative N-day paths. A live cumulative return below the 5th percentile
   is a WARNING; below the 1st percentile is a STOP (the live strategy is very
   unlikely to be the backtested one; find out why before trading on).
2. Tracking - over the same days, paper/live returns must correlate with the
   backtest (> 0.9) with low tracking error (< 3%/yr). A mismatch means an
   implementation bug, bad data or unmodelled costs, even if P&L looks fine.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def expectation_band(bt_returns: pd.Series, horizon: int, n_boot: int = 4000, block: int = 21,
                     seed: int = 0, pcts=(1, 5, 25, 50, 75, 95, 99)) -> dict:
    r = bt_returns.dropna().to_numpy()
    r = r[np.argmax(r != 0):]
    rng = np.random.default_rng(seed)
    n = len(r)
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, horizon // block + 1)
        path = np.concatenate([np.take(r, np.arange(s, s + block), mode="wrap") for s in starts])[:horizon]
        out[b] = np.prod(1 + path) - 1
    return {p: float(np.percentile(out, p)) for p in pcts}


def status(live_cum: float, band: dict) -> str:
    if live_cum < band[1]:
        return "STOP"
    if live_cum < band[5]:
        return "WARNING"
    return "OK"


def tracking(live: pd.Series, backtest: pd.Series) -> dict:
    j = pd.concat({"live": live, "bt": backtest}, axis=1).dropna()
    if len(j) < 5:
        return {"days": len(j)}
    d = j.live - j.bt
    return {"days": len(j), "corr": float(j.live.corr(j.bt)),
            "tracking_error_ann": float(d.std() * np.sqrt(252)),
            "live_total": float((1 + j.live).prod() - 1), "bt_total": float((1 + j.bt).prod() - 1)}
