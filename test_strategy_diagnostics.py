import unittest

import pandas as pd

from tools.generate_strategy_intelligence_report import _excursion_diagnostics


class StrategyDiagnosticTests(unittest.TestCase):
    def trade(self):
        return {
            "entry_date": "2026-01-05", "exit_date": "2026-01-06",
            "entry_fill": 100.0, "stop_loss": 90.0,
        }

    def test_excursion_counts_r_thresholds_and_discloses_same_bar_ambiguity(self):
        index = pd.to_datetime(["2026-01-05", "2026-01-06"])
        bars = pd.DataFrame({
            "High": [105.0, 121.0], "Low": [95.0, 92.0],
        }, index=index)
        result = _excursion_diagnostics(self.trade(), bars)
        self.assertTrue(result["reached_1r"])
        self.assertTrue(result["reached_2r"])
        self.assertFalse(result["stop_touched"])
        self.assertEqual(result["first_threshold"], "1R_AND_2R_SAME_BAR_PATH_UNKNOWN")
        self.assertTrue(result["same_bar_path_ambiguous"])
        self.assertEqual(result["mfe_r"], 2.1)

    def test_stop_and_positive_excursion_same_bar_use_conservative_label(self):
        index = pd.to_datetime(["2026-01-05", "2026-01-06"])
        bars = pd.DataFrame({
            "High": [104.0, 112.0], "Low": [95.0, 89.0],
        }, index=index)
        result = _excursion_diagnostics(self.trade(), bars)
        self.assertEqual(result["first_threshold"], "STOP_FIRST_CONSERVATIVE_SAME_BAR")
        self.assertTrue(result["same_bar_path_ambiguous"])
        self.assertTrue(result["stop_touched"])


if __name__ == "__main__":
    unittest.main()
