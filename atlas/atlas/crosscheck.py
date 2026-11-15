"""Second-source price verification before trading.

Never send orders on prices from a single unofficial feed. For NSE
instruments, the exchange's own bhavcopy (end-of-day file) is the reference:
every traded symbol's last price must match the official close within a
tolerance, or the run aborts. Fails closed: if the official file cannot be
fetched (not yet published, holiday, network), nothing is traded.
"""
from __future__ import annotations

import io
import urllib.request
import zipfile

import numpy as np
import pandas as pd

BHAV_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{d}_F_0000.csv.zip"


class DataCheckError(RuntimeError):
    pass


def nse_bhavcopy(date: pd.Timestamp) -> pd.Series:
    """Official NSE closing prices for `date`, indexed by symbol (EQ series)."""
    req = urllib.request.Request(BHAV_URL.format(d=date.strftime("%Y%m%d")),
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        raw = urllib.request.urlopen(req, timeout=30).read()
    except Exception as exc:
        raise DataCheckError(f"NSE bhavcopy for {date.date()} unavailable ({exc}); not trading") from exc
    z = zipfile.ZipFile(io.BytesIO(raw))
    df = pd.read_csv(z.open(z.namelist()[0]))
    df = df[df["SctySrs"] == "EQ"]
    return df.set_index("TckrSymb")["ClsPric"].astype(float)


def verify_nse(prices_last: pd.Series, as_of: pd.Timestamp, tol: float = 0.005) -> dict:
    """Compare our last prices (symbols like 'NIFTYBEES.NS') with the official
    close. Raises DataCheckError on any mismatch or missing symbol."""
    official = nse_bhavcopy(as_of)
    report, bad = {}, []
    for sym, p in prices_last.items():
        base = sym.replace(".NS", "")
        if base not in official.index:
            bad.append(f"{sym}: not in bhavcopy")
            continue
        o = official[base]
        dev = abs(p / o - 1) if np.isfinite(p) and o > 0 else np.inf
        report[sym] = {"ours": float(p), "nse": float(o), "dev": float(dev)}
        if dev > tol:
            bad.append(f"{sym}: ours {p:.2f} vs NSE {o:.2f} ({dev:.2%})")
    if bad:
        raise DataCheckError("price cross-check failed: " + "; ".join(bad))
    return report
