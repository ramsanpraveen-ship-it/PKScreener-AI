import csv
import json
import tempfile
import unittest
from pathlib import Path

from backend.app.scan_service import load_latest_scan


class ScanServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.output = self.root / "data" / "screening_results"
        self.output.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_no_metadata_never_surfaces_old_csvs(self):
        (self.output / "screening_results_20261127_000000.csv").write_text("symbol\nTEST\n")
        payload = load_latest_scan(self.root, "2026-11-27")
        self.assertEqual(payload["status"], "NO_VALIDATED_SCAN")
        self.assertEqual(payload["candidates"], [])

    def test_fresh_metadata_and_rows_are_visible(self):
        (self.output / "screening_results_20261127_100000.csv").write_text(
            "analysis_date,symbol,candidate_status\n2026-11-27,TEST,SETUP_WATCH\n"
        )
        (self.output / "scan_metadata_20261127_100000.json").write_text(json.dumps({
            "schema_version": 1, "freshness_status": "FRESH",
            "expected_session": "2026-11-27", "benchmark_date": "2026-11-27",
            "stock_dates": {"TEST": "2026-11-27"}, "has_analysis_errors": False,
            "results_file": "screening_results_20261127_100000.csv",
        }))
        payload = load_latest_scan(self.root, "2026-11-27")
        self.assertEqual(payload["status"], "FRESH")
        self.assertEqual(payload["candidates"][0]["symbol"], "TEST")

    def test_stale_latest_run_does_not_fall_back_to_older_fresh_run(self):
        old_results = "screening_results_20261127_090000.csv"
        (self.output / old_results).write_text(
            "analysis_date,symbol,candidate_status\n2026-11-27,OLD,FRESH\n"
        )
        (self.output / "scan_metadata_20261127_090000.json").write_text(json.dumps({
            "schema_version": 1, "freshness_status": "FRESH",
            "expected_session": "2026-11-27", "benchmark_date": "2026-11-27",
            "stock_dates": {"OLD": "2026-11-27"}, "has_analysis_errors": False,
            "results_file": old_results,
        }))
        newer_results = "screening_results_20261127_100000.csv"
        (self.output / newer_results).write_text(
            "analysis_date,symbol,candidate_status\n2026-11-26,NEW,SETUP_WATCH\n"
        )
        (self.output / "scan_metadata_20261127_100000.json").write_text(json.dumps({
            "schema_version": 1, "freshness_status": "PARTIAL_OR_STALE",
            "expected_session": "2026-11-27", "benchmark_date": "2026-11-26",
            "stock_dates": {"NEW": "2026-11-26"}, "has_analysis_errors": False,
            "results_file": newer_results,
        }))
        payload = load_latest_scan(self.root, "2026-11-27")
        self.assertEqual(payload["status"], "STALE_OR_PARTIAL_DATA")
        self.assertEqual(payload["candidates"], [])

    def test_partial_stock_dates_hide_all_rows(self):
        (self.output / "screening_results_20261127_100000.csv").write_text(
            "analysis_date,symbol,candidate_status\n2026-11-27,TEST,SETUP_WATCH\n"
        )
        (self.output / "scan_metadata_20261127_100000.json").write_text(json.dumps({
            "schema_version": 1, "freshness_status": "FRESH",
            "expected_session": "2026-11-27", "benchmark_date": "2026-11-27",
            "stock_dates": {"TEST": "2026-11-26"}, "has_analysis_errors": False,
            "results_file": "screening_results_20261127_100000.csv",
        }))
        payload = load_latest_scan(self.root, "2026-11-27")
        self.assertEqual(payload["status"], "STALE_OR_PARTIAL_DATA")
        self.assertEqual(payload["candidates"], [])


if __name__ == "__main__":
    unittest.main()
