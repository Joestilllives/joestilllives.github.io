"""Risk model and portfolio construction.

Risk model: volatilities from a fast EWMA (vol clusters, react quickly),
correlations from a slow EWMA (correlations are noisy, react slowly), with
correlations shrunk toward their cross-sectional average (Ledoit-Wolf style
constant-correlation target). Updated recursively one day at a time so the
backtest and the live system use *identical* code.

Construction methods:
  * "risk_budget"   - forecast x (target vol / instrument vol) / N x IDM.
                      Position size scales with conviction; portfolio vol
                      floats around target. Robust, low-parameter. Default.
  * "mean_variance" - w = Sigma^-1 mu with mu = IC x forecast x vol, then
                      scaled to hit target vol exactly. Exploits correlation
                      structure, but more sensitive to estimation error.
Then constraints: per-asset cap, gross leverage cap, optional long-only,
and an ex-ante vol ceiling.
"""
from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


class RiskModel:
    def __init__(self, n: int, vol_span: int = 35, corr_halflife: int = 126,
                 shrink: float = 0.3, warmup: int = 60):
        self.n = n
        self.a_vol = 2.0 / (vol_span + 1)
        self.a_cov = 1.0 - 0.5 ** (1.0 / corr_halflife)
        self.shrink = shrink
        self.warmup = warmup
        self.var = np.full(n, np.nan)
        self.cov = np.zeros((n, n))
        self.count = np.zeros(n, dtype=int)

    def update(self, r: np.ndarray) -> None:
        """Feed one day of log returns (NaN = not trading)."""
        ok = np.isfinite(r)
        x = np.where(ok, r, 0.0)
        fresh = ok & ~np.isfinite(self.var)
        self.var = np.where(fresh, x ** 2 + 1e-8, self.var)
        upd = ok & ~fresh
        self.var = np.where(upd, (1 - self.a_vol) * self.var + self.a_vol * x ** 2, self.var)
        both = np.outer(ok, ok)
        self.cov = np.where(both, (1 - self.a_cov) * self.cov + self.a_cov * np.outer(x, x), self.cov)
        self.count += ok

    @property
    def ready(self) -> np.ndarray:
        return self.count >= self.warmup

    @property
    def vol(self) -> np.ndarray:
        """Daily vol per asset (NaN where not ready)."""
        return np.where(self.ready, np.sqrt(self.var), np.nan)

    def corr(self) -> np.ndarray:
        d = np.sqrt(np.clip(np.diag(self.cov), 1e-16, None))
        c = self.cov / np.outer(d, d)
        np.fill_diagonal(c, 1.0)
        c = np.clip(c, -0.99, 0.99)
        np.fill_diagonal(c, 1.0)
        m = self.ready
        if m.sum() > 1:
            sub = c[np.ix_(m, m)]
            avg = (sub.sum() - m.sum()) / (m.sum() * (m.sum() - 1))
            target = np.full_like(c, avg)
            np.fill_diagonal(target, 1.0)
            c = (1 - self.shrink) * c + self.shrink * target
        return c

    def covariance(self) -> np.ndarray:
        v = np.nan_to_num(self.vol)
        return self.corr() * np.outer(v, v)


def ex_ante_vol(w: np.ndarray, cov: np.ndarray) -> float:
    return float(np.sqrt(max(w @ cov @ w, 0.0)) * np.sqrt(TRADING_DAYS))


def diversification_multiplier(corr: np.ndarray, active: np.ndarray, cap: float = 2.5) -> float:
    k = int(active.sum())
    if k <= 1:
        return 1.0
    c = np.clip(corr[np.ix_(active, active)], 0.0, 1.0)  # Carver: floor negatives at 0
    w = np.full(k, 1.0 / k)
    return float(min(cap, 1.0 / np.sqrt(w @ c @ w)))


def target_weights(forecast: np.ndarray, model: RiskModel, pcfg: dict) -> np.ndarray:
    n = len(forecast)
    vol = model.vol
    active = model.ready & np.isfinite(forecast) & np.isfinite(vol)
    w = np.zeros(n)
    if not active.any():
        return w
    tv = pcfg.get("target_vol", 0.12)
    f = np.where(active, forecast, 0.0)
    ann = np.where(active, vol * np.sqrt(TRADING_DAYS), np.inf)
    cov = model.covariance()
    method = pcfg.get("method", "risk_budget")

    if method == "risk_budget":
        idm = diversification_multiplier(model.corr(), active, pcfg.get("max_idm", 2.5))
        w = f * (tv / ann) / active.sum() * idm
    elif method == "mean_variance":
        mu = pcfg.get("assumed_ic", 0.05) * f * np.nan_to_num(vol)
        sub = np.ix_(active, active)
        ridge = np.eye(active.sum()) * np.trace(cov[sub]) / active.sum() * pcfg.get("ridge", 0.1)
        w[active] = np.linalg.solve(cov[sub] + ridge, mu[active])
        vol_now = ex_ante_vol(w, cov)
        if vol_now > 0:
            # Scale so a portfolio of unit-strength forecasts hits target vol.
            strength = np.mean(np.abs(f[active]))
            w *= tv / vol_now * min(strength, 2.0)
    else:
        raise ValueError(f"unknown portfolio method {method!r}")

    return apply_constraints(w, cov, pcfg)


def apply_constraints(w: np.ndarray, cov: np.ndarray, pcfg: dict) -> np.ndarray:
    w = np.nan_to_num(w)
    if pcfg.get("long_only", False):
        w = np.clip(w, 0.0, None)
    cap = pcfg.get("max_weight", 0.5)
    w = np.clip(w, -cap, cap)
    gross = np.abs(w).sum()
    max_gross = pcfg.get("max_gross", 3.0)
    if gross > max_gross:
        w *= max_gross / gross
    max_net = pcfg.get("max_net")
    if max_net is not None and abs(w.sum()) > max_net:
        w -= (w.sum() - np.sign(w.sum()) * max_net) / max(np.count_nonzero(w), 1) * (w != 0)
    ceiling = pcfg.get("target_vol", 0.12) * pcfg.get("vol_ceiling_mult", 1.5)
    v = ex_ante_vol(w, cov)
    if v > ceiling:
        w *= ceiling / v
    return w
