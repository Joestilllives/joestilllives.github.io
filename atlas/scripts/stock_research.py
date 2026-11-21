"""Research-window comparison of the pre-registered stock momentum variants.
Data is truncated at 2016-12-31 so no holdout data can enter any calculation.

usage: python scripts/stock_research.py PANEL.pkl
Writes results/stock_choice.json, which must be committed before the holdout runs.
"""
import json
import pickle
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from atlas.stocks import Panel, StockConfig, run_stock_backtest  # noqa: E402

END = "2016-12-31"
p = pickle.load(open(sys.argv[1], "rb"))
cut = lambda f: f.loc[:END]
close = cut(p.close)
p = Panel(close, cut(p.ret), cut(p.value), p.adjustments[p.adjustments.date <= END],
          close.apply(lambda c: c.last_valid_index()))
base = StockConfig()
VARIANTS = {
    "1 top30 equal": base,
    "2 top30 mom/vol": replace(base, risk_adjusted=True),
    "3 top30 inverse-vol": replace(base, weighting="inverse_vol"),
    "4 top30 equal + trend filter": replace(base, trend_filter=True),
    "5 top20 equal": replace(base, n_hold=20),
    "6 top50 equal": replace(base, n_hold=50),
}
rows = {}
for name, cfg in VARIANTS.items():
    res = run_stock_backtest(p, cfg)
    s = res.stats("2006-01-01", END)
    rows[name] = {k: s[k] for k in ("cagr", "vol", "sharpe", "max_drawdown", "turnover_ann", "cost_drag_ann")}
t = pd.DataFrame(rows).T.rename(columns={"sharpe": "sharpe_above_cash"})
print(f"Research window 2006-01-01 -> {END}")
print(t.to_string(float_format=lambda x: f"{x:.3f}"))
best = t["sharpe_above_cash"]
top = best.max()
choice = next(n for n in t.index if best[n] >= top - 0.05)
print(f"\nCHOICE (highest Sharpe; within 0.05 -> lower-numbered): {choice}")
root = Path(__file__).resolve().parent.parent
(root / "results").mkdir(exist_ok=True)
(root / "results" / "stock_choice.json").write_text(json.dumps(
    {"choice": choice, "config": VARIANTS[choice].__dict__, "research": t.round(4).to_dict(orient="index")},
    indent=2))
