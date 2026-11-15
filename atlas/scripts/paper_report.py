"""Paper/live vs backtest: tracking and pre-computed expectation bands.

usage: python scripts/paper_report.py [config]   (default config/india_v2.toml)
"""
import json
import sys
import tomllib
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from atlas.backtest import run_backtest            # noqa: E402
from atlas.data import get_prices                   # noqa: E402
from atlas.monitor import expectation_band, status, tracking  # noqa: E402

cfg_path = sys.argv[1] if len(sys.argv) > 1 else ROOT / "config/india_v2.toml"
cfg = tomllib.load(open(cfg_path, "rb"))
journal = ROOT / cfg["live"]["state_dir"] / "journal.jsonl"
recs = [json.loads(l) for l in journal.read_text().splitlines() if l.strip()]
recs = [r for r in recs if not r["dry_run"]]
eq = pd.Series({pd.Timestamp(r["as_of"]): r["equity"] for r in recs}).sort_index()
eq = eq[~eq.index.duplicated(keep="last")]

bt = run_backtest(get_prices(cfg), cfg).returns
live = eq.pct_change().dropna()
bt_same = pd.Series({d: (1 + bt.loc[p0:d].iloc[1:]).prod() - 1 for p0, d in zip(eq.index[:-1], eq.index[1:])})

days = max(len(live), 1)
band = expectation_band(bt, days)
cum = float((1 + live).prod() - 1) if len(live) else 0.0
print(f"paper runs: {len(eq)}  ({eq.index[0].date()} -> {eq.index[-1].date()}), {days} trading days scored")
print(f"paper cumulative return: {cum:+.2%}")
print("backtest-implied range for this many days: " + "  ".join(f"p{k}:{v:+.1%}" for k, v in band.items()))
print(f"STATUS: {status(cum, band)}   (WARNING below p5, STOP below p1)")
t = tracking(live, bt_same)
if "corr" in t:
    print(f"tracking vs backtest: corr {t['corr']:.3f}, tracking error {t['tracking_error_ann']:.2%}/yr "
          f"(target: corr > 0.9, TE < 3%)")
print(f"current: exposure_scale {recs[-1]['exposure_scale']:.2f}, killed={recs[-1].get('killed')}")
