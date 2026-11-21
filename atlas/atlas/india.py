"""India universe (CONSUMBEES excluded: erratic quotes, ~1 crore/day traded): liquid NSE ETFs, with NSE index proxies before an ETF listed.

Tradables are the ETFs. Where an ETF launched late, the history before its
first quote is the matching NSE price index (no dividends, so the proxy
period slightly understates long returns). Each series is cleaned on its
own before splicing, then the spliced return series is compounded to prices.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import _mask_round_trips, load_yfinance

# ETF -> proxy index used before the ETF's first quote (None = ETF history only)
UNIVERSE: dict[str, str | None] = {
    "NIFTYBEES.NS": "^NSEI",        # Nifty 50
    "JUNIORBEES.NS": None,          # Nifty Next 50
    "BANKBEES.NS": "^NSEBANK",      # Bank Nifty
    "PSUBNKBEES.NS": "^CNXPSUBANK", # PSU banks
    "ITBEES.NS": "^CNXIT",          # IT
    "PHARMABEES.NS": "^CNXPHARMA",  # Pharma
    "AUTOBEES.NS": "^CNXAUTO",      # Auto
    "CPSEETF.NS": "^CNXPSE",        # PSU enterprises
    "GOLDBEES.NS": None,            # Gold
    "SILVERBEES.NS": None,          # Silver
    "MON100.NS": None,              # Nasdaq 100 (in INR)
    "MAFANG.NS": None,              # US mega-cap tech (in INR)
    "HNGSNGBEES.NS": None,          # Hang Seng (in INR)
    "LTGILTBEES.NS": None,          # long-dated government bonds
    "GILT5YBEES.NS": None,          # 5-year government bonds
}


def build_india_prices(start: str = "2005-01-01") -> pd.DataFrame:
    tickers = list(UNIVERSE) + [p for p in UNIVERSE.values() if p]
    raw = load_yfinance(tickers, start)
    etfs = [t for t in UNIVERSE if t in raw.columns]
    raw[etfs] = _mask_round_trips(raw[etfs])   # exchange index data is never masked
    out = {}
    for etf, proxy in UNIVERSE.items():
        e = raw[etf].ffill(limit=5).pct_change(fill_method=None)
        first = raw[etf].first_valid_index()
        if proxy and first is not None:
            p = raw[proxy].ffill(limit=5).pct_change(fill_method=None)
            r = pd.concat([p[p.index <= first], e[e.index > first]])
        else:
            r = e
        r = r[~r.index.duplicated()].dropna()
        lvl = (1 + r).cumprod()
        # Anchor to the ETF's real last traded price so levels (and therefore
        # order quantities) are real; returns are unchanged by the scaling.
        last_real = raw[etf].dropna()
        out[etf] = lvl * (float(last_real.iloc[-1]) / float(lvl.iloc[-1])) if len(last_real) else lvl * 100.0
    px = pd.DataFrame(out).sort_index()
    return px.loc[px.notna().any(axis=1)]
