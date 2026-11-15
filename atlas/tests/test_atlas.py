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
            acct = Path(d) / "acct.json"
            rec = rebalance(PX.iloc[:-5], cfg, PaperBroker(acct, 1e6), dry_run=False, state_dir=d)
            self.assertTrue(rec["orders"])
            self.assertEqual(PaperBroker(acct).positions(), {})       # queued, not filled
            # Same-day re-run must not fill at the decision-day price.
            rebalance(PX.iloc[:-5], cfg, PaperBroker(acct), dry_run=False, state_dir=d)
            self.assertEqual(PaperBroker(acct).positions(), {})
            # Next day: yesterday's orders fill at today's close.
            rec = rebalance(PX.iloc[:-4], cfg, PaperBroker(acct), dry_run=False, state_dir=d)
            self.assertTrue(rec["fills"])
            b = PaperBroker(acct)
            self.assertTrue(b.positions())
            self.assertAlmostEqual(b.equity(), 1e6, delta=1e6 * 0.05)
            for k in range(3, 0, -1):
                rec = rebalance(PX.iloc[:-k], cfg, PaperBroker(acct), dry_run=False, state_dir=d)
            self.assertEqual(len((Path(d) / "journal.jsonl").read_text().splitlines()), 6)


class Financing(unittest.TestCase):
    def test_flat_book_earns_cash_rate(self):
        idx = pd.bdate_range("2015-01-01", periods=600)
        flat = pd.DataFrame(100.0, index=idx, columns=["A", "B"])
        cfg = deep_merge(CFG, {"financing": {"rate_source": "constant", "rate": 0.04}})
        res = run_backtest(flat, cfg)
        self.assertTrue(np.allclose(res.weights.to_numpy(), 0.0))
        self.assertAlmostEqual(res.returns.iloc[1:].mean() * 252, 0.04, places=6)
        self.assertAlmostEqual(res.excess.iloc[1:].abs().max(), 0.0, places=12)

    def test_leverage_costs_more_than_cash(self):
        cfg = deep_merge(CFG, {"financing": {"rate_source": "constant", "rate": 0.05}})
        res = run_backtest(PX, cfg)
        long = res.weights.clip(lower=0).sum(axis=1).shift(1).fillna(0)
        lev_days = long > 1.05
        self.assertTrue(lev_days.any())
        self.assertTrue((res.financing[lev_days] < 0).all())


class PaperFinancing(unittest.TestCase):
    def test_cash_accrues_interest_and_shorts_pay_fee(self):
        with tempfile.TemporaryDirectory() as d:
            b = PaperBroker(Path(d) / "a.json", 1000.0)
            b.mark({"X": 10.0})
            b.accrue_financing(0.0365, "2026-01-01")
            self.assertAlmostEqual(b.accrue_financing(0.0365, "2026-01-11"), 1000 * 0.0365 * 10 / 365)
            from atlas.execution import Order
            b.submit([Order("X", -50, 10.0)])          # short 500 of X
            b.slip = 0.0
            eq = b.equity()
            amt = b.accrue_financing(0.0365, "2026-01-21", short_fee=0.0365)
            # base = equity - longs = eq earns; short 500 pays the fee
            self.assertAlmostEqual(amt, (eq * 0.0365 - 500 * 0.0365) * 10 / 365, places=6)


