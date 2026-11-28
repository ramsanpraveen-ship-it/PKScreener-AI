import unittest

from risk_manager import calculate_position_size, MAX_AGGREGATE_OPEN_RISK


class RiskManagerTests(unittest.TestCase):
    def candidate(self):
        return {"candidate_status": "BREAKOUT_CONFIRMED", "symbol": "TEST", "entry_price": 100, "stop_loss": 95}

    def account(self, aggregate_open_risk=0):
        return {"total_capital": 100_000, "deployed_capital": 0,
                "open_positions_count": 0, "aggregate_open_risk": aggregate_open_risk}

    def test_sizing_respects_remaining_aggregate_risk(self):
        result = calculate_position_size(self.candidate(), self.account(MAX_AGGREGATE_OPEN_RISK - 10))
        self.assertTrue(result["approved_for_sizing"])
        self.assertEqual(result["quantity"], 2)
        self.assertEqual(result["maximum_trade_risk"], 10)

    def test_sizing_rejects_when_aggregate_risk_is_exhausted(self):
        result = calculate_position_size(self.candidate(), self.account(MAX_AGGREGATE_OPEN_RISK))
        self.assertFalse(result["approved_for_sizing"])
        self.assertEqual(result["status"], "AGGREGATE_RISK_LIMIT_REACHED")

    def test_account_rejects_aggregate_risk_over_limit(self):
        with self.assertRaisesRegex(ValueError, "Aggregate open risk"):
            calculate_position_size(self.candidate(), self.account(MAX_AGGREGATE_OPEN_RISK + 1))


if __name__ == "__main__":
    unittest.main()
