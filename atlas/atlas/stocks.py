"""Survivorship-free NSE stock panel and a monthly stock-selection backtester.

Data: every EQ-series stock in every NSE bhavcopy (scripts/build_nse_stocks.py),
including stocks later delisted, suspended or merged.

Corporate actions: bhavcopy PREVCLOSE is not adjusted for bonuses/splits, so a
1:1 bonus shows as a -50% day. Adjustment is inferred from prices, with every
rule chosen so that a *mistake hurts* the backtest rather than flattering it:

  * only drops >= 30% are candidates (normal circuit limits are 5-20%)
  * the price ratio must match a standard split/bonus factor within +-6%
    (a normal day's market move); otherwise the drop is kept as a real loss
  * smaller factors (3/4, 4/5: 1:3 and 1:4 bonuses) are NOT adjusted: a missed
    adjustment appears as a fake loss, which only penalises the strategy
  * a stock that disappears for good while held exits 30% below its last price
  * where a second source exists (scripts/verify_ca_yahoo.py), every drop of
    15%+ in any stock that was ever among the 300 most traded is checked
    against Yahoo's adjusted series and that verdict wins
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import summary
from .tax import TaxConfig, TaxLedger, financial_year

FACTORS = np.array([1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 6, 1 / 8, 1 / 10, 1 / 20, 2 / 3, 2 / 5, 3 / 5, 3 / 10])
DELIST_HAIRCUT = -0.30


@dataclass
class Panel:
    close: pd.DataFrame       # raw closes (date x symbol)
    ret: pd.DataFrame         # corporate-action-adjusted daily returns (NaN = not traded)
    value: pd.DataFrame       # Rs traded per day
    adjustments: pd.DataFrame  # detected corporate actions
    last_day: pd.Series       # last trading date per symbol


def load_panel(path: str, start: str | None = None, end: str | None = None,
               corrections: str | None = None) -> Panel:
    raw = pd.read_csv(path, parse_dates=["date"])
    if start:
        raw = raw[raw.date >= start]
    if end:
        raw = raw[raw.date <= end]
    raw = raw[raw.close > 0].drop_duplicates(["date", "symbol"], keep="last")
    close = raw.pivot(index="date", columns="symbol", values="close").sort_index()
    value = raw.pivot(index="date", columns="symbol", values="value").reindex_like(close)

    prev = close.ffill().shift(1)                      # last traded close (across gaps)
    ratio = close / prev
    cand = (ratio < 0.70).to_numpy()
    rr = ratio.to_numpy()
    ii, jj = np.nonzero(cand)
    x = rr[ii, jj]
    dev = np.abs(x[:, None] / FACTORS[None, :] - 1)
    k = dev.argmin(axis=1)
    hit = dev[np.arange(len(x)), k] <= 0.06
    fac = np.full(rr.shape, np.nan)
    fac[ii[hit], jj[hit]] = FACTORS[k[hit]]
    adj_factor = pd.DataFrame(fac, index=close.index, columns=close.columns)
    rows = list(zip(close.index[ii[hit]], close.columns[jj[hit]], x[hit], FACTORS[k[hit]]))
    ret = ratio - 1
    ret = ret.where(adj_factor.isna(), ratio / adj_factor - 1)
    ret = ret.where(close.notna())
    if corrections:
        # Second-source verdicts (scripts/verify_ca_yahoo.py) override the inference.
        cv = pd.read_csv(corrections, parse_dates=["date"])
        cv = cv[cv.verdict.isin(["corporate_action", "real"]) & cv.symbol.isin(ret.columns)
                & cv.date.isin(ret.index)]
        for v, val in (("corporate_action", "yahoo_ret"), ("real", "raw_ret")):
            sub = cv[cv.verdict == v]
            ri = ret.index.get_indexer(sub.date)
            ci = ret.columns.get_indexer(sub.symbol)
            arr = ret.to_numpy(copy=True)
            arr[ri, ci] = sub[val].to_numpy()
            ret = pd.DataFrame(arr, index=ret.index, columns=ret.columns)
    last_day = close.apply(lambda c: c.last_valid_index())
    return Panel(close, ret, value, pd.DataFrame(rows, columns=["date", "symbol", "ratio", "factor"]), last_day)


@dataclass
class StockConfig:
    top_liquid: int = 200        # universe: most traded stocks
    min_history: int = 273       # trading days needed (12m + 1m)
    min_price: float = 20.0
    lookback: int = 252
    skip: int = 21
    n_hold: int = 30
    weighting: str = "equal"     # "equal" | "inverse_vol"
    risk_adjusted: bool = False  # rank by momentum / volatility
    trend_filter: bool = False   # go to cash when the equal-weight universe is below its 200d average
    fee_bps: float = 12.0        # per side: STT 10bp + stamp/exchange/SEBI/GST/DP (avg)
    half_spread_bps: float = 8.0
    impact_k: float = 0.5
    cash_rate: float = 0.06
    capital: float = 1_000_000.0
    tax: bool = False


@dataclass
class StockResult:
    returns: pd.Series
    rf: pd.Series
    holdings: dict
    turnover: pd.Series
    costs: pd.Series
    tax_paid: dict

    def stats(self, start=None, end=None) -> dict:
        r = self.returns.loc[start:end]
        s = summary(r, self.rf.reindex(r.index))
        s["turnover_ann"] = float(self.turnover.loc[start:end].sum() / max(len(r) / 252, 1e-9))
        s["cost_drag_ann"] = float(self.costs.loc[start:end].sum() / max(len(r) / 252, 1e-9))
        return s


def run_stock_backtest(p: Panel, cfg: StockConfig) -> StockResult:
    """Monthly long-only stock selection. Decide at month-end close using data
    up to that day; trade at the next day's close (one-day lag)."""
    dates = p.close.index
    syms = p.close.columns
    R = p.ret.to_numpy()
    C = p.close.to_numpy()
    V = p.value.fillna(0.0).to_numpy()
    n = len(syms)
    rf_d = cfg.cash_rate / 252

    logr = np.log1p(p.ret.fillna(0.0))
    mom = (logr.rolling(cfg.lookback - cfg.skip, min_periods=cfg.lookback - cfg.skip - 10).sum().shift(cfg.skip))
    vol = p.ret.rolling(252, min_periods=200).std()
    hist = p.close.notna().cumsum()
    liq = p.value.rolling(63, min_periods=40).median()
    ew = p.ret.where(liq.rank(axis=1, ascending=False) <= cfg.top_liquid).mean(axis=1).fillna(0)
    ew_lvl = (1 + ew).cumprod()
    ew_ok = (ew_lvl > ew_lvl.rolling(200, min_periods=150).mean()).to_numpy()
    month_end = pd.Series(dates.to_period("M"), index=dates)
    rebal = set(np.nonzero((month_end != month_end.shift(-1)).to_numpy())[0])

    ledger = TaxLedger(TaxConfig()) if cfg.tax else None
    w = np.zeros(n)
    equity = cfg.capital
    eq = np.empty(len(dates)); TO = np.zeros(len(dates)); CO = np.zeros(len(dates))
    pending = None
    holdings = {}
    MOM, VOL, HIST, LIQ = mom.to_numpy(), vol.to_numpy(), hist.to_numpy(), liq.to_numpy()

    for i in range(len(dates)):
        if i > 0:
            r = R[i]
            gone = (w != 0) & np.isnan(r) & (p.last_day.to_numpy() == dates[i - 1])
            r = np.where(gone, DELIST_HAIRCUT, np.nan_to_num(r))
            cash = 1.0 - w.sum()
            pr = float(w @ r) + cash * rf_d
            if ledger is not None and cash > 0:
                ledger.add_interest(cash * rf_d * equity)
            equity *= 1 + pr
            w = w * (1 + r) / (1 + pr)
            if gone.any():  # delisted: position is closed at the haircut price
                if ledger is not None:
                    for k in np.nonzero(gone)[0]:
                        lp = C[i - 1, k] * (1 + DELIST_HAIRCUT)
                        ledger.sell(syms[k], sum(u for u, _, _ in ledger.lots[syms[k]]), lp, dates[i])
                w[gone] = 0.0
            if ledger is not None and financial_year(dates[i]) != financial_year(dates[i - 1]):
                tax = ledger.settle(financial_year(dates[i - 1]))
                if tax > 0:
                    frac = min(tax / equity, 0.99)
                    w = w / (1 - frac)
                    s = w.sum()
                    if s > 1:
                        w /= s
                    equity *= 1 - frac
                    CO[i] += 0  # tax tracked in ledger, not as trading cost

        if pending is not None:
            tgt = pending
            pending = None
            tradable = np.isfinite(C[i])
            tgt = np.where(tradable, tgt, w)           # can't trade a stock that didn't trade
            dw = tgt - w
            a = np.abs(dw)
            adv = np.maximum(LIQ[i] if np.isfinite(LIQ[i]).any() else np.ones(n), 1.0)
            dvol = np.nan_to_num(VOL[i], nan=0.03)
            impact = cfg.impact_k * dvol * np.sqrt(np.nan_to_num(a * equity / np.nan_to_num(adv, nan=1e12))) * a
            cost = (cfg.fee_bps + cfg.half_spread_bps) / 1e4 * a.sum() + float(np.nansum(impact))
            if ledger is not None:
                for k in np.nonzero(a > 1e-12)[0]:
                    units = dw[k] * equity / C[i, k]
                    if units > 0:
                        ledger.buy(syms[k], units, C[i, k], dates[i])
                    elif w[k] > 0:
                        ledger.sell(syms[k], min(-units, w[k] * equity / C[i, k]), C[i, k], dates[i])
            equity *= 1 - cost
            w = tgt
            TO[i] = a.sum()
            CO[i] = cost

        if i in rebal:
            elig = (HIST[i] >= cfg.min_history) & (np.nan_to_num(C[i]) >= cfg.min_price) & np.isfinite(MOM[i]) \
                & np.isfinite(LIQ[i]) & np.isfinite(C[i])
            liq_rank = np.where(elig, np.nan_to_num(LIQ[i]), -1)
            uni = np.argsort(-liq_rank)[:cfg.top_liquid]
            uni = uni[elig[uni]]
            score = MOM[i][uni] / (VOL[i][uni] if cfg.risk_adjusted else 1.0)
            ok = np.isfinite(score)
            uni, score = uni[ok], score[ok]
            pick = uni[np.argsort(-score)[:cfg.n_hold]]
            tgt = np.zeros(n)
            if len(pick) and (not cfg.trend_filter or ew_ok[i]):
                if cfg.weighting == "inverse_vol":
                    iv = 1 / np.nan_to_num(VOL[i][pick], nan=np.nanmedian(VOL[i][pick]))
                    tgt[pick] = iv / iv.sum()
                else:
                    tgt[pick] = 1.0 / len(pick)
            holdings[dates[i]] = [syms[k] for k in pick] if tgt.sum() > 0 else []
            pending = tgt
        eq[i] = equity

    e = pd.Series(eq, dates)
    return StockResult(e.pct_change().fillna(0.0), pd.Series(rf_d, dates), holdings,
                       pd.Series(TO, dates), pd.Series(CO, dates), ledger.paid if ledger else {})
