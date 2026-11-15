"""Build a 2005-2026 daily total-return history for SPY, TLT, IEF, GLD, DBC
from three public GitHub repositories (used because Yahoo/Stooq/FRED were
unreachable from the build environment). Stitches returns, not prices:

  C  11bblandin/quantfiction   Yahoo adj. close     to Mar 2018 (SPY, TLT, GLD)
  A  aspromatis/zipline_bundle close + dividends    2005 to Dec 2018 (gap filler; IEF, DBC history)
  B  fja05680/brownbear        Yahoo adj. close     Jan 2019 onward

Known data caveat: source A misses some IEF dividends in 2005-2009
(~1-2%/yr understated in those years). Overlaps agree at corr > 0.998.

usage: python scripts/build_etf5.py OUT.csv
"""
import io
import sys
import urllib.request

import pandas as pd

TICKERS = ["SPY", "TLT", "IEF", "GLD", "DBC"]
SRC = {
    "C": "https://raw.githubusercontent.com/11bblandin/quantfiction/master/data/{t}.csv",
    "A": "https://raw.githubusercontent.com/aspromatis/zipline_bundle/master/data/csvs/daily/{t}.csv",
    "B": "https://raw.githubusercontent.com/fja05680/brownbear/master/symbol-cache/{t}.csv",
}
B_START = pd.Timestamp("2019-01-03")


def fetch(src, t):
    try:
        raw = urllib.request.urlopen(SRC[src].format(t=t), timeout=30).read()
    except Exception:
        return None
    df = pd.read_csv(io.BytesIO(raw))
    df.columns = [c.lower() for c in df.columns]
    df = df.set_index(pd.to_datetime(df["date"])).sort_index()
    if src == "A":
        return (df.close + df.dividend) / df.close.shift(1) - 1
    return df["adj close"].pct_change()


def build():
    out = {}
    for t in TICKERS:
        c, a, b = fetch("C", t), fetch("A", t), fetch("B", t)
        r = b[b.index >= B_START]
        a = a[a.index < B_START]
        if c is not None:
            c = c[c.index < B_START]
            a = a[a.index > c.index[-1]]
            r = pd.concat([c, a, r])
        else:
            r = pd.concat([a, r])
        out[t] = r[~r.index.duplicated()]
    rets = pd.DataFrame(out).loc["2005-01-04":].dropna()
    return 100 * (1 + rets).cumprod()


if __name__ == "__main__":
    px = build()
    px.index.name = "date"
    px.to_csv(sys.argv[1])
    print(px.shape, px.index[0].date(), "->", px.index[-1].date())
