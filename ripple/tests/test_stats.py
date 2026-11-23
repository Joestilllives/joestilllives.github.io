"""Tests for the outcome tracker (#1) and price-based link discovery (#2) using synthetic prices."""
import math
import random
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from discover import check_map, discover  # noqa: E402
from engine import Graph  # noqa: E402
from outcomes import build_scorecard, score_impact  # noqa: E402
from prices import yahoo_symbol  # noqa: E402

G = Graph()
SYM = lambda eid: yahoo_symbol(G.entities[eid])  # noqa: E731


def business_days(n, start=date(2024, 1, 1)):
    d, out = start, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def to_prices(dates, rets, p0=100.0):
    p, out = p0, {}
    for d, r in zip(dates, rets):
        p *= math.exp(r)
        out[d] = p
    return out


def synthetic_market(seed=7, n=500):
    rnd = random.Random(seed)
    dates = business_days(n)
    noise = lambda s: [rnd.gauss(0, s) for _ in dates]  # noqa: E731
    crude, gold, nifty, spx = noise(0.02), noise(0.01), noise(0.01), noise(0.01)
    # Planted links (follower moves the NEXT day, on top of its market):
    ioc = [nifty[i] - 0.30 * (crude[i - 1] if i else 0) + rnd.gauss(0, 0.012) for i in range(n)]   # in map
    wipro = [nifty[i] + 0.45 * (gold[i - 1] if i else 0) + rnd.gauss(0, 0.012) for i in range(n)]  # NOT in map
    tcs = [nifty[i] + rnd.gauss(0, 0.012) for i in range(n)]                                        # pure noise
    return dates, {
        "BZ=F": to_prices(dates, crude), "GC=F": to_prices(dates, gold),
        "^NSEI": to_prices(dates, nifty), "^GSPC": to_prices(dates, spx),
        "IOC.NS": to_prices(dates, ioc), "WIPRO.NS": to_prices(dates, wipro), "TCS.NS": to_prices(dates, tcs),
    }


class DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.prices = synthetic_market()
        cls.found = discover(G, cls.prices, SYM, G.benchmarks)

    def pair(self, lead, follow):
        return [d for d in self.found if d["leader"] == lead and d["follower"] == follow]

    def test_finds_new_link_not_in_map(self):
        hit = self.pair("Gold price", "Wipro")
        self.assertTrue(hit, self.found)
        self.assertFalse(hit[0]["in_map"])
        self.assertGreater(hit[0]["beta"], 0)

    def test_finds_known_link_and_marks_it(self):
        hit = self.pair("Crude oil price", "Indian Oil")
        self.assertTrue(hit)
        self.assertTrue(hit[0]["in_map"])
        self.assertLess(hit[0]["beta"], 0)

    def test_ignores_noise(self):
        self.assertFalse([d for d in self.found if d["follower"] == "TCS"])

    def test_new_links_listed_first(self):
        self.assertFalse(self.found[0]["in_map"])

    def test_map_check_confirms_crude_to_ioc(self):
        rows = [r for r in check_map(G, self.prices, SYM, G.benchmarks)
                if r["from"] == "Crude oil price" and r["to"] == "Indian Oil"]
        self.assertEqual(rows[0]["status"], "confirmed")
        self.assertEqual(rows[0]["timing"], "next day")


class OutcomeTests(unittest.TestCase):
    def setUp(self):
        dates = business_days(20)
        self.dates = dates
        flat = {d: 100.0 for d in dates}
        # IOC is flat until day 10's close, then drops 1% a day; the Nifty stays flat.
        ioc = {d: 100.0 * (0.99 ** max(0, i - 10)) for i, d in enumerate(dates)}
        self.prices = {"IOC.NS": ioc, "^NSEI": flat}

    def at(self, day_index, hour):
        d = datetime.fromisoformat(self.dates[day_index]).replace(tzinfo=timezone.utc)
        return (d + timedelta(hours=hour)).timestamp()

    def test_headwind_that_came_true_is_a_hit(self):
        res = score_impact(self.at(10, 12), "IOC.NS", "headwind", self.prices, G.benchmarks)
        self.assertTrue(res[1]["hit"])
        self.assertAlmostEqual(res[3]["excess"], 0.99 ** 3 - 1, places=4)

    def test_tailwind_that_failed_is_a_miss(self):
        res = score_impact(self.at(10, 12), "IOC.NS", "tailwind", self.prices, G.benchmarks)
        self.assertFalse(res[1]["hit"])

    def test_alert_before_india_close_uses_previous_close(self):
        # 08:00 UTC is before the 10:00 UTC India close, so the base is day 9; day 10 was flat.
        res = score_impact(self.at(10, 8), "IOC.NS", "headwind", self.prices, G.benchmarks)
        self.assertEqual(res[1]["excess"], 0)
        self.assertFalse(res[1]["hit"])

    def test_pending_when_future_prices_missing(self):
        res = score_impact(self.at(17, 12), "IOC.NS", "headwind", self.prices, G.benchmarks)
        self.assertIn(1, res)
        self.assertNotIn(3, res)

    def test_scorecard_summary(self):
        log = [{"id": "x", "title": "Oil jumps", "published": datetime.fromtimestamp(self.at(10, 12), timezone.utc).isoformat(),
                "impacts": [{"id": "ioc", "name": "Indian Oil", "effect": "headwind", "cross_market": True,
                             "path": [{"from": "Crude oil price", "to": "Indian Oil", "why": "-"}]},
                            {"id": "ongc", "name": "ONGC", "effect": "tailwind", "cross_market": True,
                             "path": [{"from": "Crude oil price", "to": "ONGC", "why": "-"}]}]}]
        sc = build_scorecard(log, self.prices, SYM, G.benchmarks)
        self.assertEqual(sc["overall"]["1"]["n"], 1)  # ONGC has no prices, so it's skipped
        self.assertEqual(sc["overall"]["1"]["hit_rate"], 1.0)
        self.assertFalse(sc["overall"]["1"]["enough_data"])
        self.assertGreater(sc["overall"]["3"]["avg_edge_pct"], 0)


class SignalTests(unittest.TestCase):
    def test_long_short_none(self):
        from signal_today import compute
        spx = {"2026-01-01": 100.0, "2026-01-02": 101.0}          # S&P +1%
        self.assertEqual(compute({"2026-01-01": 100.0, "2026-01-02": 103.0}, spx)["action"], "LONG")   # +2% beyond
        self.assertEqual(compute({"2026-01-01": 100.0, "2026-01-02": 99.0}, spx)["action"], "SHORT")   # -2% beyond
        self.assertEqual(compute({"2026-01-01": 100.0, "2026-01-02": 101.5}, spx)["action"], "NONE")   # +0.5% beyond


class StaleOpenTests(unittest.TestCase):
    def test_drops_open_equal_to_previous_close(self):
        from backtest import drop_stale_opens
        o = {"2026-01-01": (100.0, 101.0), "2026-01-02": (101.0, 103.0), "2026-01-05": (102.0, 104.0)}
        self.assertEqual(sorted(drop_stale_opens(o)), ["2026-01-01", "2026-01-05"])


if __name__ == "__main__":
    unittest.main()
