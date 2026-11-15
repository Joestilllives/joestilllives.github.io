"""Performance statistics, including the ones that tell you if you're fooling yourself.

The Probabilistic Sharpe Ratio (PSR) and Deflated Sharpe Ratio (DSR) come from
Bailey & Lopez de Prado. DSR asks: given how many configurations I tried,
what is the probability the true Sharpe is above zero? If you tried 50
variants and kept the best, a Sharpe of 1.0 can easily be pure luck.
"""
from __future__ import annotations

from math import erf, exp, log, sqrt

import numpy as np
import pandas as pd

TRADING_DAYS = 252
EULER = 0.5772156649


def _ncdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def _ninv(p: float) -> float:
    """Inverse normal CDF (Acklam's rational approximation, |err| < 1.2e-9)."""
    a = [-3.969683028665376e01, 2.209460984245205e02, -2.759285104469687e02,
         1.383577518672690e02, -3.066479806614716e01, 2.506628277459239e00]
    b = [-5.447609879822406e01, 1.615858368580409e02, -1.556989798598866e02,
         6.680131188771972e01, -1.328068155288572e01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e00,
         -2.549732539343734e00, 4.374664141464968e00, 2.938163982698783e00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e00, 3.754408661907416e00]
    lo = 0.02425
    if p < lo:
        q = sqrt(-2 * log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - lo:
        return -_ninv(1 - p)
    q = p - 0.5; r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def drawdown(returns: pd.Series) -> pd.Series:
    eq = (1 + returns).cumprod()
    return eq / eq.cummax() - 1


def probabilistic_sharpe(returns: pd.Series, benchmark_sr: float = 0.0) -> float:
    """P(true per-period Sharpe > benchmark), adjusting for skew and fat tails."""
    r = returns.dropna()
    n = len(r)
    if n < 30 or r.std() == 0:
        return float("nan")
    sr = r.mean() / r.std()
    g3, g4 = r.skew(), r.kurt() + 3
    denom = sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    return _ncdf((sr - benchmark_sr) * sqrt(n - 1) / denom)


def expected_max_sharpe(n_trials: int, sr_std: float) -> float:
    """Expected max of n_trials Sharpe estimates under the null of zero skill."""
    if n_trials <= 1:
        return 0.0
    return sr_std * ((1 - EULER) * _ninv(1 - 1 / n_trials) + EULER * _ninv(1 - 1 / (n_trials * exp(1))))


def deflated_sharpe(returns: pd.Series, n_trials: int, trial_sharpes: list[float] | None = None) -> float:
    """DSR: PSR against the Sharpe you'd expect from the best of `n_trials` lucky draws."""
    r = returns.dropna()
    if trial_sharpes is not None and len(trial_sharpes) > 1:
        sr_std = float(np.std(trial_sharpes, ddof=1))
    else:
        sr_std = 1 / sqrt(max(len(r) - 1, 1))  # sampling std of SR under the null
    return probabilistic_sharpe(r, expected_max_sharpe(n_trials, sr_std))


def summary(returns: pd.Series, rf: pd.Series | None = None) -> dict:
    """Stats on total returns. Sharpe, Sortino and PSR use returns in excess
    of the cash rate `rf` (daily, decimal) when given: a leveraged book must
    beat its own financing to add anything."""
    r = returns.dropna()
    # Skip the warm-up period where the book is flat.
    nz = r.ne(0).to_numpy().nonzero()[0]
    r = r.iloc[nz[0]:] if len(nz) else r
    x = r - rf.reindex(r.index).fillna(0.0) if rf is not None else r
    if len(r) < 2:
        return {}
    years = len(r) / TRADING_DAYS
    total = float((1 + r).prod())
    vol = float(r.std() * sqrt(TRADING_DAYS))
    mean = float(x.mean() * TRADING_DAYS)
    down = x[x < 0].std() * sqrt(TRADING_DAYS)
    dd = drawdown(r)
    cagr = total ** (1 / years) - 1 if total > 0 else -1.0
    monthly = (1 + r).resample("ME").prod() - 1
    return {
        "start": str(r.index[0].date()), "end": str(r.index[-1].date()), "years": round(years, 2),
        "cagr": cagr, "vol": vol,
        "sharpe": mean / vol if vol > 0 else float("nan"),
        "sortino": mean / down if down > 0 else float("nan"),
        "max_drawdown": float(dd.min()),
        "calmar": cagr / abs(dd.min()) if dd.min() < 0 else float("nan"),
        "skew": float(r.skew()), "excess_kurtosis": float(r.kurt()),
        "hit_rate_daily": float((r > 0).mean()),
        "hit_rate_monthly": float((monthly > 0).mean()),
        "worst_day": float(r.min()), "worst_month": float(monthly.min()),
        "var_95_daily": float(-np.percentile(r, 5)),
        "cvar_95_daily": float(-r[r <= np.percentile(r, 5)].mean()),
        "psr": probabilistic_sharpe(x),
    }


def format_stats(s: dict) -> str:
    pct = {"cagr", "vol", "max_drawdown", "hit_rate_daily", "hit_rate_monthly", "worst_day",
           "worst_month", "var_95_daily", "cvar_95_daily", "cost_drag_ann", "psr", "dsr"}
    lines = []
    for k, v in s.items():
        if isinstance(v, float):
            v = f"{v:8.2%}" if k in pct else f"{v:8.3f}"
        lines.append(f"  {k:<18} {v}")
    return "\n".join(lines)
