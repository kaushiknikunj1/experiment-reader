"""Run: python test_experiment_reader.py"""
from __future__ import annotations

import unittest

import pandas as pd

import experiment_reader as er
import llm


class EngineOnSyntheticData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.packs = {n: er.read_experiment(n, d) for n, d in er.make_experiments().items()}

    def test_clean_winner_ships(self):
        ev = self.packs["checkout_upi_intent"]
        self.assertEqual(ev["verdict"], "SHIP")
        self.assertGreater(ev["conversion"]["ci_low_pct"], 0)
        self.assertTrue(1.5 < ev["conversion"]["lift_pct"] < 4.0)
        self.assertGreater(ev["bayes"]["p_b_beats_a"], 0.99)
        self.assertGreater(ev["srm"]["p_value"], 0.05)

    def test_srm_test_is_refused_despite_apparent_lift(self):
        ev = self.packs["onboarding_kyc_lite"]
        self.assertEqual(ev["verdict"], "INVALID (SRM)")
        self.assertLess(ev["srm"]["p_value"], 0.001)
        self.assertGreater(ev["conversion"]["ci_low_pct"], 0)   # would have "won" on p alone
        self.assertEqual(ev["srm"]["observed_split"], "51.7%/48.3%")

    def test_flat_test_hides_a_segment_reversal_and_a_peek(self):
        ev = self.packs["home_offers_rail"]
        self.assertEqual(ev["verdict"], "INVESTIGATE (segment reversal)")
        self.assertLess(ev["conversion"]["ci_low_pct"], 0)
        self.assertGreater(ev["conversion"]["ci_high_pct"], 0)
        reversed_segments = [s["segment"] for s in ev["segments"] if s["reversal"]]
        self.assertEqual(reversed_segments, ["iOS"])
        self.assertTrue(ev["peeking"]["flag"])
        self.assertLess(ev["peeking"]["p_value_path"]["day_3"], 0.05)
        self.assertGreaterEqual(ev["peeking"]["day_14"], 0.05)

    def test_template_renders_verdict_first(self):
        for ev in self.packs.values():
            memo = er.template_memo(ev)
            lines = memo.split("\n")
            self.assertEqual(lines[0], f"Verdict: {ev['verdict']}.")
            self.assertTrue(lines[-1].startswith("Next:"))
            self.assertIn(f"{ev['conversion']['lift_pct']:+g}%", memo)

    def test_unpinned_catches_an_invented_number(self):
        ev = self.packs["checkout_upi_intent"]
        c = ev["conversion"]
        clean = f"Verdict: SHIP. Conversion {c['lift_pct']:+g}% (CI {c['ci_low_pct']:+g}% to {c['ci_high_pct']:+g}%)."
        self.assertEqual(llm.unpinned(clean, ev), set())
        invented = clean.replace(f"{c['lift_pct']:+g}%", "+3.5%")
        self.assertIn("3.5", llm.unpinned(invented, ev))


class HandComputedExamples(unittest.TestCase):
    def test_srm_chi_square(self):
        # 5,200 vs 4,800 on a 50/50 split: chi2 = 2 * 200^2 / 5000 = 16.0
        r = er.srm_test(5200, 4800)
        self.assertAlmostEqual(r["chi2"], 16.0, places=2)
        self.assertLess(r["p_value"], 0.001)
        self.assertEqual(r["observed_split"], "52.0%/48.0%")

    def test_two_proportion_lift(self):
        # 100/1000 vs 120/1000: lift = 20%, pooled p = 0.11, z = 0.02 / sqrt(0.11*0.89*2/1000) = 1.43
        a = pd.Series([1] * 100 + [0] * 900)
        b = pd.Series([1] * 120 + [0] * 880)
        r = er.conversion_lift(a, b)
        self.assertEqual(r["lift_pct"], 20.0)
        self.assertAlmostEqual(r["z"], 1.43, places=2)
        self.assertLess(r["ci_low_pct"], 0)           # not significant at n = 1,000
        self.assertGreater(r["ci_high_pct"], 20.0)

    def test_verdict_order(self):
        base = {"srm": {"p_value": 0.5}, "segments": [{"reversal": False}],
                "conversion": {"ci_low_pct": 1.0}, "peeking": {"flag": False}}
        self.assertEqual(er.verdict(base), "SHIP")
        self.assertEqual(er.verdict({**base, "peeking": {"flag": True}}), "HOLD")
        self.assertEqual(er.verdict({**base, "segments": [{"reversal": True}]}), "INVESTIGATE (segment reversal)")
        self.assertEqual(er.verdict({**base, "srm": {"p_value": 1e-9}}), "INVALID (SRM)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
