import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from atlas.backtest import run_backtest
from atlas.cli import load_config
from atlas.data import clean_prices, synthetic_prices
from atlas.execution import PaperBroker, apply_buffer
from atlas.live import rebalance
from atlas.metrics import deflated_sharpe, probabilistic_sharpe
from atlas.portfolio import RiskModel, ex_ante_vol, target_weights
from atlas.regime import regime_multiplier
from atlas.risk import PreTradeCheckError, RiskManager, pre_trade_checks
from atlas.signals import REGISTRY
from atlas.validation import deep_merge, lookahead_probe

CFG = load_config(None)
PX = clean_prices(synthetic_prices(n_assets=8, n_days=252 * 8, seed=3))


class NoLookahead(unittest.TestCase):
    def _scramble(self, cut):
        s = PX.copy()
        s.iloc[cut:] = s.iloc[cut:].to_numpy()[::-1]
        return s

    def test_each_signal_is_causal(self):
        cut = 1200
        alt = self._scramble(cut)
        for name, fn in REGISTRY.items():
            a, b = fn(PX).iloc[:cut], fn(alt).iloc[:cut]
            pd.testing.assert_frame_equal(a, b, obj=name)

    def test_regime_is_causal(self):
        cut = 1200
        a = regime_multiplier(PX, CFG).iloc[:cut]
        b = regime_multiplier(self._scramble(cut), CFG).iloc[:cut]
        pd.testing.assert_series_equal(a, b)

    def test_full_pipeline_is_causal(self):
        self.assertLess(lookahead_probe(PX, CFG), 1e-12)


class EdgeDetection(unittest.TestCase):
    """The framework must find real edge and must not find edge in noise."""

    def test_real_trend_is_captured(self):
        px = clean_prices(synthetic_prices(n_days=252 * 15, seed=1, trend_strength=1.0))
        cfg = deep_merge(CFG, {"signals": {"method": "static"}})
        cfg["signals"]["weights"] = {"trend": 1.0}
        res = run_backtest(px, cfg)
        self.assertGreater(res.stats["sharpe"], 0.5)
        self.assertGreater(deflated_sharpe(res.returns, 5), 0.95)

    def test_noise_does_not_pass_gate(self):
        for seed in (1, 2, 3):
            px = clean_prices(synthetic_prices(n_days=252 * 15, seed=seed, trend_strength=0.0))
            res = run_backtest(px, CFG)
            self.assertLess(deflated_sharpe(res.returns, 5), 0.95)


class RiskControls(unittest.TestCase):
    def test_target_vol_respected(self):
        m = RiskModel(PX.shape[1])
        for row in np.log(PX).diff().to_numpy():
            m.update(row)
        pcfg = CFG["portfolio"]
        w = target_weights(np.full(PX.shape[1], 2.0), m, pcfg)
        self.assertLessEqual(ex_ante_vol(w, m.covariance()),
                             pcfg["target_vol"] * pcfg["vol_ceiling_mult"] + 1e-9)
        self.assertLessEqual(np.abs(w).max(), pcfg["max_weight"] + 1e-12)

    def test_drawdown_ladder_and_kill(self):
        rm = RiskManager({"dd_soft": 0.1, "dd_hard": 0.25, "dd_kill": 0.35, "halt_days": 3}, 0.12)
        rm.on_equity(100.0)
        self.assertEqual(rm.exposure_scale(100.0), 1.0)
        rm.on_equity(85.0)
        self.assertTrue(0.3 < rm.exposure_scale(85.0) < 1.0)
        rm.on_equity(74.0)
        self.assertEqual(rm.exposure_scale(74.0), 0.0)  # hard stop -> halt
        for _ in range(3):
            rm.on_equity(74.0)
        self.assertGreater(rm.exposure_scale(74.0), 0.0)  # re-armed
        rm.on_equity(60.0)
        self.assertTrue(rm.state.killed)
        for _ in range(50):
            rm.on_equity(200.0)
        self.assertEqual(rm.exposure_scale(200.0), 0.0)  # kill is permanent

    def test_backtest_max_loss_bounded(self):
        px = clean_prices(synthetic_prices(n_days=252 * 15, seed=2, trend_strength=0.0))
        dd = run_backtest(px, CFG).stats["max_drawdown"]
        self.assertGreater(dd, -(CFG["risk"]["dd_kill"] + 0.05))

    def test_pre_trade_checks(self):
        with self.assertRaises(PreTradeCheckError):
            pre_trade_checks(np.array([np.nan]), np.array([0.0]), 1e6, {}, {"kill_switch_file": None})
        with self.assertRaises(PreTradeCheckError):
            pre_trade_checks(np.array([0.1]), np.array([5e5]), 1e6, {}, {"kill_switch_file": None})
        with tempfile.TemporaryDirectory() as d:
            ks = Path(d) / "KILL"
            ks.touch()
            with self.assertRaises(PreTradeCheckError):
                pre_trade_checks(np.array([0.1]), np.array([1.0]), 1e6, {}, {"kill_switch_file": str(ks)})


class Execution(unittest.TestCase):
    def test_buffer(self):
        cur = np.array([0.10, 0.10, 0.30])
        tgt = np.array([0.105, 0.30, 0.0])
        out = apply_buffer(cur, tgt, 0.1)
        self.assertEqual(out[0], 0.10)               # inside band: no trade
        self.assertAlmostEqual(out[1], 0.27)         # trade to band edge
        self.assertEqual(out[2], 0.0)                # flat target closes fully

    def test_paper_cycle(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = deep_merge(CFG, {"live": {"max_staleness_days": None},
                                   "risk": {"kill_switch_file": None}})
            broker = PaperBroker(Path(d) / "acct.json", 1e6)
            rec = rebalance(PX, cfg, broker, dry_run=False, state_dir=d)
            self.assertTrue(rec["orders"])
            self.assertAlmostEqual(broker.equity(), 1e6, delta=1e6 * 0.002)  # only slippage lost
            # Same data re-run: throttled trades finish, then nothing left to do.
            for n in range(2, 6):
                rec = rebalance(PX, cfg, PaperBroker(Path(d) / "acct.json"), dry_run=False, state_dir=d)
                if not rec["orders"]:
                    break
            self.assertEqual(rec["orders"], [])
            self.assertEqual(len((Path(d) / "journal.jsonl").read_text().splitlines()), n)


class Metrics(unittest.TestCase):
    def test_psr(self):
        rng = np.random.default_rng(0)
        idx = pd.bdate_range("2010-01-01", periods=2520)
        good = pd.Series(rng.normal(0.001, 0.01, 2520), idx)   # SR ~1.6
        noise = pd.Series(rng.normal(0.0, 0.01, 2520), idx)
        self.assertGreater(probabilistic_sharpe(good), 0.99)
        self.assertLess(probabilistic_sharpe(noise), 0.95)
        self.assertLess(deflated_sharpe(good, 1000), probabilistic_sharpe(good))


if __name__ == "__main__":
    unittest.main()
