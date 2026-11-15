#!/usr/bin/env python3
"""Download NSE's public daily equity files (prices + delivery %) for a date range.

One file per trading day from nsearchives.nseindia.com, fetched one at a time with
a pause between requests. Weekends are skipped; holidays return 404 and are noted.

Usage: python3 download.py START END OUTDIR    (dates as YYYY-MM-DD)
"""
import datetime as dt, os, subprocess, sys, time

URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{:%d%m%Y}.csv"
UA = "market-research-script/0.1"

def main(start, end, out):
    os.makedirs(out, exist_ok=True)
    holidays = os.path.join(out, "_missing.txt")
    seen_missing = set(open(holidays).read().split()) if os.path.exists(holidays) else set()
    d, end = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    got = miss = 0
    while d <= end:
        if d.weekday() < 5:
            path = os.path.join(out, f"{d:%Y-%m-%d}.csv")
            if not os.path.exists(path) and d.isoformat() not in seen_missing:
                r = subprocess.run(["curl", "-sS", "-m", "60", "-A", UA, "-o", path + ".part",
                                    "-w", "%{http_code}", URL.format(d)], capture_output=True, text=True)
                code = r.stdout.strip()
                if code == "200" and os.path.getsize(path + ".part") > 10000:
                    os.rename(path + ".part", path); got += 1
                else:
                    if os.path.exists(path + ".part"): os.remove(path + ".part")
                    if code == "404":
                        with open(holidays, "a") as f: f.write(d.isoformat() + "\n")
                    miss += 1
                    print(f"{d} -> {code or r.stderr.strip()}", flush=True)
                time.sleep(0.4)
        d += dt.timedelta(days=1)
        if d.day == 1:
            print(f"reached {d}  downloaded={got} missing={miss}", flush=True)
    print(f"done downloaded={got} missing={miss}", flush=True)

if __name__ == "__main__":
    main(*sys.argv[1:4])
