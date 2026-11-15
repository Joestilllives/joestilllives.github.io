#!/usr/bin/env python3
"""List liquid NSE stocks that had a "frenzy" day in the last few sessions:
volume 3x+ its 20-day average while delivery % was 15+ points below its usual level.
Historically (2020-2026) these stocks did worse than similar-sized stocks over the
following week to three months.

Usage: python3 scan.py PANEL.pkl BHAVCOPY.csv OUT.json [SESSIONS]
"""
import csv, json, sys
import pandas as pd
from backtest import prepare


def main(panel, bhav, out, sessions=5):
    sessions = int(sessions)
    names = {r["TckrSymb"]: r["FinInstrmNm"].title() for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    p = prepare(pd.read_pickle(panel))
    last = sorted(p["date"].unique())[-sessions:]
    recent = p[p["date"].isin(last) & p["liquid"]]
    hits = recent[(recent["vol_x"] >= 3) & (recent["deliv_jump"] <= -15)].sort_values(["date", "vol_x"], ascending=[False, False])
    latest_close = p[p["date"] == last[-1]].set_index("symbol")["close"]
    rows = []
    for r in hits.itertuples():
        since = latest_close.get(r.symbol)
        rows.append({
            "symbol": r.symbol, "company": names.get(r.symbol, r.symbol),
            "frenzy_date": r.date.strftime("%Y-%m-%d"),
            "volume_x_usual": round(float(r.vol_x), 1),
            "delivery_pct": round(float(r.deliv_per), 1), "usual_delivery_pct": round(float(r.deliv_avg60), 1),
            "day_change_pct": round(float(r.ret) * 100, 1),
            "traded_value_cr": round(float(r.turnover_lacs) / 100, 1),
            "close_that_day": round(float(r.close), 2),
            "close_latest": round(float(since), 2) if since is not None else None,
            "latest_session": last[-1].strftime("%Y-%m-%d"),
        })
    json.dump(rows, open(out, "w"), indent=1)
    print(f"{len(rows)} frenzy days among liquid stocks in the {sessions} sessions to {last[-1]:%Y-%m-%d}")
    for x in rows[:15]:
        print(f"  {x['frenzy_date']} {x['symbol']:12} vol {x['volume_x_usual']:>5}x  delivery {x['delivery_pct']:>5}% (usual {x['usual_delivery_pct']}%)  day {x['day_change_pct']:+}%")


if __name__ == "__main__":
    main(*sys.argv[1:])
