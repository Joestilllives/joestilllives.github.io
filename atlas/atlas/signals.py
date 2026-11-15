"""Alpha signals ("forecasts").

Contract for every signal:
  * input: wide price frame
  * output: same-shape frame of forecasts, roughly unit average |forecast|,
    clipped to [-CAP, +CAP]. Positive = long.
  * strictly causal: the value at row t uses prices at rows <= t only.
    (tests/test_no_lookahead.py enforces this for every registered signal.)

The scaling to unit average magnitude uses an *expanding* mean, so it is
causal too. That lets the portfolio layer treat a forecast of 1.0 as
"normal conviction" regardless of which signal produced it.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

CAP = 2.0


def log_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return np.log(prices).diff()


def ewma_vol(prices: pd.DataFrame, span: int = 35) -> pd.DataFrame:
    """Daily return volatility, EWMA, floored to avoid divide-by-tiny."""
    vol = log_returns(prices).ewm(span=span, min_periods=20).std()
    floor = vol.expanding(min_periods=20).median() * 0.25
    return vol.clip(lower=floor)


def _unit_scale(raw: pd.DataFrame, min_periods: int = 126) -> pd.DataFrame:
    """Causally rescale so the long-run mean |forecast| is 1, then cap."""
    scale = raw.abs().expanding(min_periods=min_periods).mean()
    return (raw / scale).clip(-CAP, CAP)


def _xs_zscore(raw: pd.DataFrame) -> pd.DataFrame:
    mu = raw.mean(axis=1)
    sd = raw.std(axis=1).replace(0, np.nan)
    return raw.sub(mu, axis=0).div(sd, axis=0)


# ---------------------------------------------------------------- signals

def trend(prices: pd.DataFrame, speeds=((8, 32), (16, 64), (32, 128), (64, 256))) -> pd.DataFrame:
    """Multi-speed EWMA crossover, risk-normalised. The workhorse of CTAs."""
    price_vol = prices * ewma_vol(prices)
    parts = []
    for fast, slow in speeds:
        raw = (prices.ewm(span=fast, min_periods=fast).mean()
               - prices.ewm(span=slow, min_periods=slow).mean()) / price_vol
        parts.append(_unit_scale(raw))
    return _unit_scale(sum(parts) / len(parts))


def ts_momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """12-1 time-series momentum as a volatility-adjusted t-stat."""
    mom = np.log(prices.shift(skip) / prices.shift(lookback))
    raw = mom / (ewma_vol(prices) * np.sqrt(lookback - skip))
    return _unit_scale(raw)


def xs_momentum(prices: pd.DataFrame, lookback: int = 252, skip: int = 21) -> pd.DataFrame:
    """Cross-sectional momentum: long relative winners, short relative losers."""
    mom = np.log(prices.shift(skip) / prices.shift(lookback)) / ewma_vol(prices)
    return _unit_scale(_xs_zscore(mom))


def reversal(prices: pd.DataFrame, lookback: int = 5) -> pd.DataFrame:
    """Short-term cross-sectional reversal (liquidity provision premium)."""
    r = np.log(prices / prices.shift(lookback)) / (ewma_vol(prices) * np.sqrt(lookback))
    return _unit_scale(-_xs_zscore(r))


def low_vol(prices: pd.DataFrame, window: int = 126) -> pd.DataFrame:
    """Low-volatility anomaly: overweight calmer instruments, cross-sectionally."""
    vol = log_returns(prices).rolling(window, min_periods=window // 2).std()
    return _unit_scale(-_xs_zscore(np.log(vol)))


def carry(prices: pd.DataFrame, carry_frame: pd.DataFrame | None = None) -> pd.DataFrame:
    """Carry needs external data (yields, futures roll, funding). Provide an
    annualised carry frame aligned to prices; without one this is flat."""
    if carry_frame is None:
        return pd.DataFrame(0.0, index=prices.index, columns=prices.columns)
    cf = carry_frame.reindex_like(prices).ffill()
    return _unit_scale(cf / (ewma_vol(prices) * np.sqrt(252)))


REGISTRY: dict[str, Callable[..., pd.DataFrame]] = {
    "trend": trend,
    "ts_momentum": ts_momentum,
    "xs_momentum": xs_momentum,
    "reversal": reversal,
    "low_vol": low_vol,
    "carry": carry,
}


# ------------------------------------------------------------ combination

def rolling_ic(signal: pd.DataFrame, prices: pd.DataFrame, horizon: int = 21,
               window: int = 504) -> pd.Series:
    """Pooled information coefficient of a signal, measured causally.

    IC at t correlates the signal at t-horizon with the vol-normalised return
    realised over (t-horizon, t]. Nothing after t is touched.
    """
    fwd = np.log(prices / prices.shift(horizon))
    y = fwd / (ewma_vol(prices).shift(horizon) * np.sqrt(horizon))
    x = signal.shift(horizon)
    ok = x.notna() & y.notna()
    x, y = x.where(ok, 0.0), y.where(ok, 0.0)
    sxy = (x * y).sum(axis=1).rolling(window, min_periods=window // 2).sum()
    sxx = (x * x).sum(axis=1).rolling(window, min_periods=window // 2).sum()
    syy = (y * y).sum(axis=1).rolling(window, min_periods=window // 2).sum()
    return sxy / np.sqrt(sxx * syy)


def build_forecasts(prices: pd.DataFrame, cfg: dict, extra: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Compute every configured signal and blend into one forecast frame.

    method = "static":   fixed weights from config.
    method = "adaptive": weights tilt toward signals with positive recent IC
                         (shrunk 50% to the static prior to avoid chasing noise).
    Returns (combined_forecast, {name: individual_forecast}).
    """
    scfg = cfg.get("signals", {})
    weights: dict = scfg.get("weights", {"trend": 1.0})
    params: dict = scfg.get("params", {})
    extra = extra or {}
    individual = {}
    for name, w in weights.items():
        if w == 0:
            continue
        fn = REGISTRY[name]
        kw = dict(params.get(name, {}))
        if name == "carry":
            kw["carry_frame"] = extra.get("carry")
        individual[name] = fn(prices, **kw).fillna(0.0)

    names = list(individual)
    prior = pd.Series({n: float(weights[n]) for n in names})
    prior = prior / prior.abs().sum()

    if scfg.get("method", "static") == "adaptive" and len(names) > 1:
        ics = pd.DataFrame({n: rolling_ic(individual[n], prices) for n in names}).clip(lower=0.0)
        ic_w = ics.div(ics.sum(axis=1).replace(0, np.nan), axis=0)
        w_t = (0.5 * ic_w).add(0.5 * prior, axis=1).fillna(prior)
    else:
        w_t = pd.DataFrame([prior.values] * len(prices), index=prices.index, columns=names)

    combo = sum(individual[n].mul(w_t[n], axis=0) for n in names)
    # Blending diversifies forecasts and shrinks them; re-scale to unit magnitude.
    combo = _unit_scale(combo).where(prices.notna(), 0.0).fillna(0.0)
    return combo, individual
