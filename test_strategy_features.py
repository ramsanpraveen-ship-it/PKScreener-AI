import unittest

import numpy as np
import pandas as pd

from market_regime import analyze_market_regime
from strategy_features import (
    measure_breakout_features,
    measure_relative_strength_features,
    measure_vcp_features,
)


class StrategyFeatureTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.bdate_range("2025-01-01", periods=300)
        close = pd.Series(np.linspace(100, 180, len(self.index)), index=self.index)
        self.bars = pd.DataFrame({
            "Open": close * 0.998,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": np.linspace(1_000, 2_000, len(self.index)),
        }, index=self.index)

    def test_vcp_excludes_contractions_confirmed_after_as_of(self):
        contractions = [
            {"start_date": str(self.index[180].date()), "end_date": str(self.index[190].date()),
             "confirmation_date": str(self.index[190].date()), "depth_pct": 20, "low": 120,
             "duration_sessions": 10, "volume_analysis": {"volume_ratio": 0.8}},
            {"start_date": str(self.index[200].date()), "end_date": str(self.index[210].date()),
             "confirmation_date": str(self.index[210].date()), "depth_pct": 12, "low": 130,
             "duration_sessions": 10, "volume_analysis": {"volume_ratio": 0.7}},
            {"start_date": str(self.index[290].date()), "end_date": str(self.index[299].date()),
             "confirmation_date": str(self.index[299].date()), "depth_pct": 5, "low": 140,
             "duration_sessions": 9, "volume_analysis": {"volume_ratio": 0.6}},
        ]
        features = measure_vcp_features(self.bars, contractions, pivot_price=180, as_of=self.index[250])
        self.assertEqual(features["contractions_observed"], 2)
        self.assertTrue(features["higher_lows"])
        self.assertTrue(features["depths_strictly_decreasing"])
        self.assertTrue(features["measurements_only"])

    def test_market_regime_and_breadth_are_as_of_only(self):
        benchmark = pd.Series(np.linspace(100, 250, 240), index=pd.bdate_range("2025-01-01", periods=240))
        strong = pd.Series(np.linspace(50, 140, 240), index=benchmark.index)
        weak = pd.Series(np.linspace(150, 90, 240), index=benchmark.index)
        future = pd.Series(10_000.0, index=[benchmark.index[-1] + pd.offsets.BDay(1)])
        benchmark = pd.concat([benchmark, future])
        result = analyze_market_regime(benchmark, ["A", "B"], {"A": strong, "B": weak}, as_of=benchmark.index[-2])
        self.assertEqual(result["as_of"], benchmark.index[-2].date().isoformat())
        self.assertEqual(result["classification"], "BULLISH")
        self.assertEqual(result["breadth_pct_above_200d"], 50.0)
        missing_membership = analyze_market_regime(benchmark, [], {}, as_of=benchmark.index[-2])
        self.assertIsNone(missing_membership["breadth_pct_above_200d"])

    def test_relative_strength_reports_3_6_12_months_and_internal_rank(self):
        benchmark = pd.Series(np.linspace(100, 130, 300), index=self.index)
        stock = benchmark * np.linspace(1, 1.4, 300)
        slower = benchmark * np.linspace(1, 0.9, 300)
        later = pd.Series(99_999.0, index=[self.index[-1] + pd.offsets.BDay(1)])
        result = measure_relative_strength_features(
            pd.concat([stock, later]), benchmark, {"A": stock, "B": slower},
            symbol="A", as_of=self.index[-2],
        )
        self.assertIsNotNone(result["periods"]["3m"]["relative_return_pct"])
        self.assertIsNotNone(result["periods"]["6m"]["relative_return_pct"])
        self.assertIsNotNone(result["periods"]["12m"]["relative_return_pct"])
        self.assertEqual(result["internal_cross_sectional_relative_percentile"], 75.0)
        self.assertEqual(result["as_of"], self.index[-2].date().isoformat())
        self.assertIsNone(result["sector_relative_performance"])

    def test_breakout_features_exclude_future_candles(self):
        future = self.bars.iloc[[-1]].copy()
        future.index = [self.index[-1] + pd.offsets.BDay(1)]
        future.loc[:, ["Open", "High", "Low", "Close"]] = 10_000
        with_future = pd.concat([self.bars, future])
        result = measure_breakout_features(with_future, pivot_price=175, as_of=self.index[-1])
        expected = measure_breakout_features(self.bars, pivot_price=175, as_of=self.index[-1])
        self.assertEqual(result, expected)
        self.assertIsNone(result["next_session_gap_risk"])
        self.assertTrue(result["measurements_only"])


if __name__ == "__main__":
    unittest.main()
