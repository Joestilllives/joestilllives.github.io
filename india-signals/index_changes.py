#!/usr/bin/env python3
"""NIFTY 50 additions and removals (from the Wikipedia table) and what the stocks did
in the month before the change took effect and the 1 and 3 months after, against the
average liquid company. Usage: python3 index_changes.py WIKITEXT PANEL.pkl FUNDS.txt BHAVCOPY.csv ARTICLES.csv"""
import csv, re, sys
import numpy as np
import pandas as pd
from backtest import prepare


def parse(path):
    t = open(path, encoding="utf-8").read()
    t = t[t.index("==Index changes=="):]
    t = t[:t.index("|}")]
    cells, rows, carry = [], [], {}
    for block in t.split("\n|-")[1:]:
        lines = [l for l in block.split("\n") if l.startswith("|") and not l.startswith("|}")]
        vals = []
        for l in lines:
            l = re.sub(r"<ref.*?(</ref>|/>)", "", l[1:]).strip()
            m = re.match(r'\s*rowspan="?(\d+)"?\s*\|(.*)', l)
            span, v = (int(m.group(1)), m.group(2).strip()) if m else (1, l)
            vals.append((v, span))
        if len(vals) < 2:
            continue
        out, inn = vals[0][0], vals[1][0]
        date = None
        for v, span in vals[2:]:
            if re.search(r"\d{4}", v):
                date = v
                if span > 1:
                    carry = {"date": v, "left": span - 1}
                break
        if date is None and carry.get("left", 0) > 0:
            date = carry["date"]; carry["left"] -= 1
        link = lambda s: (re.findall(r"\[\[([^\]|]+)", s) or [s])[0].strip()
        rows.append({"removed": link(out), "added": link(inn), "date": date})
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=True)
    return df.dropna(subset=["date"])


def main(wikitext, panel, funds_txt, bhav, articles):
    ch = parse(wikitext)
    ch = ch[ch["date"] >= "2020-04-01"]
    art = {r["article"].replace("_", " ").lower(): r["symbol"] for r in csv.DictReader(open(articles))}
    names = {r["FinInstrmNm"].lower(): r["TckrSymb"] for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    def sym(name):
        n = name.lower()
        if n in art: return art[n]
        key = re.sub(r"\b(limited|ltd|india|company|corporation|the)\b|[^a-z ]", "", n).split()
        for full, s in names.items():
            if key and all(k in full for k in key[:2]):
                return s
        return None
    funds = {l.strip() for l in open(funds_txt) if l.strip() and not l.startswith("#")}
    raw = pd.read_pickle(panel)
    p = prepare(raw[~raw["symbol"].isin(funds)])
    lp = p.pivot_table(index="date", columns="symbol", values="logidx").ffill()
    mkt = np.log1p(p[p["liquid"]].groupby("date")["ret"].mean()).cumsum().reindex(lp.index).ffill().fillna(0)
    dates = lp.index
    rows = []
    for r in ch.itertuples():
        for side, name in [("added", r.added), ("removed", r.removed)]:
            s = sym(name)
            if not s or s not in lp:
                rows.append({"side": side, "company": name, "symbol": None, "date": r.date.date()}); continue
            k = dates.searchsorted(r.date)
            row = {"side": side, "company": name, "symbol": s, "date": r.date.date()}
            for label, a, b in [("month before", -21, 0), ("month after", 0, 21), ("3 months after", 0, 63)]:
                if k + a < 0 or k + b >= len(dates):
                    row[label] = np.nan; continue
                row[label] = np.expm1(lp[s].iloc[k + b] - lp[s].iloc[k + a]) - np.expm1(mkt.iloc[k + b] - mkt.iloc[k + a])
            rows.append(row)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False, float_format=lambda x: f"{x*100:+.1f}%"))
    print()
    for side, g in df.dropna(subset=["symbol"]).groupby("side"):
        print(side, f"n={len(g)}", "  ".join(f"{c}: mean {g[c].mean()*100:+.1f}%, median {g[c].median()*100:+.1f}%, positive {(g[c].dropna()>0).mean()*100:.0f}%"
              for c in ["month before", "month after", "3 months after"]))


if __name__ == "__main__":
    main(*sys.argv[1:])
