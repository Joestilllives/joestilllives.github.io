"""Download NSE equity bhavcopies (every trading day, every listed stock) into one
survivorship-free long file: date, symbol, close, prevclose, value (Rs traded).

Includes stocks that were later delisted, merged or suspended, which is the
point: a stock universe built from today's index members flatters backtests.

NOTE: bhavcopy PREVCLOSE is NOT adjusted for bonuses/splits. Adjustment is
done downstream (atlas/stocks.py).

usage: python scripts/build_nse_stocks.py OUT.csv.gz [start] [end]
"""
import io
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

OLD = "https://nsearchives.nseindia.com/content/historical/EQUITIES/{y}/{m}/cm{d}bhav.csv.zip"
NEW = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{ymd}_F_0000.csv.zip"
UA = {"User-Agent": "Mozilla/5.0"}


def _get(url):
    for attempt in range(4):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40).read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def fetch_day(day: pd.Timestamp):
    if day < pd.Timestamp("2024-07-08"):
        raw = _get(OLD.format(y=day.year, m=day.strftime("%b").upper(), d=day.strftime("%d%b%Y").upper()))
        if raw is None:
            return None
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]))
        df.columns = [c.strip() for c in df.columns]
        df = df[df["SERIES"].astype(str).str.strip() == "EQ"]
        out = pd.DataFrame({"symbol": df["SYMBOL"].str.strip(), "close": df["CLOSE"],
                            "prevclose": df["PREVCLOSE"], "value": df["TOTTRDVAL"]})
    else:
        raw = _get(NEW.format(ymd=day.strftime("%Y%m%d")))
        if raw is None:
            return None
        z = zipfile.ZipFile(io.BytesIO(raw))
        df = pd.read_csv(z.open(z.namelist()[0]))
        df = df[df["SctySrs"].astype(str).str.strip() == "EQ"]
        out = pd.DataFrame({"symbol": df["TckrSymb"].str.strip(), "close": df["ClsPric"],
                            "prevclose": df["PrvsClsgPric"], "value": df["TtlTrfVal"]})
    out.insert(0, "date", day.strftime("%Y-%m-%d"))
    return out


def main():
    out_path = sys.argv[1]
    start = sys.argv[2] if len(sys.argv) > 2 else "2005-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else pd.Timestamp.today().strftime("%Y-%m-%d")
    days = pd.bdate_range(start, end)
    frames, done = [], 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        for res in ex.map(fetch_day, days):
            done += 1
            if res is not None:
                frames.append(res)
            if done % 500 == 0:
                print(f"{done}/{len(days)} days, {len(frames)} trading days", flush=True)
    data = pd.concat(frames, ignore_index=True)
    data.to_csv(out_path, index=False, compression="gzip")
    print(f"wrote {out_path}: {len(data):,} rows, {data.symbol.nunique():,} symbols, "
          f"{data.date.nunique():,} trading days {data.date.min()} -> {data.date.max()}")


if __name__ == "__main__":
    main()
