import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import Graph, analyze, direction_near  # noqa: E402

G = Graph()


def impact(title, company_id):
    a = analyze(G, {"title": title})
    assert a, f"no alert for {title!r}"
    for i in a["impacts"]:
        if i["id"] == company_id:
            return i
    raise AssertionError(f"{company_id} not in impacts for {title!r}: {[i['id'] for i in a['impacts']]}")


class DirectionTests(unittest.TestCase):
    def test_word_after_mention(self):
        t = "Oil prices jump on supply fears"
        s = t.index("Oil prices")
        self.assertEqual(direction_near(t, s, s + len("Oil prices")), 1)

    def test_word_before_mention(self):
        t = "Deficient monsoon worries farmers"
        s = t.index("monsoon")
        self.assertEqual(direction_near(t, s, s + 7), -1)


class ChainTests(unittest.TestCase):
    def test_opec_cut_hurts_fuel_retailers(self):
        # OPEC cuts output -> crude up -> fuel retailers squeezed
        self.assertEqual(impact("OPEC+ agrees to cut output", "ioc")["effect"], "headwind")

    def test_opec_cut_helps_producer(self):
        self.assertEqual(impact("OPEC+ agrees to cut output", "ongc")["effect"], "tailwind")

    def test_oil_fall_helps_airline(self):
        self.assertEqual(impact("Crude oil falls to six-month low", "indigo")["effect"], "tailwind")

    def test_h1b_fee_hike_cross_market(self):
        i = impact("US to raise H-1B visa fees", "infosys")
        self.assertEqual(i["effect"], "headwind")
        self.assertTrue(i["cross_market"])

    def test_auto_tariffs_reach_tata_via_jlr(self):
        i = impact("White House plans 25% auto tariffs on imported cars", "tatamotors")
        self.assertEqual(i["effect"], "headwind")
        self.assertEqual([p["to"] for p in i["path"]], ["Jaguar Land Rover", "Tata Motors (JLR parent)"])

    def test_risk_easing_flips_direction(self):
        self.assertEqual(impact("Strait of Hormuz tensions ease after talks", "indigo")["effect"], "tailwind")

    def test_mentioned_company_not_flagged_as_hidden(self):
        a = analyze(G, {"title": "Infosys shares rise after US banks boost spending"})
        self.assertNotIn("infosys", [i["id"] for i in a["impacts"]])

    def test_case_sensitive_alias(self):
        self.assertIsNone(analyze(G, {"title": "Fans are fed up with the weather"}))

    def test_real_headline_oil_import_bill(self):
        # Real GDELT headline the first version missed
        i = impact("India oil & gas import bill shoots up $6 billion in Oct as global prices surge", "bpcl")
        self.assertEqual(i["effect"], "headwind")

    def test_unrelated_headline(self):
        self.assertIsNone(analyze(G, {"title": "Local football club wins cup final"}))


if __name__ == "__main__":
    unittest.main()
