#!/usr/bin/env python3
"""Download NSE futures & options daily files and condense them per stock per day.

For every stock with derivatives: futures open interest (all expiries), futures
volume, put and call open interest, options volume. Each day's zip is condensed on
arrival and deleted, so only a small table is kept. Resumable.

Old format (to early Jul 2024): content/historical/DERIVATIVES/YYYY/MON/foDDMONYYYYbhav.csv.zip
New format (from Jul 2024):     content/fo/BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip

Usage: python3 fo_download.py START END OUTDIR
"""
import datetime as dt, io, os, subprocess, sys, time, zipfile
import pandas as pd

HOST = "https://archives.nseindia.com/"
UA = "market-research-script/0.1 (https://joestilllives.github.io; personal research)"


def get(path):
    r = subprocess.run(["curl", "-sS", "--http1.1", "-m", "90", "-A", UA, "-w", "%{http_code}", "-o", "-", HOST + path],
                       capture_output=True)
    body, code = r.stdout[:-3], r.stdout[-3:].decode(errors="replace")
    return code, body


def condense(df, new):
    if new:
        df = df.rename(columns={"TckrSymb": "symbol", "FinInstrmTp": "kind", "OptnTp": "opt",
                                "OpnIntrst": "oi", "TtlTradgVol": "vol"})
        df = df[df["kind"].isin(["STF", "STO"])]
        df["kind"] = df["kind"].map({"STF": "FUT", "STO": "OPT"})
    else:
        df.columns = [c.strip() for c in df.columns]
        df = df.rename(columns={"SYMBOL": "symbol", "INSTRUMENT": "kind", "OPTION_TYP": "opt",
                                "OPEN_INT": "oi", "CONTRACTS": "vol"})
        df = df[df["kind"].isin(["FUTSTK", "OPTSTK"])]
        df["kind"] = df["kind"].map({"FUTSTK": "FUT", "OPTSTK": "OPT"})
    df["symbol"] = df["symbol"].str.strip()
    df["opt"] = df["opt"].astype(str).str.strip()
    for c in ["oi", "vol"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    fut = df[df["kind"] == "FUT"].groupby("symbol")[["oi", "vol"]].sum().add_prefix("fut_")
    opt = df[df["kind"] == "OPT"]
    put = opt[opt["opt"] == "PE"].groupby("symbol")["oi"].sum().rename("put_oi")
    call = opt[opt["opt"] == "CE"].groupby("symbol")["oi"].sum().rename("call_oi")
    ov = opt.groupby("symbol")["vol"].sum().rename("opt_vol")
    return pd.concat([fut, put, call, ov], axis=1).fillna(0).reset_index()


def main(start, end, outdir):
    os.makedirs(outdir, exist_ok=True)
    d, end = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    got = 0
    while d <= end:
        out = os.path.join(outdir, f"{d}.csv")
        if d.weekday() < 5 and not os.path.exists(out) and not os.path.exists(out + ".none"):
            new = d >= dt.date(2024, 7, 8)
            mon = d.strftime("%b").upper()
            path = (f"content/fo/BhavCopy_NSE_FO_0_0_0_{d:%Y%m%d}_F_0000.csv.zip" if new else
                    f"content/historical/DERIVATIVES/{d:%Y}/{mon}/fo{d:%d}{mon}{d:%Y}bhav.csv.zip")
            code, body = get(path)
            if code == "200" and body[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(body)) as z:
                    df = pd.read_csv(z.open(z.namelist()[0]), dtype=str)
                df = condense(df, new)
                df.insert(0, "date", d.isoformat())
                df.to_csv(out, index=False)
                got += 1
            elif code == "404":
                open(out + ".none", "w").close()
            else:
                print(f"{d}: HTTP {code}", flush=True)
            time.sleep(0.4)
        d += dt.timedelta(days=1)
        if d.day == 1 and d.month in (1, 4, 7, 10):
            print(f"reached {d}, {got} days saved", flush=True)
    print(f"done: {got} days saved", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
