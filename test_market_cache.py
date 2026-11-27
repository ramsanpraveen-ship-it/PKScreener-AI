import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import market_data


class MarketCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.cache = Path(self.temp.name) / "sample.csv"
        self.frame = pd.DataFrame(
            {
                "Open": [10.0, 11.0], "High": [12.0, 13.0],
                "Low": [9.0, 10.0], "Close": [11.0, 12.0],
                "Volume": [100, 120],
            },
            index=pd.to_datetime(["2026-11-26", "2026-11-27"]),
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_fresh_cache_is_loaded(self):
        market_data._write_cache(self.cache, self.frame)
        with patch.object(market_data, "get_latest_expected_nse_session", return_value=date(2026, 11, 27)):
            loaded = market_data._load_fresh_cache(self.cache, "TEST")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.index[-1].date(), date(2026, 11, 27))

    def test_fresh_session_cache_ignores_newer_in_progress_candle(self):
        market_data._write_cache(self.cache, self.frame)
        with patch.object(market_data, "get_latest_expected_nse_session", return_value=date(2026, 11, 26)):
            loaded = market_data._load_fresh_cache(self.cache, "TEST")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.index[-1].date(), date(2026, 11, 26))

    def test_stale_long_download_uses_fresh_short_window(self):
        long_frame = pd.DataFrame(
            {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0], "Volume": [100]},
            index=pd.to_datetime(["2026-11-25"]),
        )
        recent_frame = pd.DataFrame(
            {
                "Open": [11.0, 12.0], "High": [13.0, 14.0],
                "Low": [10.0, 11.0], "Close": [12.0, 13.0],
                "Volume": [120, 130],
            },
            index=pd.to_datetime(["2026-11-26", "2026-11-27"]),
        )
        with patch.object(market_data, "_load_fresh_cache", return_value=None), \
             patch.object(market_data, "_cache_path", return_value=self.cache), \
             patch.object(market_data, "get_latest_expected_nse_session", return_value=date(2026, 11, 26)), \
             patch("market_data.yf.download", side_effect=[long_frame, recent_frame]) as download:
            loaded = market_data.fetch_stock_data("TEST", period="2y")
        self.assertEqual(loaded.index[-1].date(), date(2026, 11, 26))
        self.assertNotIn(date(2026, 11, 27), {stamp.date() for stamp in loaded.index})
        self.assertEqual([call.kwargs["period"] for call in download.call_args_list], ["2y", "1mo"])

    def test_official_nse_bar_fills_only_exact_eq_session_with_stable_adjustment(self):
        long_frame = pd.DataFrame(
            {"Open": [10.0], "High": [12.0], "Low": [9.0], "Close": [11.0], "Volume": [100]},
            index=pd.to_datetime(["2026-11-25"]),
        )
        recent_frame = pd.DataFrame(
            {"Open": [10.0, 12.0], "High": [12.0, 14.0], "Low": [9.0, 11.0],
             "Close": [11.0, 13.0], "Volume": [100, 130]},
            index=pd.to_datetime(["2026-11-25", "2026-11-27"]),
        )
        adjustment_frame = pd.DataFrame(
            {"Close": [11.0, 13.0], "Adj Close": [11.0, 13.0],
             "Dividends": [0.0, 0.0], "Stock Splits": [0.0, 0.0]},
            index=pd.to_datetime(["2026-11-25", "2026-11-27"]),
        )
        csv_bytes = (
            b"SYMBOL, SERIES, DATE1, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, TTL_TRD_QNTY\n"
            b"TEST, EQ, 26-Nov-2026, 11.0, 13.0, 10.0, 12.0, 120\n"
        )
        class Response:
            content = csv_bytes
            def raise_for_status(self):
                return None
        with patch.object(market_data, "_load_fresh_cache", return_value=None), \
             patch.object(market_data, "_cache_path", return_value=self.cache), \
             patch.object(market_data, "CACHE_DIR", Path(self.temp.name)), \
             patch.object(market_data, "get_latest_expected_nse_session", return_value=date(2026, 11, 26)), \
             patch("market_data.yf.download", side_effect=[long_frame, recent_frame, adjustment_frame]), \
             patch("market_data.requests.get", return_value=Response()):
            loaded = market_data.fetch_stock_data("TEST", period="2y")
        self.assertEqual(loaded.index[-1].date(), date(2026, 11, 26))
        self.assertFalse(loaded.index.has_duplicates)
        self.assertEqual(float(loaded.iloc[-1]["Close"]), 12.0)
        self.assertIn("NSE official EOD", loaded.iloc[-1]["DataSource"])

    def test_adjustment_factor_rejects_change_across_missing_session(self):
        frame = pd.DataFrame(
            {"Close": [10.0, 10.0], "Adj Close": [9.0, 10.0],
             "Dividends": [0.0, 0.0], "Stock Splits": [0.0, 0.0]},
            index=pd.to_datetime(["2026-11-25", "2026-11-27"]),
        )
        with self.assertRaisesRegex(ValueError, "factor changes"):
            market_data._validated_adjustment_factor(frame, date(2026, 11, 26))

    def test_stale_cache_is_ignored(self):
        market_data._write_cache(self.cache, self.frame)
        with patch.object(market_data, "get_latest_expected_nse_session", return_value=date(2026, 11, 28)):
            loaded = market_data._load_fresh_cache(self.cache, "TEST")
        self.assertIsNone(loaded)

    def test_invalid_cache_is_ignored(self):
        self.cache.write_text("not,a,candle\n", encoding="utf-8")
        loaded = market_data._load_fresh_cache(self.cache, "TEST")
        self.assertIsNone(loaded)


if __name__ == "__main__":
    unittest.main()
