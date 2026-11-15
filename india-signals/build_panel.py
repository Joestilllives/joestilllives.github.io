#!/usr/bin/env python3
"""Combine NSE daily files into one table of EQ-series stocks.

Usage: python3 build_panel.py DAILY_DIR OUT.pkl
"""
import glob, os, sys
import numpy as np
import pandas as pd

COLS = {"SYMBOL": "symbol", "SERIES": "series", "DATE1": "date", "PREV_CLOSE": "prev_close",
        "CLOSE_PRICE": "close", "TTL_TRD_QNTY": "volume", "TURNOVER_LACS": "turnover_lacs",
        "DELIV_QTY": "deliv_qty", "DELIV_PER": "deliv_per"}


def read_day(path):
    with open(path, "rb") as f:
        if not f.read(6).startswith(b"SYMBOL"):
            print(f"skipping {os.path.basename(path)}: not a CSV", file=sys.stderr)
            return None
    df = pd.read_csv(path, skipinitialspace=True, dtype=str)
    df.columns = [c.strip() for c in df.columns]
    df = df[list(COLS)].rename(columns=COLS)
    df = df[df["series"].str.strip() == "EQ"].drop(columns="series")
    df["symbol"] = df["symbol"].str.strip()
    df["date"] = pd.to_datetime(df["date"].str.strip(), format="%d-%b-%Y")
    for c in ["prev_close", "close", "volume", "turnover_lacs", "deliv_qty", "deliv_per"]:
        df[c] = pd.to_numeric(df[c].str.strip(), errors="coerce")  # "-" -> NaN
    return df


def main(daily_dir, out):
    files = sorted(glob.glob(os.path.join(daily_dir, "*.csv")))
    panel = pd.concat([read_day(f) for f in files], ignore_index=True)
    panel = panel.dropna(subset=["close", "prev_close"]).sort_values(["symbol", "date"])
    panel = panel.drop_duplicates(["symbol", "date"], keep="last").reset_index(drop=True)
    panel["volume"] = panel["volume"].astype("float64")
    panel.to_pickle(out)
    print(f"{len(files)} days, {panel['symbol'].nunique()} stocks, {len(panel):,} rows, "
          f"{panel['date'].min():%Y-%m-%d} .. {panel['date'].max():%Y-%m-%d}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
