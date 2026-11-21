"""The one holdout run for the stock momentum sleeve (PREREGISTRATION.md, India stocks).
Reads the locked choice from results/stock_choice.json.

usage: python scripts/stock_holdout.py PANEL.pkl
"""
import json
import pickle
import sys
import tomllib
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas.backtest import run_backtest                   # noqa: E402
from atlas.data import get_prices                          # noqa: E402
from atlas.metrics import deflated_sharpe, summary         # noqa: E402
from atlas.stocks import StockConfig, run_stock_backtest   # noqa: E402

H0, H1 = "2017-01-01", "2026-11-20"
N_TRIALS = 10
lock = json.loads((ROOT / "results" / "stock_choice.json").read_text())
cfg = StockConfig(**lock["config"])
p = pickle.load(open(sys.argv[1], "rb"))

res = run_stock_backtest(p, cfg)
res2 = run_stock_backtest(p, replace(cfg, fee_bps=cfg.fee_bps * 2, half_spread_bps=cfg.half_spread_bps * 2,
                                     impact_k=cfg.impact_k * 2))
res_tax = run_stock_backtest(p, replace(cfg, tax=True))

icfg = tomllib.load(open(ROOT / "config" / "india_v2.toml", "rb"))
etf_px = get_prices(icfg)
v2 = run_backtest(etf_px, icfg).returns
nifty = etf_px["NIFTYBEES.NS"].pct_change(fill_method=None)

ix = res.returns.loc[H0:H1].index
mom = res.returns.loc[ix]
v2h = v2.reindex(ix).fillna(0.0)
nif = nifty.reindex(ix).fillna(0.0)
rf = res.rf.loc[ix]
combo = 0.5 * mom + 0.5 * v2h
rows = {f"stock momentum ({lock['choice']})": summary(mom, rf), "v2-IN (ETF trend)": summary(v2h, rf),
        "50/50 combination": summary(combo, rf), "Nifty 50": summary(nif, rf),
        "stock momentum at 2x costs": summary(res2.returns.loc[ix], rf)}
print(f"HOLDOUT {ix[0].date()} -> {ix[-1].date()}  (locked choice: {lock['choice']})")
print(pd.DataFrame({k: {m: v[m] for m in ("cagr", "vol", "sharpe", "max_drawdown")} for k, v in rows.items()})
      .T.rename(columns={"sharpe": "sharpe_above_cash"}).to_string(float_format=lambda x: f"{x:.3f}"))
print(f"correlation stock momentum vs v2-IN: {mom.corr(v2h):.2f} | vs Nifty: {mom.corr(nif):.2f}")
print(f"turnover {res.stats(H0, H1)['turnover_ann']:.1f}x/yr, cost drag {res.stats(H0, H1)['cost_drag_ann']:.2%}/yr")
tax_c = (1 + res_tax.returns.loc[ix]).prod() ** (252 / len(ix)) - 1
print(f"stock momentum after Indian tax: CAGR {tax_c:.2%} (pre-tax {rows[list(rows)[0]]['cagr']:.2%})")
yr = (1 + pd.DataFrame({"stock mom": mom, "v2-IN": v2h, "50/50": combo, "Nifty": nif})).resample("YE").prod() - 1
yr.index = yr.index.year
print((yr * 100).round(1).T.to_string())

s_mom, s_v2, s_combo, s_nif = (rows[k]["sharpe"] for k in list(rows)[:4])
dsr = deflated_sharpe(mom - rf, N_TRIALS)
checks = {
    "S1 Sharpe above cash > 0 at 2x costs": rows["stock momentum at 2x costs"]["sharpe"] > 0,
    "S2 Sharpe above cash > Nifty 50": s_mom > s_nif,
    "S3 50/50 combination Sharpe > v2-IN alone": s_combo > s_v2,
}
print("\nTIER 1:")
for k, v in checks.items():
    print(f"   {'PASS' if v else 'FAIL'}  {k}")
print(f"   => {'PASS' if all(checks.values()) else 'FAIL'}")
print(f"TIER 2: DSR {dsr:.3f} > 0.95 -> {'PASS' if dsr > 0.95 else 'FAIL'}")
(ROOT / "results" / "stock_holdout.json").write_text(json.dumps(
    {"stats": rows, "tier1": checks, "dsr": dsr, "after_tax_cagr": tax_c,
     "yearly": (yr * 100).round(1).to_dict(orient="index")}, indent=2, default=str))
