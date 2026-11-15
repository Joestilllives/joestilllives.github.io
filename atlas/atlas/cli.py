"""Command line: `python -m atlas <command> [--config path]`

  backtest   full simulation + HTML tearsheet
  validate   walk-forward OOS, deflated Sharpe, bootstrap CI, cost stress,
             signal ablation, look-ahead probe
  rebalance  one live/paper trading cycle (dry-run unless --execute)
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .data import get_prices
from .metrics import format_stats, summary
from .report import tearsheet
from .validation import (block_bootstrap_sharpe, cost_stress, lookahead_probe,
                         signal_ablation, walk_forward)

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "default.toml"

# Variants the walk-forward chooses between. Kept deliberately small: every
# extra variant raises the bar the deflated Sharpe has to clear.
DEFAULT_GRID = [
    {},
    {"signals": {"method": "static"}},
    {"portfolio": {"method": "mean_variance"}},
    {"execution": {"buffer": 0.2}},
    {"signals": {"weights": {"trend": 1.0, "ts_momentum": 0, "xs_momentum": 0,
                             "reversal": 0, "low_vol": 0, "carry": 0}}},
]


def load_config(path: str | None) -> dict:
    with open(path or DEFAULT_CONFIG, "rb") as f:
        return tomllib.load(f)


def cmd_backtest(cfg: dict, args) -> int:
    prices = get_prices(cfg)
    res = run_backtest(prices, cfg)
    print(f"Universe: {prices.shape[1]} instruments, {len(prices)} days\n")
    print(format_stats(res.stats))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "tearsheet.html").write_text(tearsheet(res, "Atlas backtest"))
    pd.DataFrame({"equity": res.equity, "returns": res.returns, "cost": res.costs,
                  "turnover": res.turnover}).to_csv(out / "daily.csv")
    res.weights.to_csv(out / "weights.csv")
    print(f"\nWrote {out/'tearsheet.html'}, daily.csv, weights.csv")
    return 0


def cmd_validate(cfg: dict, args) -> int:
    prices = get_prices(cfg)
    v = cfg.get("validation", {})
    print("1) Look-ahead probe (scramble the future, past weights must not move)")
    diff = lookahead_probe(prices, cfg)
    print(f"   max weight change before cut: {diff:.2e}  ->  {'PASS' if diff < 1e-9 else 'FAIL'}")

    print(f"\n2) Walk-forward ({len(DEFAULT_GRID)} variants, train {v.get('train_years', 5)}y / test {v.get('test_years', 1)}y)")
    wf = walk_forward(prices, cfg, DEFAULT_GRID, v.get("train_years", 5), v.get("test_years", 1))
    print(wf.choices.to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    oos = summary(wf.oos_returns)
    print("\n   Out-of-sample stitched track (returns above cash):")
    print(format_stats({**{k: oos[k] for k in ("cagr", "vol", "sharpe", "max_drawdown", "psr")},
                        "dsr": wf.dsr}))

    lo, med, hi = block_bootstrap_sharpe(wf.oos_returns)
    print(f"\n3) Block-bootstrap OOS Sharpe 90% CI: [{lo:.2f}, {hi:.2f}] (median {med:.2f})")

    print("\n4) Cost stress")
    cs = cost_stress(prices, cfg)
    print(cs.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    print("\n5) Signal ablation (each signal alone)")
    ab = signal_ablation(prices, cfg)
    print(ab.to_string(index=False, float_format=lambda x: f"{x:.3f}"))

    verdict = (diff < 1e-9 and wf.dsr > 0.95 and cs["sharpe"].iloc[-1] > 0)
    print(f"\nDEPLOYMENT GATE: {'PASS' if verdict else 'FAIL'} "
          "(needs: no look-ahead, DSR > 95%, positive Sharpe at 3x costs)")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    res = run_backtest(prices, cfg)
    (out / "validation.html").write_text(tearsheet(res, "Atlas validation", {
        "Walk-forward folds": wf.choices.set_index("test_start"),
        "Cost stress": cs.set_index("cost_x"),
        "Signal ablation": ab.set_index("signal"),
    }))
    print(f"Wrote {out/'validation.html'}")
    return 0 if verdict else 2


def cmd_rebalance(cfg: dict, args) -> int:
    from .execution import AlpacaBroker, PaperBroker
    from .live import rebalance
    lc = cfg.get("live", {})
    if cfg.get("data", {}).get("source") == "synthetic":
        lc["max_staleness_days"] = None
        cfg["live"] = lc
    prices = get_prices(cfg)
    state = Path(lc.get("state_dir", "state"))
    if lc.get("broker", "paper") == "alpaca":
        broker = AlpacaBroker()
    elif lc.get("broker") == "zerodha":
        from .execution import ZerodhaBroker
        broker = ZerodhaBroker(amo=lc.get("amo", True))
    else:
        broker = PaperBroker(state / "paper_account.json", cfg.get("capital", 1e6))
    rec = rebalance(prices, cfg, broker, dry_run=not args.execute, state_dir=state)
    print(json.dumps({k: rec[k] for k in ("as_of", "dry_run", "equity", "exposure_scale",
                                          "regime", "ex_ante_vol", "gross")}, indent=2))
    print(f"{len(rec['orders'])} orders" + ("" if args.execute else " (dry run: nothing sent)"))
    for o in rec["orders"]:
        print(f"  {o['symbol']:<8} {o['qty']:>12,.2f} @ {o['price']:,.2f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="atlas", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["backtest", "validate", "rebalance"])
    p.add_argument("--config", help="TOML config (default: config/default.toml)")
    p.add_argument("--out", default="reports", help="output directory for reports")
    p.add_argument("--execute", action="store_true", help="rebalance: actually send orders")
    args = p.parse_args(argv)
    cfg = load_config(args.config)
    return {"backtest": cmd_backtest, "validate": cmd_validate,
            "rebalance": cmd_rebalance}[args.command](cfg, args)


if __name__ == "__main__":
    sys.exit(main())
