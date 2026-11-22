#!/usr/bin/env python3
"""Download daily closes of global factors (commodities, currencies, rates, world
markets, themes) from Yahoo Finance's public chart endpoint.

Usage: python3 factors.py OUT.pkl
"""
import json, subprocess, sys, time
import pandas as pd

UA = "Mozilla/5.0 (compatible; market-research-script/0.1; +https://joestilllives.github.io)"
FACTORS = {
    # energy
    "BZ=F": "Brent crude", "CL=F": "US crude", "NG=F": "Natural gas", "RB=F": "Petrol (US)", "HO=F": "Diesel (US)",
    # metals
    "GC=F": "Gold", "SI=F": "Silver", "HG=F": "Copper", "ALI=F": "Aluminium", "PL=F": "Platinum", "HRC=F": "Steel (US HRC)",
    # crops
    "ZW=F": "Wheat", "ZC=F": "Corn", "ZS=F": "Soybeans", "SB=F": "Sugar", "CT=F": "Cotton", "KC=F": "Coffee",
    "CC=F": "Cocoa", "ZR=F": "Rice",
    # currencies and rates
    "USDINR=X": "Rupee per dollar", "EURINR=X": "Rupee per euro", "DX-Y.NYB": "Dollar index", "CNY=X": "Yuan per dollar",
    "JPY=X": "Yen per dollar", "^TNX": "US 10-year rate", "^IRX": "US 3-month rate",
    # world markets and fear
    "^GSPC": "S&P 500", "^IXIC": "Nasdaq", "^SOX": "Chip stocks", "^VIX": "US fear index", "^HSI": "Hong Kong",
    "000001.SS": "Shanghai", "^N225": "Japan", "^STOXX50E": "Europe", "EEM": "Emerging markets", "^INDIAVIX": "India fear index",
    # themes
    "XLE": "US energy stocks", "XLF": "US financials", "XLV": "US healthcare", "XLK": "US tech", "XLB": "US materials",
    "XLI": "US industrials", "XLY": "US consumer", "XLU": "US utilities", "IBB": "US biotech", "ITA": "US defence",
    "TAN": "Solar stocks", "LIT": "Lithium/batteries", "ACN": "Accenture (IT spending)", "BTC-USD": "Bitcoin",
}


def fetch(sym):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sym.replace('=', '%3D').replace('^', '%5E')}"
           "?period1=1546300800&period2=1800000000&interval=1d")
    for i in range(4):
        r = subprocess.run(["curl", "-sSf", "-m", "60", "-A", UA, url], capture_output=True, text=True)
        if r.returncode == 0:
            res = json.loads(r.stdout)["chart"]["result"]
            if res and res[0].get("timestamp"):
                ts = pd.to_datetime(res[0]["timestamp"], unit="s").normalize()
                close = res[0]["indicators"]["quote"][0]["close"]
                return pd.Series(close, index=ts).dropna().groupby(level=0).last()
            return None
        time.sleep(2 ** (i + 1))
    return None


def main(out):
    cols, missing = {}, []
    for sym, name in FACTORS.items():
        s = fetch(sym)
        if s is None or len(s) < 500:
            missing.append(name)
        else:
            cols[name] = s
        time.sleep(0.8)
    df = pd.DataFrame(cols).sort_index()
    df.to_pickle(out)
    print(f"{df.shape[1]} factors, {df.index.min().date()}..{df.index.max().date()}; missing: {missing}")


if __name__ == "__main__":
    main(*sys.argv[1:])
