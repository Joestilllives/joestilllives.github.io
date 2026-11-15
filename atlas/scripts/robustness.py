"""Parameter robustness: perturb one setting at a time and re-run.

Diagnostic only. A real edge degrades gently when parameters move; an overfit
one has a sharp peak at the chosen values. Never pick the best row from this
table: that would be fitting to the same data.

usage: python scripts/robustness.py [config]   (default config/india_v2.toml)
"""
import sys
import tomllib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas.backtest import run_backtest    # noqa: E402
from atlas.data import get_prices           # noqa: E402
from atlas.validation import deep_merge     # noqa: E402

cfg = tomllib.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "config/india_v2.toml", "rb"))
px = get_prices(cfg)
base_speeds = [[8, 32], [16, 64], [32, 128], [64, 256]]
variants = {
    "as validated": {},
    "trend speeds x0.5": {"signals": {"params": {"trend": {"speeds": [[a // 2, b // 2] for a, b in base_speeds]}}}},
    "trend speeds x2": {"signals": {"params": {"trend": {"speeds": [[a * 2, b * 2] for a, b in base_speeds]}}}},
    "trend only": {"signals": {"weights": {"trend": 1.0, "ts_momentum": 0.0}}},
    "momentum only": {"signals": {"weights": {"trend": 0.0, "ts_momentum": 1.0}}},
    "momentum 6-1": {"signals": {"params": {"ts_momentum": {"lookback": 126, "skip": 21}}}},
    "target vol 8%": {"portfolio": {"target_vol": 0.08}},
    "target vol 12%": {"portfolio": {"target_vol": 0.12}},
    "max weight 15%": {"portfolio": {"max_weight": 0.15}},
    "max weight 35%": {"portfolio": {"max_weight": 0.35}},
    "buffer 0.05": {"execution": {"buffer": 0.05}},
    "buffer 0.20": {"execution": {"buffer": 0.20}},
    "buffer floor 0.05": {"execution": {"buffer_floor": 0.05}},
    "no regime overlay": {"regime": {"enabled": False}},
    "no drawdown ladder": {"risk": {"dd_soft": 0.9, "dd_hard": 0.95, "dd_kill": 0.99}},
    "lag 2 days": {"execution": {"lag": 2}},
}
rows = {}
for name, over in variants.items():
    c = deep_merge(cfg, over)
    if "weights" in over.get("signals", {}):
        c["signals"]["weights"] = over["signals"]["weights"]
    s = run_backtest(px, c).stats
    rows[name] = {"cagr": s["cagr"], "sharpe_above_cash": s["sharpe"], "max_dd": s["max_drawdown"],
                  "turnover": s["turnover_ann"]}
t = pd.DataFrame(rows).T
print(t.to_string(float_format=lambda x: f"{x:.3f}"))
sh = t["sharpe_above_cash"].drop("as validated")
print(f"\nSharpe across perturbations: min {sh.min():.2f}, median {sh.median():.2f}, max {sh.max():.2f} "
      f"(validated {t.loc['as validated', 'sharpe_above_cash']:.2f}); "
      f"{(sh > 0).mean():.0%} of variants positive")
