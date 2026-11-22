#!/usr/bin/env python3
"""Swanson-style chains: does a foreign parent (or a US-listed version) move before
its Indian listed company?

A = the foreign stock moves (it trades in Europe/US, which close AFTER India)
B = ownership / it is the same company
C = does the Indian stock follow on the NEXT NSE trading day?

For each pair: correlation of the foreign day-t move with the Indian day t+1 move
(both relative to their own market), and a simple rule's return before costs:
own the Indian stock next day after the foreign stock beat its market, step aside
after it lagged.

Usage: python3 leadlag.py PANEL.pkl FUNDS.txt OUT.json
"""
import json, subprocess, sys, time
import numpy as np
import pandas as pd
from backtest import prepare
from factors import fetch

# Indian symbol: (foreign ticker, foreign market index, relationship)
PAIRS = {
    "HINDUNILVR": ("ULVR.L", "^FTSE", "Unilever owns ~62%"), "NESTLEIND": ("NESN.SW", "^SSMI", "Nestle owns ~63%"),
    "SIEMENS": ("SIE.DE", "^GDAXI", "Siemens owns ~69%"), "ABB": ("ABBN.SW", "^SSMI", "ABB owns 75%"),
    "CASTROLIND": ("BP.L", "^FTSE", "BP owns ~51%"), "GLAXO": ("GSK.L", "^FTSE", "GSK owns ~75%"),
    "COLPAL": ("CL", "^GSPC", "Colgate owns ~51%"), "PGHH": ("PG", "^GSPC", "P&G owns ~70%"),
    "GILLETTE": ("PG", "^GSPC", "P&G owns ~75%"), "HONAUT": ("HON", "^GSPC", "Honeywell owns 75%"),
    "3MINDIA": ("MMM", "^GSPC", "3M owns 75%"), "CUMMINSIND": ("CMI", "^GSPC", "Cummins owns 51%"),
    "WHIRLPOOL": ("WHR", "^GSPC", "Whirlpool owns ~51-75%"), "TIMKEN": ("TKR", "^GSPC", "Timken owns ~51%"),
    "PFIZER": ("PFE", "^GSPC", "Pfizer owns ~64%"), "SANOFI": ("SAN.PA", "^FCHI", "Sanofi owns ~60%"),
    "ABBOTINDIA": ("ABT", "^GSPC", "Abbott owns ~75%"), "LINDEINDIA": ("LIN", "^GSPC", "Linde owns 75%"),
    "BASF": ("BAS.DE", "^GDAXI", "BASF owns 73%"), "BAYERCROP": ("BAYN.DE", "^GDAXI", "Bayer owns ~71%"),
    "ASTRAZEN": ("AZN.L", "^FTSE", "AstraZeneca owns 75%"), "SCHNEIDER": ("SU.PA", "^FCHI", "Schneider owns ~70%"),
    "GRINDWELL": ("SGO.PA", "^FCHI", "Saint-Gobain owns ~58%"), "INGERRAND": ("IR", "^GSPC", "Ingersoll Rand owns 75%"),
    "OFSS": ("ORCL", "^GSPC", "Oracle owns ~73%"), "ITC": ("BATS.L", "^FTSE", "BAT owns ~23-29%"),
    "SKFINDIA": ("SKF-B.ST", "^OMX", "SKF owns ~53%"), "ESABINDIA": ("ESAB", "^GSPC", "ESAB owns ~74%"),
    "VESUVIUS": ("VSVS.L", "^FTSE", "Vesuvius owns ~56%"), "HEIDELBERG": ("HEI.DE", "^GDAXI", "Heidelberg owns ~69%"),
    # US-listed versions of the same Indian company (ADRs)
    "INFY": ("INFY", "^GSPC", "ADR of Infosys"), "WIPRO": ("WIT", "^GSPC", "ADR of Wipro"),
    "HDFCBANK": ("HDB", "^GSPC", "ADR of HDFC Bank"), "ICICIBANK": ("IBN", "^GSPC", "ADR of ICICI Bank"),
    "DRREDDY": ("RDY", "^GSPC", "ADR of Dr Reddy's"),
}


def main(panel, funds_txt, out):
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    nse_mkt = p[p["liquid"]].groupby("date")["ret"].mean()
    nse = p.pivot_table(index="date", columns="symbol", values="ret")
    cache = {}
    def get(t):
        if t not in cache:
            cache[t] = fetch(t)
            time.sleep(0.8)
        return cache[t]
    res, legs = {}, []
    for sym, (ft, fmkt, rel) in PAIRS.items():
        if sym not in nse:
            continue
        a, m = get(ft), get(fmkt)
        if a is None or m is None:
            print(f"{sym}: no data for {ft}")
            continue
        fx = (np.log(a).diff() - np.log(m).diff()).dropna()         # foreign stock vs its market, day t
        own = (nse[sym] - nse_mkt).dropna()                          # Indian stock vs NSE, day t
        # foreign day t -> first NSE day AFTER t (US/Europe close after India)
        nxt = own.copy(); nxt.index = nxt.index - pd.Timedelta(days=0)
        df = pd.DataFrame({"f": fx}).join(own.rename("same"), how="left")
        nse_dates = own.index
        pos = nse_dates.searchsorted(df.index, side="right")
        df["next"] = [own.iloc[i] if i < len(own) else np.nan for i in pos]
        df = df.dropna(subset=["f", "next"])
        df = df[df.index >= "2020-03-01"]
        rule = np.where(df["f"] > 0, df["next"], 0.0) - np.where(df["f"] <= 0, 0.0, 0.0)
        big = df[df["f"].abs() > 2 * df["f"].std()]
        res[sym] = {"foreign": ft, "relationship": rel, "days": int(len(df)),
                    "corr_next_day": round(float(df["f"].corr(df["next"])), 3),
                    "big_moves": int(len(big)),
                    "next_day_after_big_up_pct": round(float(big.loc[big.f > 0, "next"].mean() * 100), 2) if (big.f > 0).any() else None,
                    "next_day_after_big_down_pct": round(float(big.loc[big.f < 0, "next"].mean() * 100), 2) if (big.f < 0).any() else None}
        legs.append(pd.Series(np.sign(df["f"]) * df["next"], index=df.index, name=sym))
    L = pd.concat(legs, axis=1)
    combo = L.mean(axis=1).dropna()
    for label, part in [("2020-23", combo[combo.index < "2023-07-01"]), ("2023-26", combo[combo.index >= "2023-07-01"])]:
        res["_all_pairs_" + label] = {"days": int(len(part)), "per_day_pct": round(float(part.mean() * 100), 3),
                                      "t": round(float(part.mean() / part.std() * np.sqrt(len(part))), 2),
                                      "per_year_before_costs_pct": round(float(part.mean() * 250 * 100), 1)}
    json.dump(res, open(out, "w"), indent=1)
    print(f"{'Indian stock':12} {'foreign':9} {'corr':>6} {'big moves':>9} {'next day after big up':>22} {'after big down':>15}")
    for s, r in sorted([(k, v) for k, v in res.items() if not k.startswith("_")], key=lambda x: -x[1]["corr_next_day"]):
        print(f"{s:12} {r['foreign']:9} {r['corr_next_day']:+6.3f} {r['big_moves']:>9} {r['next_day_after_big_up_pct'] or 0:+21.2f}% {r['next_day_after_big_down_pct'] or 0:+14.2f}%")
    for k in ["_all_pairs_2020-23", "_all_pairs_2023-26"]:
        print(k, res[k])


if __name__ == "__main__":
    main(*sys.argv[1:])
