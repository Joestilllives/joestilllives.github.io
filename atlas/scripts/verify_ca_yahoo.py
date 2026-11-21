"""Second-source verification of large one-day drops in NSE bhavcopy data.

For every stock that was ever among the 300 most traded, every day with a raw
drop of 15% or more is checked against Yahoo's split/bonus-adjusted series:

  * Yahoo shows a normal day  -> it was a corporate action: use Yahoo's return
  * Yahoo shows the drop too  -> it was real: keep the raw return (this also
                                 undoes any wrong inference in atlas/stocks.py)
  * symbol not on Yahoo (typically delisted) -> keep the conservative rules

Writes date, symbol, raw_ret, yahoo_ret, verdict.
usage: python scripts/verify_ca_yahoo.py PANEL.pkl OUT.csv
"""
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import yfinance as yf  # noqa: E402

p = pickle.load(open(sys.argv[1], "rb"))
liq = p.value.rolling(63, min_periods=40).median()
ever = (liq.rank(axis=1, ascending=False) <= 300).any()
syms = list(ever[ever].index)
raw_ratio = p.close / p.close.ffill().shift(1)
cand = (raw_ratio[syms] < 0.85).stack()
cand = cand[cand].index                      # (date, symbol)
need = sorted(set(cand.get_level_values(1)))

yret = {}
for i in range(0, len(need), 80):
    chunk = need[i:i + 80]
    d = yf.download([s + ".NS" for s in chunk], start="2004-12-01", auto_adjust=True,
                    progress=False, threads=True)["Close"]
    if isinstance(d, pd.Series):
        d = d.to_frame(chunk[0] + ".NS")
    for s in chunk:
        col = s + ".NS"
        if col in d and d[col].notna().sum() > 50:
            yret[s] = d[col].dropna().pct_change()
    print(f"{min(i + 80, len(need))}/{len(need)} symbols, {len(yret)} on Yahoo", flush=True)

rows = []
for dt, s in cand:
    raw = float(raw_ratio.at[dt, s] - 1)
    if s not in yret or dt not in yret[s].index or not np.isfinite(yret[s].at[dt]):
        rows.append((dt.date(), s, raw, np.nan, "unverified"))
        continue
    y = float(yret[s].at[dt])
    verdict = "corporate_action" if y - raw > 0.08 else "real"
    rows.append((dt.date(), s, raw, y, verdict))
out = pd.DataFrame(rows, columns=["date", "symbol", "raw_ret", "yahoo_ret", "verdict"])
out.to_csv(sys.argv[2], index=False)
print(out.verdict.value_counts().to_string())
