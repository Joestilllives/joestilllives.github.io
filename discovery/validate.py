#!/usr/bin/env python3
"""Did the hidden links found with literature up to CUTOFF get studied later?

For the top N ranked substances and a random sample of the lower-ranked ones,
count papers pairing the substance with the target published after the cutoff.
Usage: python3 validate.py RESULTS.json [N]
"""
import json, random, sys
import swanson as s


def later(sub, target, cutoff):
    term = f'("{sub}"[nm] OR "{sub}"[mh]) AND {target}'
    return s.count(term, 2026) - s.count(term, cutoff)


def main(path, n=25):
    n = int(n)
    r = json.load(open(path))
    rows, target, cutoff = r["hidden_links"], r["target"], r["cutoff"]
    random.seed(1)
    rest = random.sample(rows[n:], min(n, len(rows) - n))
    out = {}
    for label, group in [("top", rows[:n]), ("random_rest", rest)]:
        res = []
        for x in group:
            k = later(x["substance"], target, cutoff)
            res.append({"substance": x["substance"], "papers_after": k})
        hit = sum(1 for z in res if z["papers_after"] > 0)
        out[label] = {"studied_later": hit, "of": len(res), "rows": res}
        print(f"{label:12}: {hit}/{len(res)} were later studied with {target} "
              f"(total later papers {sum(z['papers_after'] for z in res)})")
    for z in out["top"]["rows"]:
        print(f"   {z['substance'][:50]:50} {z['papers_after']:>5} papers after {cutoff}")
    json.dump(out, open(path.replace(".json", "_validation.json"), "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:])
