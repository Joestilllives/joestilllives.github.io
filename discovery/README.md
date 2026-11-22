# Swanson-style literature-based discovery

`swanson.py` finds hidden A–B–C links in PubMed: substances (A) connected to a target
disease (C) through biological mechanisms (B), where no paper has ever linked A and C directly.
`validate.py` checks how many of those hidden links were studied after the cutoff.

```
python3 swanson.py '"raynaud disease"[mh]' 1985 results.json 0
python3 validate.py results.json 25
```

## Validation on Swanson's own case (papers up to 1985)
- Bridges restricted to biological processes and chemicals (MeSH branches G and D), as
  Swanson did; bridging through other diseases mostly rediscovers known comorbidities.
- Top 25 hidden links: 15 were later studied with Raynaud's (89 papers), vs 10 of 25 random
  lower-ranked candidates (45 papers).
- It predicted that nifedipine's sister drugs would be tried: nicardipine (17 later papers),
  felodipine (5), nisoldipine (3).
- It missed fish oil, Swanson's famous find (5 later papers): the fish-oil papers are a small
  share of the thousands on platelets, and a sample of 800 papers per bridge missed them.

The market version (stocks that historically move with peers that just moved) is in
`india-signals/combined.py` as `peer_ret1`, `peer_gap1`, `peer_gap3`.
