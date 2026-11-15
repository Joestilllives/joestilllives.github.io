#!/usr/bin/env python3
"""Match NSE symbols to English Wikipedia articles.

1. Exact matches from Wikidata (ISIN or NSE ticker) passed in as a CSV.
2. For the rest, search Wikipedia by cleaned company name and accept the top hit
   only if its title contains the name's distinctive first word and its short
   description says it is a company (bank, manufacturer, ...).

Usage: python3 match_wikipedia.py PANEL.pkl BHAVCOPY.csv EXACT.csv OUT.csv [N]
"""
import csv, json, re, subprocess, sys, time, urllib.parse
import pandas as pd

UA = "market-research-script/0.1 (personal research)"
STOP = {"LTD", "LTD.", "LIMITED", "THE", "CO", "CO.", "OF", "AND", "&", "CORP", "CORPN", "INDIA", "IND",
        "(I)", "(INDIA)", "COMPANY", "INDUSTRIES", "INDS", "INDUSTRY"}
COMPANYISH = re.compile(r"compan|bank|conglomerat|manufactur|corporat|\bfirm\b|enterprise|insur|producer|"
                        r"provider|operator|chain|group|retail|exchange|airline|developer|maker|subsidiar|"
                        r"\bpublic sector\b|holding|business|brand|lender|financ|pharmaceutical|refiner|"
                        r"\bmill|\bplant\b|software|consult|cement|steel|power|energy|logistics|hospital",
                        re.I)


def clean(name):
    n = re.sub(r"\((I|INDIA)\)", " India ", name, flags=re.I)
    n = re.sub(r"\b(LTD\.?|LIMITED)\b", " ", n, flags=re.I)
    n = re.sub(r"\bIND\b", "India", n, flags=re.I)
    n = re.sub(r"\s+", " ", n).strip(" .-")
    return n.title()


def key_words(name):
    """First two distinctive words of the company name (abbreviated words skipped)."""
    words = [w for w in re.sub(r"[().,&-]", " ", name.upper()).split() if w not in STOP and len(w) >= 3]
    return words[:2]


def accept(name, pg):
    title, desc = pg.get("title", ""), pg.get("description", "")
    t = re.sub(r"[-.,&()]", " ", title.lower())
    if not all(w.lower() in t.split() or w.lower() in t for w in key_words(name)) or not key_words(name):
        return False
    if not COMPANYISH.search(desc + " " + title):
        return False
    # must be the Indian company, not a foreign parent with the same name
    return "india" in t or re.search(r"\bIndian?\b", desc) is not None


def search(q):
    params = {"action": "query", "format": "json", "formatversion": "2", "generator": "search",
              "gsrsearch": q, "gsrlimit": "3", "prop": "description", "redirects": "1"}
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode(params) + "&maxlag=5"
    for attempt in range(4):
        r = subprocess.run(["curl", "-sSf", "-m", "30", "-A", UA, url], capture_output=True, text=True)
        if r.returncode == 0:
            pages = json.loads(r.stdout).get("query", {}).get("pages", [])
            return sorted(pages, key=lambda p: p.get("index", 99))
        time.sleep(2 ** (attempt + 1))
    return []


def main(panel, bhav, exact, out, n=1200):
    p = pd.read_pickle(panel)
    med = p.groupby("symbol")["turnover_lacs"].median().sort_values(ascending=False)
    wanted = list(med.index[: int(n)])
    names = {}
    for r in csv.DictReader(open(bhav)):
        if r["SctySrs"] == "EQ":
            names[r["TckrSymb"]] = r["FinInstrmNm"]
    done = {r["symbol"]: r for r in csv.DictReader(open(exact))}
    rows = [{"symbol": s, "article": done[s]["article"].rsplit("/wiki/", 1)[1], "how": "wikidata"}
            for s in wanted if s in done]
    todo = [s for s in wanted if s not in done]
    print(f"{len(rows)} exact, {len(todo)} to search ({sum(s not in names for s in todo)} have no current name)", flush=True)
    for i, s in enumerate(todo):
        if s not in names:
            continue
        q = clean(names[s])
        hit = None
        for query in dict.fromkeys([q, re.sub(r"\bIndia\b", "", q).strip()]):
            for pg in search(query)[:3]:
                if accept(names[s], pg):
                    hit = pg; break
            if hit:
                break
            time.sleep(0.3)
        if hit:
            rows.append({"symbol": s, "article": urllib.parse.quote(hit["title"].replace(" ", "_")), "how": "search",
                         "desc": hit.get("description", "")})
        if i % 100 == 0:
            print(f"  searched {i}/{len(todo)}, matched {len(rows)}", flush=True)
        time.sleep(0.6)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "article", "how", "desc"])
        w.writeheader(); w.writerows(rows)
    print(f"done: {len(rows)} of {len(wanted)} matched", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
