import csv
from concurrent.futures import ThreadPoolExecutor
import json
import tempfile
import unittest
from pathlib import Path

from forward_paper import process_fresh_scan
from forward_paper import _connect


class ForwardPaperTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scan = self.root / "scan.csv"
        with self.scan.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=["analysis_date", "candidate_status"])
            writer.writeheader()
            writer.writerow({"analysis_date": "2026-11-27", "candidate_status": "NOT_QUALIFIED"})
        self.meta = self.root / "metadata.json"
        self.meta.write_text(json.dumps({
            "freshness_status": "FRESH", "expected_session": "2026-11-27",
            "benchmark_date": "2026-11-27", "has_analysis_errors": False,
            "stock_dates": {"TEST": "2026-11-27"},
        }), encoding="utf-8")
        self.db = self.root / "paper.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def test_missing_freshness_metadata_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "metadata is required"):
            process_fresh_scan(self.scan, "2026-11-27", db_path=self.db)

    def test_session_advances_once_with_fresh_metadata(self):
        first = process_fresh_scan(self.scan, "2026-11-27", self.meta, self.db)
        second = process_fresh_scan(self.scan, "2026-11-27", self.meta, self.db)
        self.assertEqual(first["status"], "PROCESSED")
        self.assertEqual(second["status"], "ALREADY_PROCESSED")

    def test_concurrent_session_runs_advance_once(self):
        db = _connect(self.db)
        db.close()
        def advance(_):
            return process_fresh_scan(self.scan, "2026-11-27", self.meta, self.db)["status"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(advance, range(2)))
        self.assertCountEqual(statuses, ["PROCESSED", "ALREADY_PROCESSED"])


if __name__ == "__main__":
    unittest.main()
