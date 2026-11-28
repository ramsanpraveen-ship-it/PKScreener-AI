import json
import unittest
from pathlib import Path

from tools.freeze_strategy_baseline import build_snapshot


class StrategyBaselineTests(unittest.TestCase):
    def test_frozen_baseline_hashes_match_source_artifacts(self):
        root = Path(__file__).resolve().parent
        frozen = json.loads((root / "STRATEGY_BASELINE_SNAPSHOT.json").read_text(encoding="utf-8"))
        current = build_snapshot(root)
        self.assertEqual(frozen["artifact_sha256"], current["artifact_sha256"])
        self.assertTrue(frozen["immutable_comparison"])
        self.assertFalse(frozen["signal_gates"]["contraction_volume_is_hard_gate"])


if __name__ == "__main__":
    unittest.main()
