import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
from unittest.mock import patch

from market_data import _download_with_retries, validate_ohlcv_data
from nse_calendar import validate_market_data_freshness
from relative_strength import fetch_close_prices
from technical_engine import run_technical_analysis


IST = ZoneInfo("Asia/Kolkata")


def candles(day, bad=False):
    values = [[10.0, 12.0, 9.0, 11.0, 1000.0]]
    if bad:
        values = [[10.0, float("nan"), 9.0, 11.0, 1000.0]]
    return pd.DataFrame(values, columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.to_datetime([day]))


class DataReliabilityTests(unittest.TestCase):
    def test_fresh_date_is_accepted(self):
        now = datetime(2026, 11, 27, 17, 0, tzinfo=IST)
        self.assertEqual(validate_market_data_freshness(candles("2026-11-27"), candles("2026-11-27"), now)["status"], "FRESH")

    def test_stale_date_is_rejected(self):
        now = datetime(2026, 11, 27, 17, 0, tzinfo=IST)
        with self.assertRaisesRegex(ValueError, "STALE_DATA"):
            validate_market_data_freshness(candles("2026-11-26"), candles("2026-11-26"), now)

    def test_mismatched_dates_are_rejected(self):
        now = datetime(2026, 11, 27, 17, 0, tzinfo=IST)
        with self.assertRaisesRegex(ValueError, "DATA_DATE_MISMATCH"):
            validate_market_data_freshness(candles("2026-11-27"), candles("2026-11-26"), now)

    def test_nan_ohlc_row_is_removed(self):
        with self.assertRaisesRegex(ValueError, "No valid OHLCV candles"):
            validate_ohlcv_data(candles("2026-11-27", bad=True), "TEST")

    def test_benchmark_discards_in_progress_session_but_requires_expected_close(self):
        frame = pd.DataFrame(
            {"Close": [100.0, 101.0]},
            index=pd.to_datetime(["2026-11-26", "2026-11-27"]),
        )
        with patch("relative_strength.get_latest_expected_nse_session", return_value=datetime(2026, 11, 26).date()), \
             patch("relative_strength.yf.download", return_value=frame):
            close = fetch_close_prices("^NSEI", attempts=1)
        self.assertEqual(close.index[-1].date(), datetime(2026, 11, 26).date())
        self.assertEqual(len(close), 1)

    def test_benchmark_still_rejects_missing_expected_session(self):
        frame = pd.DataFrame(
            {"Close": [101.0]},
            index=pd.to_datetime(["2026-11-27"]),
        )
        with patch("relative_strength.get_latest_expected_nse_session", return_value=datetime(2026, 11, 26).date()), \
             patch("relative_strength.yf.download", return_value=frame):
            with self.assertRaisesRegex(RuntimeError, "STALE_DATA"):
                fetch_close_prices("^NSEI", attempts=1)

    def test_fresh_but_short_history_is_excluded_without_analysis_error(self):
        sessions = pd.bdate_range(end="2026-11-26", periods=252)
        stock = pd.DataFrame(
            {"Open": 10.0, "High": 12.0, "Low": 9.0, "Close": 11.0, "Volume": 100},
            index=sessions,
        )
        stock["DataSource"] = "Yahoo Finance auto-adjusted OHLCV"
        benchmark = pd.Series(100.0, index=sessions, name="^NSEI")
        with patch("technical_engine.fetch_stock_data", return_value=stock), \
             patch("technical_engine.validate_market_data_freshness", return_value={"status": "FRESH"}):
            result = run_technical_analysis("NEWLISTING", benchmark_df=benchmark)
        self.assertEqual(result["analysis_date"], "2026-11-26")
        self.assertEqual(result["data_info"]["aligned_sessions"], 252)
        self.assertEqual(result["screening_summary"]["candidate_status"], "INSUFFICIENT_HISTORY")

    def test_retry_exhaustion_is_bounded(self):
        calls, delays = [], []
        def fail():
            calls.append(1)
            raise ValueError("temporary")
        with self.assertRaisesRegex(RuntimeError, "after 3 attempts"):
            _download_with_retries(fail, attempts=3, backoff=0.1, sleep=delays.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [0.1, 0.2])


if __name__ == "__main__":
    unittest.main()
