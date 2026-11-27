import unittest

from paper_trading import summarize_paper_trades, validate_paper_entry


class PaperTradingTests(unittest.TestCase):
    def test_entry_obeys_risk_and_allocation_limits(self):
        result = validate_paper_entry(100, 95, 100, 0, 0)
        self.assertEqual(result, {"planned_risk": 500, "investment": 10000})

    def test_entry_rejects_risk_over_limit(self):
        with self.assertRaisesRegex(ValueError, "₹500"):
            validate_paper_entry(100, 94, 100, 0, 0)

    def test_entry_rejects_position_allocation_over_limit(self):
        with self.assertRaisesRegex(ValueError, "₹20,000"):
            validate_paper_entry(101, 100, 200, 0, 0)

    def test_summary_counts_only_closed_simulations_and_excludes_costs(self):
        summary = summarize_paper_trades([
            {"status": "CLOSED", "entry_price": 100, "exit_price": 110, "quantity": 10},
            {"status": "CLOSED", "entry_price": 100, "exit_price": 95, "quantity": 10},
            {"status": "OPEN", "entry_price": 100, "exit_price": None, "quantity": 10},
        ])
        self.assertEqual(summary["closed_trades"], 2)
        self.assertEqual(summary["open_trades"], 1)
        self.assertEqual(summary["realized_pnl_before_costs"], 50)
        self.assertEqual(summary["win_rate_percent"], 50)
        self.assertFalse(summary["costs_included"])
        self.assertFalse(summary["live_orders_placed"])


if __name__ == "__main__":
    unittest.main()
