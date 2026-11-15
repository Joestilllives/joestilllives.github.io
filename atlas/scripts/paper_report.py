"""Compare the paper-trading record with what the backtest says the same days
should have returned. This is the Tier 2 tracking check in PREREGISTRATION.md.

usage: python scripts/paper_report.py [config/v2.toml]
"""
import json
import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas.backtest import run_backtest   # noqa: E402
from atlas.data import get_prices          # noqa: E402

cfg = tomllib.load(open(sys.argv[1] if len(sys.argv) > 1 else ROOT / "config/v2.toml", "rb"))
journal = ROOT / cfg["live"]["state_dir"] / "journal.jsonl"
recs = [json.loads(l) for l in journal.read_text().splitlines() if l.strip()]
recs = [r for r in recs if not r["dry_run"]]
if len(recs) < 3:
    sys.exit(f"only {len(recs)} live paper runs so far; need at least 3")
eq = pd.Series({pd.Timestamp(r["as_of"]): r["equity"] for r in recs}).sort_index()
paper = eq.pct_change().dropna()

bt = run_backtest(get_prices(cfg), cfg).returns
bt_period = pd.Series({d: (1 + bt.loc[p0:d].iloc[1:]).prod() - 1
                       for p0, d in zip(eq.index[:-1], eq.index[1:])})
j = pd.concat({"paper": paper, "backtest": bt_period}, axis=1).dropna()
diff = j.paper - j.backtest
print(f"paper runs: {len(recs)}  ({eq.index[0].date()} -> {eq.index[-1].date()})")
print(f"paper total return:    {(1 + j.paper).prod() - 1:+.2%}")
print(f"backtest same period:  {(1 + j.backtest).prod() - 1:+.2%}")
print(f"correlation:           {j.paper.corr(j.backtest):.3f}")
print(f"tracking error (ann.): {diff.std() * np.sqrt(252):.2%}")
print(f"current drawdown flag: killed={recs[-1].get('killed')} scale={recs[-1]['exposure_scale']:.2f}")
print("Tier 2 tracking target: correlation > 0.9 and tracking error < 3% over >= 63 trading days")
