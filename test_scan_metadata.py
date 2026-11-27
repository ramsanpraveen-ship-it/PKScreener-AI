import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from stock_screener import save_scan_metadata


class ScanMetadataTests(unittest.TestCase):
    def test_metadata_is_fresh_only_when_every_stock_and_benchmark_match(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            all_file = output / "screening_results_20261127_100000.csv"
            candidate_file = output / "breakout_candidates_20261127_100000.csv"
            rows = [{"symbol": "AAA", "analysis_date": "2026-11-27", "market_data_source": "Yahoo Finance auto-adjusted OHLCV", "candidate_status": "SETUP_WATCH"}]
            with patch("stock_screener.OUTPUT_DIR", output):
                saved = save_scan_metadata(all_file, candidate_file, date(2026, 11, 27), date(2026, 11, 27), rows)
            meta = json.loads(saved.read_text())
            self.assertEqual(meta["freshness_status"], "FRESH")
            self.assertEqual(meta["stock_dates"]["AAA"], "2026-11-27")
            self.assertEqual(meta["stock_data_sources"]["AAA"], "Yahoo Finance auto-adjusted OHLCV")

    def test_insufficient_history_is_recorded_as_a_fresh_exclusion(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            all_file = output / "screening_results_20261127_100000.csv"
            candidate_file = output / "breakout_candidates_20261127_100000.csv"
            rows = [{
                "symbol": "NEW", "analysis_date": "2026-11-27",
                "market_data_source": "Yahoo Finance auto-adjusted OHLCV",
                "candidate_status": "INSUFFICIENT_HISTORY",
            }]
            with patch("stock_screener.OUTPUT_DIR", output):
                saved = save_scan_metadata(all_file, candidate_file, date(2026, 11, 27), date(2026, 11, 27), rows)
            meta = json.loads(saved.read_text())
            self.assertEqual(meta["freshness_status"], "FRESH")
            self.assertFalse(meta["has_analysis_errors"])
            self.assertEqual(meta["insufficient_history_symbols"], ["NEW"])

    def test_errors_or_date_mismatch_are_not_marked_fresh(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            all_file = output / "screening_results_20261127_100000.csv"
            candidate_file = output / "breakout_candidates_20261127_100000.csv"
            rows = [
                {"symbol": "AAA", "analysis_date": "2026-11-27", "candidate_status": "SETUP_WATCH"},
                {"symbol": "BBB", "analysis_date": "2026-11-26", "candidate_status": "ERROR"},
            ]
            with patch("stock_screener.OUTPUT_DIR", output):
                saved = save_scan_metadata(all_file, candidate_file, date(2026, 11, 27), date(2026, 11, 27), rows)
            meta = json.loads(saved.read_text())
            self.assertEqual(meta["freshness_status"], "PARTIAL_OR_STALE")
            self.assertTrue(meta["has_analysis_errors"])
            self.assertIsNone(meta["stock_dates"]["BBB"])
            self.assertIsNone(meta["stock_data_sources"]["BBB"])


if __name__ == "__main__":
    unittest.main()
