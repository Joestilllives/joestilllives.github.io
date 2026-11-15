#!/usr/bin/env python3
"""Match NSE companies to English Wikipedia articles using the full titles dump,
then confirm with a few batched API calls (redirects + short descriptions).

Usage: python3 match_offline.py PANEL.pkl BHAVCOPY.csv EXACT.csv TITLES.gz OUT.csv [N]
"""
import csv, gzip, itertools, json, os, re, subprocess, sys, time, urllib.parse
import pandas as pd
from match_wikipedia import clean, accept, UA

ABBR = {"CORPN": "Corporation", "CORP": "Corporation", "INDS": "Industries", "TECH": "Technologies",
        "TECHNO": "Technologies", "PHARMA": "Pharmaceuticals", "FIN": "Finance", "SER": "Services",
        "SERV": "Services", "SERVS": "Services", "MFG": "Manufacturing", "ENGG": "Engineering",
        "INTL": "International", "CHEM": "Chemicals", "CHEMS": "Chemicals", "HSG": "Housing", "BK": "Bank",
        "LAB": "Laboratories", "LABS": "Laboratories", "PROD": "Products", "INFRA": "Infrastructure",
        "HOLD": "Holdings", "INV": "Investments", "CAP": "Capital", "PWR": "Power", "GEN": "General",
        "NAT": "National", "CO": "Company", "SYS": "Systems", "ELECT": "Electricals", "FERT": "Fertilisers",
        "INSUR": "Insurance", "INS": "Insurance", "DEVP": "Developers", "MOT": "Motors", "TRAN": "Transport"}


def variants(name):
    base = clean(name)
    words = base.split()
    expanded = " ".join(ABBR.get(w.upper().rstrip("."), w) for w in words)
    out = []
    for b in dict.fromkeys([base, expanded]):
        no_india = re.sub(r"\bIndia\b", "", b).strip()
        for core in dict.fromkeys([b, no_india]):
            if not core:
                continue
            out += [core, core + " Limited", core + " Ltd", core + " (company)", core + " India",
                    core + " India Limited", core.replace(" And ", " & "), core.replace(" & ", " and ")]
    return [v.replace(" ", "_").lower() for v in dict.fromkeys(out)]


def api(titles):
    params = {"action": "query", "format": "json", "formatversion": "2", "redirects": "1",
              "prop": "description", "titles": "|".join(titles)}
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params)
    hdr = "/tmp/_wiki_headers.txt"
    for attempt in range(10):
        r = subprocess.run(["curl", "-sS", "-m", "30", "-A", UA, "-D", hdr, url], capture_output=True, text=True)
        head = open(hdr).read() if os.path.exists(hdr) else ""
        codes = re.findall(r"HTTP/\S+ (\d+)", head)
        if codes and codes[-1] == "200":
            return json.loads(r.stdout)
        ra = re.search(r"retry-after: (\d+)", head, re.I)
        time.sleep(int(ra.group(1)) + 1 if ra else 15)
    raise RuntimeError("Wikipedia API kept refusing")


def main(panel, bhav, exact, titles_gz, out, n=1200):
    p = pd.read_pickle(panel)
    wanted = list(p.groupby("symbol")["turnover_lacs"].median().sort_values(ascending=False).index[: int(n)])
    names = {r["TckrSymb"]: r["FinInstrmNm"] for r in csv.DictReader(open(bhav)) if r["SctySrs"] == "EQ"}
    done = {r["symbol"]: r["article"] for r in csv.DictReader(open(exact))}
    cands = {s: variants(names[s]) for s in wanted if s in names and s not in done}
    need = set(itertools.chain.from_iterable(cands.values()))
    found = {}
    with gzip.open(titles_gz, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            t = line.rstrip("\n")
            if t.lower() in need:
                found.setdefault(t.lower(), t)
    hits = {s: [found[v] for v in vs if v in found] for s, vs in cands.items()}
    hits = {s: h for s, h in hits.items() if h}
    print(f"{len(done)} from Wikidata; {len(hits)} of {len(cands)} others have a title match in the dump", flush=True)

    # resolve redirects and fetch descriptions, 50 titles per request
    uniq = sorted(set(itertools.chain.from_iterable(hits.values())))
    info = {}
    for i in range(0, len(uniq), 50):
        batch = [t.replace("_", " ") for t in uniq[i:i + 50]]
        d = api(batch).get("query", {})
        back = {}
        for r in d.get("normalized", []) + d.get("redirects", []):
            back.setdefault(r["to"], []).append(back.get(r["from"], [r["from"]])[0] if r["from"] in back else r["from"])
        for pg in d.get("pages", []):
            if pg.get("missing"):
                continue
            for src in back.get(pg["title"], []) + [pg["title"]]:
                info[src] = {"title": pg["title"], "description": pg.get("description", "")}
        time.sleep(1.5)
    rows = [{"symbol": s, "article": urllib.parse.unquote(a.rsplit("/wiki/", 1)[1]), "how": "wikidata", "desc": ""}
            for s, a in done.items() if s in wanted]
    for s, ts in hits.items():
        for t in ts:
            pg = info.get(t.replace("_", " "))
            if pg and accept(names[s], pg):
                rows.append({"symbol": s, "article": pg["title"].replace(" ", "_"), "how": "titles", "desc": pg["description"]})
                break
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "article", "how", "desc"])
        w.writeheader(); w.writerows(rows)
    print(f"done: {len(rows)} of {len(wanted)} stocks matched")


if __name__ == "__main__":
    main(*sys.argv[1:])
