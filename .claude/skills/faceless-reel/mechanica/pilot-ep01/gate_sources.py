"""Sources gate: every claim must have a source, a URL, a saved copy of the source, and a quote that
really appears in that saved copy (fuzzy, because patents are OCR scans). Every beat that states a fact
must be covered by a claim. Exit 1 on any failure."""
import json, re, sys, difflib
spec = json.load(open(sys.argv[1])); bad = 0
norm = lambda s: re.sub(r'[^a-z0-9]', '', s.lower())
def found(quote, text):
    q, t = norm(quote), norm(text)
    if q in t: return 1.0
    best, n = 0, len(q)
    for i in range(0, max(1, len(t) - n), max(1, n // 4)):
        best = max(best, difflib.SequenceMatcher(None, q, t[i:i + n + n // 5]).ratio())
    return best
for c in spec['claims']:
    missing = [k for k in ('claim', 'source', 'url', 'file', 'quote', 'beat') if not c.get(k)]
    if missing:
        print(f"  FAIL  claim '{c.get('claim','?')[:50]}' missing {missing}"); bad += 1; continue
    text = open(c['file'], encoding='utf-8', errors='ignore').read()
    parts = c['quote'] if isinstance(c['quote'], list) else [c['quote']]
    score = min(found(q, text) for q in parts)               # every fragment must be in the source
    ok = score >= 0.85; bad += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  quote match {score:.2f}  [{c['beat']}] {c['claim'][:70]}")
fact_beats = {'parts', 'split', 'turn', 'receipt'}   # beats that state facts (hook/jam/send are framing or follow from claims)
covered = {c['beat'] for c in spec['claims']}
for b in sorted(fact_beats - covered):
    print(f"  FAIL  beat '{b}' states a fact but has no claim"); bad += 1
print(f"  {'PASS' if not bad else 'FAIL'}  sources gate: {len(spec['claims'])} claims, {bad} problems")
sys.exit(1 if bad else 0)
