"""Pre-registered India test for Atlas v2-IN (see PREREGISTRATION.md, India section).

usage: python scripts/india_holdout.py
"""
import json
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas.backtest import run_backtest          # noqa: E402
from atlas.data import get_prices                 # noqa: E402
from atlas.metrics import deflated_sharpe, summary  # noqa: E402
from atlas.validation import deep_merge           # noqa: E402

N_TRIALS = 4      # default(5 ETF), default(28 ETF), v2 (US), v2-IN
SLEEVE = 0.20

cfg = tomllib.load(open(ROOT / "config" / "india_v2.toml", "rb"))
px = get_prices(cfg)
res = run_backtest(px, cfg)
ix = res.returns.index[res.weights.abs().sum(axis=1).gt(0).to_numpy().argmax():]  # from first position
s, rf = res.returns.loc[ix], res.rf.loc[ix]
st = summary(s, rf)
stress = run_backtest(px, deep_merge(cfg, {"execution": {
    "commission_bps": 6.0, "half_spread_bps": 30.0, "impact_k": 1.5}}))
st3 = summary(stress.returns.loc[ix], rf)

nifty = px["NIFTYBEES.NS"].pct_change(fill_method=None).reindex(ix).fillna(0.0)
blend = (1 - SLEEVE) * nifty + SLEEVE * s
sn, sb = summary(nifty, rf), summary(blend, rf)

rows = {"v2-IN": st, "Nifty 50": sn, "80% Nifty + 20% v2-IN": sb}
print(f"Universe: {px.shape[1]} NSE ETFs, {ix[0].date()} -> {ix[-1].date()}, cash 6%")
print(pd.DataFrame({k: {m: v[m] for m in ("cagr", "vol", "sharpe", "max_drawdown")} for k, v in rows.items()})
      .T.rename(columns={"sharpe": "sharpe_above_cash"}).to_string(float_format=lambda x: f"{x:.3f}"))
w = res.weights.loc[ix]
print(f"avg invested {w.sum(axis=1).mean():.0%} | turnover {res.turnover.loc[ix].mean()*252:.1f}x/yr | "
      f"cost drag {res.costs.loc[ix].mean()*252:.2%}/yr | corr to Nifty {s.corr(nifty):.2f}")
yr = (1 + pd.DataFrame({"v2-IN": s, "Nifty": nifty, "blend": blend})).resample("YE").prod() - 1
yr.index = yr.index.year
print((yr * 100).round(1).T.to_string())

dsr = deflated_sharpe(s - rf, N_TRIALS)
checks = {
    "P1 blend Sharpe > Nifty Sharpe": sb["sharpe"] > sn["sharpe"],
    "P2 blend max DD shallower than Nifty": sb["max_drawdown"] > sn["max_drawdown"],
    "P3 v2-IN Sharpe above cash > 0 at 3x costs": st3["sharpe"] > 0,
}
print("\nTIER 1 (proceed to paper trading):")
for k, v in checks.items():
    print(f"   {'PASS' if v else 'FAIL'}  {k}")
print(f"   (3x-cost Sharpe {st3['sharpe']:.3f})  => {'PASS' if all(checks.values()) else 'FAIL'}")
print(f"TIER 2 (real money after paper): DSR {dsr:.3f} > 0.95 -> {'PASS' if dsr > 0.95 else 'FAIL'}")
(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "india_holdout.json").write_text(json.dumps(
    {"stats": rows, "stress_sharpe": st3["sharpe"], "dsr": dsr, "tier1": checks,
     "yearly": (yr * 100).round(1).to_dict(orient="index")}, indent=2, default=str))
