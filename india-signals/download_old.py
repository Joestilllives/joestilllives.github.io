#!/usr/bin/env python3
"""Download NSE daily prices (old bhavcopy) and delivery (MTO files) for 2016-2019 and
write them in the same layout as the newer sec_bhavdata_full files, so build_panel.py
reads them unchanged. Resumable; one request at a time with a short pause.

Usage: python3 download_old.py START END OUTDIR      (dates YYYY-MM-DD)
"""
import datetime as dt, io, os, subprocess, sys, time, zipfile
import pandas as pd

HOST = "https://archives.nseindia.com/"
UA = "market-research-script/0.1 (https://joestilllives.github.io; personal research)"


def get(path):
    r = subprocess.run(["curl", "-sS", "--http1.1", "-m", "90", "-A", UA, "-w", "%{http_code}", "-o", "-", HOST + path],
                       capture_output=True)
    return r.stdout[-3:].decode(errors="replace"), r.stdout[:-3]


def main(start, end, outdir):
    os.makedirs(outdir, exist_ok=True)
    d, end = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    got = 0
    while d <= end:
        out = os.path.join(outdir, f"{d}.csv")
        if d.weekday() < 5 and not os.path.exists(out) and not os.path.exists(out + ".none"):
            mon = d.strftime("%b").upper()
            code, body = get(f"content/historical/EQUITIES/{d:%Y}/{mon}/cm{d:%d}{mon}{d:%Y}bhav.csv.zip")
            if code == "200" and body[:2] == b"PK":
                with zipfile.ZipFile(io.BytesIO(body)) as z:
                    b = pd.read_csv(z.open(z.namelist()[0]), dtype=str)
                b.columns = [c.strip() for c in b.columns]
                time.sleep(0.3)
                c2, mto = get(f"archives/equities/mto/MTO_{d:%d%m%Y}.DAT")
                deliv = pd.DataFrame(columns=["SYMBOL", "SERIES", "DELIV_QTY", "DELIV_PER"])
                if c2 == "200":
                    lines = [l.split(",") for l in mto.decode(errors="replace").splitlines() if l.startswith("20,")]
                    deliv = pd.DataFrame([(x[2].strip(), x[3].strip(), x[5].strip(), x[6].strip()) for x in lines if len(x) >= 7],
                                         columns=["SYMBOL", "SERIES", "DELIV_QTY", "DELIV_PER"])
                b["SYMBOL"], b["SERIES"] = b["SYMBOL"].str.strip(), b["SERIES"].str.strip()
                m = b.merge(deliv, on=["SYMBOL", "SERIES"], how="left")
                o = pd.DataFrame({
                    "SYMBOL": m["SYMBOL"], "SERIES": m["SERIES"],
                    "DATE1": pd.to_datetime(m["TIMESTAMP"].str.strip(), format="%d-%b-%Y").dt.strftime("%d-%b-%Y"),
                    "PREV_CLOSE": m["PREVCLOSE"], "OPEN_PRICE": m["OPEN"], "HIGH_PRICE": m["HIGH"], "LOW_PRICE": m["LOW"],
                    "LAST_PRICE": m["LAST"], "CLOSE_PRICE": m["CLOSE"], "AVG_PRICE": "",
                    "TTL_TRD_QNTY": m["TOTTRDQTY"],
                    "TURNOVER_LACS": (pd.to_numeric(m["TOTTRDVAL"], errors="coerce") / 1e5).round(2),
                    "NO_OF_TRADES": m.get("TOTALTRADES", ""), "DELIV_QTY": m["DELIV_QTY"].fillna("-"),
                    "DELIV_PER": m["DELIV_PER"].fillna("-")})
                o.to_csv(out + ".part", index=False)
                os.rename(out + ".part", out)
                got += 1
            elif code in ("404", "403"):
                open(out + ".none", "w").close()   # holiday (or not published)
            else:
                print(f"{d}: HTTP {code}", flush=True)
            time.sleep(0.4)
        d += dt.timedelta(days=1)
        if d.day == 1 and d.month in (1, 7):
            print(f"reached {d}, {got} days saved", flush=True)
    print(f"done: {got} days saved", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
