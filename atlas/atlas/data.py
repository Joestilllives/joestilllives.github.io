"""Market data: loaders, a realistic synthetic generator, and cleaning.

Every downstream module consumes one shape: a wide DataFrame of daily close
prices, indexed by date, one column per instrument. NaN before an instrument
starts trading is allowed and handled everywhere.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def synthetic_prices(n_assets: int = 12, n_days: int = 252 * 20, seed: int = 7,
                     start: str = "2005-01-03", trend_strength: float = 0.45) -> pd.DataFrame:
    """Multi-asset prices with the features that break naive systems.

    * factor-correlated returns (diversification is partial, not free)
    * fat tails (Student-t, df=4)
    * a two-state volatility regime (calm / stress) shared by all assets
    * persistent, randomly switching drifts (so trend has *some* edge, and
      the edge decays and reverses — just like real markets)
    * staggered listing dates (later assets have shorter histories)

    `trend_strength` is the annualised Sharpe of a drift regime if you knew
    it perfectly. 0 = pure noise (every strategy should fail validation).
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start, periods=n_days)
    n_f = 3
    loadings = rng.normal(0.0, 0.6, (n_assets, n_f))
    ann_vol = rng.uniform(0.08, 0.35, n_assets)
    dvol = ann_vol / np.sqrt(252)

    # Volatility regime: Markov chain, stress = 2.2x vol, mean duration ~40d.
    stress = np.zeros(n_days, dtype=bool)
    for t in range(1, n_days):
        p_stay = 0.975 if stress[t - 1] else 0.996
        stress[t] = stress[t - 1] if rng.random() < p_stay else not stress[t - 1]
    vol_mult = np.where(stress, 2.2, 1.0)

    # Drift regimes: each asset re-draws its drift on average every ~150 days.
    switches = rng.random((n_days, n_assets)) < 1 / 150
    draws = rng.normal(0.0, 1.0, (n_days, n_assets)) * ann_vol * trend_strength / 252
    drift = np.zeros((n_days, n_assets))
    cur = draws[0].copy()
    for t in range(n_days):
        cur = np.where(switches[t], draws[t], cur)
        drift[t] = cur
    drift += 0.02 / 252  # small positive risk premium

    df_t = 4.0
    t_scale = np.sqrt((df_t - 2) / df_t)  # unit-variance Student-t
    f = rng.standard_t(df_t, (n_days, n_f)) * t_scale
    e = rng.standard_t(df_t, (n_days, n_assets)) * t_scale
    shocks = (f @ loadings.T + e) / np.sqrt((loadings ** 2).sum(1) + 1.0)
    rets = drift + shocks * dvol * vol_mult[:, None]
    prices = 100.0 * np.exp(np.cumsum(rets, axis=0))

    cols = [f"SYN{i:02d}" for i in range(n_assets)]
    out = pd.DataFrame(prices, index=dates, columns=cols)
    # Staggered listings: a third of assets start up to 6 years late.
    for j in rng.choice(n_assets, n_assets // 3, replace=False):
        out.iloc[: int(rng.integers(252, 252 * 6)), j] = np.nan
    return out


def load_csv(path: str | Path) -> pd.DataFrame:
    """Load prices from CSV, wide (date, SYM1, SYM2, ...) or long (date, symbol, close)."""
    raw = pd.read_csv(path)
    raw.columns = [c.strip().lower() if c.strip().lower() in
                   {"date", "symbol", "ticker", "close", "adj_close", "adj close"} else c.strip()
                   for c in raw.columns]
    if "symbol" in raw.columns or "ticker" in raw.columns:
        sym = "symbol" if "symbol" in raw.columns else "ticker"
        px = next(c for c in ("adj_close", "adj close", "close") if c in raw.columns)
        wide = raw.pivot_table(index="date", columns=sym, values=px)
    else:
        wide = raw.set_index("date")
    wide.index = pd.to_datetime(wide.index)
    return wide.sort_index().astype(float)


def load_yfinance(symbols: list[str], start: str = "2005-01-01") -> pd.DataFrame:
    """Adjusted closes from Yahoo Finance (optional dependency: `pip install yfinance`)."""
    try:
        import yfinance as yf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("yfinance not installed: pip install yfinance") from exc
    df = yf.download(symbols, start=start, auto_adjust=True, progress=False)["Close"]
    if isinstance(df, pd.Series):
        df = df.to_frame(symbols[0])
    return df.sort_index().astype(float)


def clean_prices(prices: pd.DataFrame, max_ffill: int = 5, max_abs_ret: float = 0.5,
                 min_history: int = 260) -> pd.DataFrame:
    """Defensive cleaning. Bad data is the #1 killer of automated systems.

    * non-positive prices -> NaN
    * single-day moves above `max_abs_ret` that fully reverse next day -> NaN (spikes)
    * forward-fill short gaps only (holidays, stale quotes), never long ones
    * drop instruments that never accumulate `min_history` observations
    """
    px = prices.copy().sort_index()
    px = px[~px.index.duplicated(keep="last")]
    px = px.where(px > 0)
    r = px.pct_change(fill_method=None)
    spike = (r.abs() > max_abs_ret) & (r.shift(-1).abs() > max_abs_ret * 0.5) & (np.sign(r) != np.sign(r.shift(-1)))
    px = px.mask(spike)
    px = px.ffill(limit=max_ffill)
    keep = px.notna().sum() >= min_history
    return px.loc[:, keep]


def get_prices(cfg: dict) -> pd.DataFrame:
    d = cfg.get("data", {})
    src = d.get("source", "synthetic")
    if src == "synthetic":
        px = synthetic_prices(d.get("n_assets", 12), d.get("n_days", 252 * 20), d.get("seed", 7),
                              trend_strength=d.get("trend_strength", 0.45))
    elif src == "csv":
        px = load_csv(d["path"])
    elif src == "yfinance":
        px = load_yfinance(d["symbols"], d.get("start", "2005-01-01"))
    else:
        raise ValueError(f"unknown data source {src!r}")
    return clean_prices(px, min_history=d.get("min_history", 260))
