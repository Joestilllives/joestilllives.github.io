"""Pre-registered holdout test for Atlas v2. See PREREGISTRATION.md.

usage:
  python scripts/holdout_test.py seen        # debug run on the already-used 28-ETF data
  python scripts/holdout_test.py holdout     # the one real run (universes A and B)
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
from atlas.data import clean_prices, get_rates, load_yfinance  # noqa: E402
from atlas.metrics import deflated_sharpe, summary  # noqa: E402
from atlas.validation import deep_merge           # noqa: E402

# Holdout A: instruments NOT in the 28-ETF or 5-ETF sets (and no near-duplicates
# such as IAU~GLD or IYR~VNQ), same calendar period.
HOLDOUT_A = dict(start="2005-01-01", end=None, symbols=[
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY",          # US sectors
    "EWD", "EWH", "EWL", "EWP", "EWQ", "EWS", "EWT", "EWW", "EWY", "EZA",   # countries
    "EWI", "EWN",
    "AGG", "IEI", "TLH", "MBB", "BWX",                                      # bonds
    "UNG", "DBB", "DBE", "PPLT",                                            # commodities
    "FXB", "FXC", "FXF", "UUP",                                             # currencies
    "RWX",                                                                  # intl real estate
])
# Holdout B: years never used (1999-2004), whatever liquid ETFs existed then.
HOLDOUT_B = dict(start="1998-01-01", end="2004-12-31", symbols=[
    "SPY", "QQQ", "DIA", "MDY", "IWM",
    "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY",
    "EWA", "EWC", "EWD", "EWG", "EWH", "EWI", "EWJ", "EWL", "EWN", "EWP",
    "EWQ", "EWS", "EWU", "EWW", "EWY", "EWT", "EWZ",
    "SHY", "IEF", "TLT", "LQD", "TIP",
])
SEEN = dict(start="2005-01-01", end=None, symbols=None)  # filled from etf_broad.toml

N_TRIALS = 3        # configs evaluated project-wide on real data: default(5), default(28), v2
SLEEVE = 0.20


def sharpe_x(r, rf):
    x = (r - rf).dropna()
    return float(x.mean() / x.std() * np.sqrt(252))


def evaluate(name, spec, cfg, out):
    px = load_yfinance(spec["symbols"], spec["start"])
    if spec["end"]:
        px = px.loc[: spec["end"]]
    px = clean_prices(px)
    res = run_backtest(px, cfg)
    start = res.returns.ne(0).idxmax()
    ix = res.returns.loc[start:].index
    s = res.returns.loc[ix]
    rf = res.rf.loc[ix]
    st = res.stats
    stress = run_backtest(px, deep_merge(cfg, {"execution": {
        "commission_bps": 1.5, "half_spread_bps": 3.0, "impact_k": 1.5}})).stats

    row = {"universe": name, "n_assets": px.shape[1], "start": str(ix[0].date()), "end": str(ix[-1].date()),
           "cagr": st["cagr"], "sharpe_above_cash": st["sharpe"], "max_dd": st["max_drawdown"],
           "sharpe_3x_costs": stress["sharpe"], "dsr": deflated_sharpe(s - rf, N_TRIALS),
           "avg_gross": st["avg_gross"], "corr_spy": None}

    bench = load_yfinance(["SPY", "IEF"], "1998-01-01").pct_change(fill_method=None).reindex(ix)
    if bench.notna().all().all():
        b = 0.6 * bench.SPY + 0.4 * bench.IEF
        blend = (1 - SLEEVE) * b + SLEEVE * s
        sb, sbl = summary(b, rf), summary(blend, rf)
        row.update({"corr_spy": float(s.corr(bench.SPY)),
                    "6040_sharpe": sb["sharpe"], "6040_max_dd": sb["max_drawdown"], "6040_cagr": sb["cagr"],
                    "blend_sharpe": sbl["sharpe"], "blend_max_dd": sbl["max_drawdown"], "blend_cagr": sbl["cagr"]})
        yr = pd.DataFrame({"atlas_v2": s, "60/40": b, "blend": blend})
        yr = (1 + yr).resample("YE").prod() - 1
        yr.index = yr.index.year
        row["yearly"] = (yr * 100).round(1).to_dict(orient="index")
    out.append(row)
    return row


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "seen"
    cfg = tomllib.load(open(ROOT / "config" / "v2.toml", "rb"))
    out = []
    if mode == "seen":
        SEEN["symbols"] = tomllib.load(open(ROOT / "config" / "etf_broad.toml", "rb"))["data"]["symbols"]
        a = evaluate("seen-28", SEEN, cfg, out)
        b = None
    else:
        a = evaluate("A: new assets 2005-2026", HOLDOUT_A, cfg, out)
        b = evaluate("B: unseen years 1999-2004", HOLDOUT_B, cfg, out)

    checks = {
        "P1 blend Sharpe > 60/40 Sharpe": a.get("blend_sharpe", -9) > a.get("6040_sharpe", 9),
        "P2 blend max DD shallower than 60/40": a.get("blend_max_dd", -9) > a.get("6040_max_dd", 9),
        "P3 standalone Sharpe above cash > 0 at 3x costs": a["sharpe_3x_costs"] > 0,
    }
    if b is not None:
        checks["S1 unseen-years Sharpe above cash > 0"] = b["sharpe_above_cash"] > 0
    tier2 = a["dsr"] > 0.95
    for r in out:
        print(f"\n== {r['universe']}  ({r['n_assets']} assets, {r['start']} -> {r['end']})")
        for k, v in r.items():
            if k not in ("universe", "yearly", "n_assets", "start", "end") and v is not None:
                print(f"   {k:<20} {v:8.3f}")
        if "yearly" in r:
            print(pd.DataFrame(r["yearly"]).T.to_string())
    print("\nTIER 1 (proceed to paper trading):")
    for k, v in checks.items():
        print(f"   {'PASS' if v else 'FAIL'}  {k}")
    print(f"   => {'PASS' if all(checks.values()) else 'FAIL'}")
    print(f"TIER 2 (eligible for real money after paper): DSR {a['dsr']:.3f} > 0.95 -> "
          f"{'PASS' if tier2 else 'FAIL'}  (also needs 3 months of paper trading tracking the backtest)")
    Path(ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"holdout_{mode}.json").write_text(json.dumps(
        {"rows": out, "tier1": checks, "tier2_dsr_pass": tier2}, indent=2, default=str))


if __name__ == "__main__":
    main()
