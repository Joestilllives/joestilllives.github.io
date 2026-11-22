#!/usr/bin/env python3
"""Swanson-style literature-based discovery (open discovery, A-B-C) on PubMed.

Start from a target C (a disease). Using only papers published up to CUTOFF:
  1. B terms: MeSH topics that appear unusually often in C's papers (lift over PubMed).
  2. A terms: substances (MeSH chemical list) appearing in papers about those B topics.
  3. Keep A only if it links through 2+ different B topics AND has (almost) no paper
     with C itself: a connection that exists in the literature but nobody has made.
  4. Rank by how many strong B links A has, penalising very common substances.

Usage: python3 swanson.py "raynaud disease[mh]" 1985 OUT.json [max_direct]
"""
import json, math, re, subprocess, sys, time, urllib.parse
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = "literature-discovery-script"
GENERIC = {"Humans", "Male", "Female", "Adult", "Middle Aged", "Aged", "Aged, 80 and over", "Child", "Adolescent",
           "Animals", "Infant", "Child, Preschool", "Rats", "Mice", "Dogs", "Rabbits", "Cats", "Time Factors",
           "In Vitro Techniques", "Case Reports", "English Abstract", "Follow-Up Studies", "Clinical Trials as Topic",
           "Prognosis", "Retrospective Studies", "Prospective Studies", "Rats, Inbred Strains", "Cattle", "Swine",
           "Guinea Pigs", "Methods", "Statistics as Topic", "Kinetics", "Reference Values", "Age Factors",
           "Sex Factors", "Double-Blind Method", "Comparative Study", "Research Support, Non-U.S. Gov't"}
_last = [0.0]


def call(endpoint, params, tries=6):
    params = {**params, "tool": TOOL}
    url = EUTILS + endpoint + "?" + urllib.parse.urlencode(params)
    for i in range(tries):
        wait = 0.36 - (time.time() - _last[0])  # stay under NCBI's 3 requests/second
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        r = subprocess.run(["curl", "-sSf", "-m", "60", url], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout
        time.sleep(2 ** i)
    raise RuntimeError(f"PubMed request failed: {endpoint} {params.get('term', '')[:80]}")


def dated(term, cutoff):
    return {"term": term, "datetype": "pdat", "mindate": "1800", "maxdate": str(cutoff)}


def count(term, cutoff):
    j = json.loads(call("esearch.fcgi", {**dated(term, cutoff), "db": "pubmed", "retmode": "json", "rettype": "count"}))
    return int(j["esearchresult"]["count"])


def fetch_terms(term, cutoff, limit):
    """MeSH descriptors and chemical substances for up to `limit` papers."""
    j = json.loads(call("esearch.fcgi", {**dated(term, cutoff), "db": "pubmed", "retmode": "json",
                                         "retmax": str(limit), "sort": "relevance"}))
    ids = j["esearchresult"]["idlist"]
    docs = []
    for i in range(0, len(ids), 200):
        xml = call("efetch.fcgi", {"db": "pubmed", "retmode": "xml", "id": ",".join(ids[i:i + 200])})
        root = ET.fromstring(xml)
        for art in root.iter("PubmedArticle"):
            mesh = {d.text for d in art.iter("DescriptorName") if d.text}
            chems = {c.text for c in art.iter("NameOfSubstance") if c.text}
            docs.append((mesh - GENERIC, chems))
    return docs


_trees = {}


def mesh_branches(name):
    """MeSH tree letters for a descriptor: C = disease, G = biological process, D = chemical, ..."""
    if name not in _trees:
        j = json.loads(call("esearch.fcgi", {"db": "mesh", "retmode": "json", "term": f'"{name}"[mh]'}))
        ids = j["esearchresult"]["idlist"][:1]
        letters = set()
        if ids:
            sj = json.loads(call("esummary.fcgi", {"db": "mesh", "retmode": "json", "id": ids[0]}))
            for link in sj.get("result", {}).get(ids[0], {}).get("ds_idxlinks", []):
                if link.get("treenum"):
                    letters.add(link["treenum"][0])
        _trees[name] = letters
    return _trees[name]


def q(name):
    return f'"{name}"[mh]'


def main(target, cutoff, out, max_direct=0):
    cutoff, max_direct = int(cutoff), int(max_direct)
    total = count("all[sb]", cutoff)
    n_c = count(target, cutoff)
    print(f"PubMed up to {cutoff}: {total:,} papers; target {target}: {n_c:,}", flush=True)

    # 1. B topics: over-represented in C's papers
    c_docs = fetch_terms(target, cutoff, 2000)
    freq = Counter(t for mesh, _ in c_docs for t in mesh)
    target_name = re.sub(r'\[.*?\]|"', "", target).strip().lower()
    cands = [(t, k) for t, k in freq.items() if k >= 4 and t.lower() != target_name]
    lifts = []
    for t, k in sorted(cands, key=lambda x: -x[1])[:150]:
        # Swanson bridged through mechanisms, not other diseases: keep biological
        # processes (G) and chemicals/substances (D) only
        if not (mesh_branches(t) & {"G", "D"}) or (mesh_branches(t) & {"C"}):
            continue
        n_b = count(q(t), cutoff)
        if n_b < 30:
            continue
        lift = (k / len(c_docs)) / (n_b / total)
        lifts.append((t, k, n_b, lift))
    B = sorted([x for x in lifts if x[3] >= 2], key=lambda x: -x[1] * math.log(x[3]))[:40]
    print(f"{len(B)} B topics, e.g.:", ", ".join(f"{t} (x{l:.0f})" for t, _, _, l in B[:12]), flush=True)

    # 2. A candidates: substances in papers about each B
    links = defaultdict(dict)
    for t, k, n_b, lift in B:
        docs = fetch_terms(q(t), cutoff, 800)
        cc = Counter(c for _, chems in docs for c in chems)
        for a, n in cc.items():
            if n >= 2:
                links[a][t] = (n / len(docs)) * math.log(lift)
    multi = {a: bs for a, bs in links.items() if len(bs) >= 2}
    print(f"{len(multi)} substances link to C through 2+ B topics", flush=True)

    # 3. keep hidden links only, 4. rank
    pre = sorted(multi, key=lambda a: -sum(multi[a].values()))[:250]
    rows = []
    for a in pre:
        term = f'"{a}"[nm] OR "{a}"[mh]'
        direct = count(f"({term}) AND {target}", cutoff)
        if direct > max_direct:
            continue
        n_a = count(term, cutoff)
        score = sum(multi[a].values()) / math.log10(n_a + 100)
        rows.append({"substance": a, "score": round(score, 4), "b_links": len(multi[a]),
                     "via": sorted(multi[a], key=lambda b: -multi[a][b])[:5], "papers_with_target": direct,
                     "papers_total": n_a})
    rows.sort(key=lambda r: -r["score"])
    json.dump({"target": target, "cutoff": cutoff, "b_topics": [{"topic": t, "papers_with_target": k, "lift": round(l, 1)}
               for t, k, _, l in B], "hidden_links": rows}, open(out, "w"), indent=1)
    print(f"\nTop hidden links for {target} (no paper connected them by {cutoff}):")
    for i, r in enumerate(rows[:25], 1):
        print(f"{i:3}. {r['substance'][:45]:45} score {r['score']:.3f}  via {r['b_links']} topics: {', '.join(r['via'][:3])}")


if __name__ == "__main__":
    main(*sys.argv[1:])