class Tax(unittest.TestCase):
    def setUp(self):
        from atlas.tax import TaxConfig, TaxLedger
        self.L = TaxLedger(TaxConfig(classes={"G": "other", "D": "debt"}))
        self.d = pd.Timestamp

    def test_short_term_equity_fifo(self):
        L, d = self.L, self.d
        L.buy("E", 100, 10.0, d("2024-05-01"))
        L.buy("E", 100, 20.0, d("2024-06-01"))
        L.sell("E", 150, 30.0, d("2024-09-01"))      # FIFO: 100@10 + 50@20 -> 2000 + 500
        self.assertAlmostEqual(L.settle(2025), 2500 * 0.20)
        self.assertEqual(sum(u for u, _, _ in L.lots["E"]), 50)

    def test_long_term_exemption_and_other_classes(self):
        L, d = self.L, self.d
        L.buy("E", 1000, 100.0, d("2023-01-02"))
        L.sell("E", 1000, 400.0, d("2024-06-03"))    # LT gain 300k, 125k exempt
        L.buy("G", 100, 100.0, d("2024-06-03"))
        L.sell("G", 100, 150.0, d("2024-09-03"))     # gold short-term -> slab
        L.buy("D", 100, 100.0, d("2022-06-03"))
        L.sell("D", 100, 110.0, d("2024-09-03"))     # debt -> slab even if long
        expect = 175_000 * 0.125 + 5000 * 0.312 + 1000 * 0.312
        self.assertAlmostEqual(L.settle(2025), expect)

    def test_losses_offset_and_carry_forward(self):
        L, d = self.L, self.d
        L.buy("E", 100, 50.0, d("2024-05-01"))
        L.sell("E", 100, 30.0, d("2024-06-01"))      # ST loss 2000
        self.assertEqual(L.settle(2025), 0.0)
        L.buy("E", 100, 30.0, d("2025-05-01"))
        L.sell("E", 100, 60.0, d("2025-06-01"))      # ST gain 3000, 2000 carried loss
        self.assertAlmostEqual(L.settle(2026), 1000 * 0.20)

    def test_backtest_tax_reduces_returns(self):
        cfg = deep_merge(CFG, {"tax": {"enabled": True}})
        a, b = run_backtest(PX, CFG), run_backtest(PX, cfg)
        self.assertIsNone(a.tax)
        self.assertGreaterEqual(b.tax.sum(), 0.0)
        self.assertLessEqual(b.equity.iloc[-1], a.equity.iloc[-1] + 1e-6)


class CrossCheck(unittest.TestCase):
    def test_mismatch_and_missing_fail_closed(self):
        from unittest import mock
        from atlas import crosscheck
        official = pd.Series({"NIFTYBEES": 286.64, "GOLDBEES": 111.91})
        last = pd.Series({"NIFTYBEES.NS": 286.64, "GOLDBEES.NS": 111.91})
        with mock.patch.object(crosscheck, "nse_bhavcopy", return_value=official):
            rep = crosscheck.verify_nse(last, pd.Timestamp("2026-11-13"))
            self.assertEqual(rep["NIFTYBEES.NS"]["dev"], 0.0)
            with self.assertRaises(crosscheck.DataCheckError):
                crosscheck.verify_nse(last * 1.02, pd.Timestamp("2026-11-13"))
            with self.assertRaises(crosscheck.DataCheckError):
                crosscheck.verify_nse(pd.Series({"ITBEES.NS": 35.5}), pd.Timestamp("2026-11-13"))

    def test_unreachable_source_fails_closed(self):
        from unittest import mock
        from atlas import crosscheck
        with mock.patch("urllib.request.urlopen", side_effect=OSError("down")):
            with self.assertRaises(crosscheck.DataCheckError):
                crosscheck.nse_bhavcopy(pd.Timestamp("2026-11-13"))


class Monitor(unittest.TestCase):
    def test_bands_and_status(self):
        from atlas.monitor import expectation_band, status
        rng = np.random.default_rng(0)
        r = pd.Series(rng.normal(0.0004, 0.006, 3000), pd.bdate_range("2010-01-01", periods=3000))
        b = expectation_band(r, 63, n_boot=500)
        self.assertLess(b[1], b[5]); self.assertLess(b[5], b[50]); self.assertLess(b[50], b[99])
        self.assertEqual(status(b[50], b), "OK")
        self.assertEqual(status((b[1] + b[5]) / 2, b), "WARNING")
        self.assertEqual(status(b[1] - 0.01, b), "STOP")


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
