import unittest

from ai_analyst import REQUIRED_FIELDS, validate_and_guard
from trading_pipeline import build_ai_candidate


def model_response():
    return {
        "symbol": "HALLUCINATED",
        "trend_alignment": "Aligned",
        "vcp_quality": "Contracting",
        "breakout_confirmation": {
            "status": "CONFIRMED_BREAKOUT",
            "reason": "Model claim",
            "volume_confirmation": "CONFIRMED",
        },
        "entry_price": 1.0,
        "stop_loss": 0.5,
        "target": 5.0,
        "position_sizing": {"quantity": 99999, "risk_per_trade": 500},
        "missing_information": [],
        "risk_notes": [],
        "assessment": "Explanation",
        "extra_model_field": "discard this",
    }


class AIAnalystGuardTests(unittest.TestCase):
    def test_python_prices_and_size_override_model_values(self):
        candidate = {
            "symbol": "TEST",
            "completed_daily_close": 102.0,
            "contraction_low": 95.0,
            "volume_baseline": 1000.0,
            "breakout_status": "CONFIRMED_BREAKOUT",
            "breakout_confirmed": True,
            "volume_confirmed": True,
            "python_results": {
                "entry_price": 102.0,
                "stop_loss": 94.5,
                "target_reference_2r": 117.0,
                "approved_for_sizing": True,
                "quantity": 50,
                "maximum_trade_risk": 375.0,
                "risk_budget": 500,
                "investment_value": 5100.0,
            },
        }
        guarded = validate_and_guard(model_response(), candidate)
        self.assertEqual(guarded["symbol"], "TEST")
        self.assertEqual(guarded["entry_price"], 102.0)
        self.assertEqual(guarded["stop_loss"], 94.5)
        self.assertEqual(guarded["target"], 117.0)
        self.assertEqual(guarded["position_sizing"]["quantity"], 50)
        self.assertEqual(guarded["position_sizing"]["risk_per_trade"], 375.0)
        self.assertTrue(guarded["position_sizing"]["manual_approval_required"])
        self.assertFalse(guarded["position_sizing"]["order_placed"])
        self.assertTrue(guarded["breakout_confirmation"]["confirmed"])
        self.assertEqual(set(guarded), set(REQUIRED_FIELDS))

    def test_missing_close_or_python_approval_removes_trade_values(self):
        candidate = {
            "symbol": "TEST",
            "completed_daily_close": None,
            "contraction_low": None,
            "volume_baseline": None,
            "breakout_status": "BELOW_PIVOT",
            "breakout_confirmed": False,
            "python_results": {
                "entry_price": 100.0,
                "stop_loss": 90.0,
                "target_reference_2r": 120.0,
                "approved_for_sizing": False,
                "quantity": None,
                "maximum_trade_risk": None,
            },
        }
        guarded = validate_and_guard(model_response(), candidate)
        self.assertEqual(guarded["breakout_confirmation"]["status"], "UNCONFIRMED")
        self.assertIsNone(guarded["entry_price"])
        self.assertIsNone(guarded["stop_loss"])
        self.assertIsNone(guarded["target"])
        self.assertIsNone(guarded["position_sizing"]["quantity"])
        self.assertEqual(guarded["breakout_confirmation"]["volume_confirmation"], "UNKNOWN")

    def test_missing_required_model_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Missing fields"):
            validate_and_guard({"symbol": "TEST"}, {"symbol": "TEST"})

    def test_malformed_model_numeric_sections_are_replaced_by_python(self):
        candidate = {
            "symbol": "TEST", "completed_daily_close": 102.0,
            "contraction_low": 95.0, "volume_baseline": 1000.0,
            "breakout_status": "BELOW_PIVOT", "breakout_confirmed": False,
            "volume_confirmed": False,
            "python_results": {
                "entry_price": 102.0, "stop_loss": 94.5,
                "target_reference_2r": 117.0,
                "approved_for_sizing": False,
            },
        }
        model = model_response()
        model["position_sizing"] = "quantity: 999999"
        model["breakout_confirmation"] = 999
        guarded = validate_and_guard(model, candidate)
        self.assertIsNone(guarded["position_sizing"]["quantity"])
        self.assertEqual(guarded["breakout_confirmation"]["status"], "BELOW_PIVOT")
        self.assertFalse(guarded["breakout_confirmation"]["confirmed"])

    def test_pipeline_passes_python_levels_and_risk_to_local_ai(self):
        technical = {
            "symbol": "TEST",
            "analysis_date": "2026-01-01",
            "latest_price": 102.0,
            "screening_summary": {"candidate_status": "BREAKOUT_CONFIRMED"},
            "trend_analysis": {"conditions_passed": 9, "conditions": {"price_above_sma200": True},
                               "moving_averages": {"sma200": 90.0}},
            "contraction_analysis": {"contractions": [{"depth_pct": 8.0, "low": 95.0}]},
            "breakout_analysis": {"status": "CONFIRMED_BREAKOUT", "breakout_confirmed": True,
                                  "pivot": {"pivot_price": 100.0},
                                  "volume_analysis": {"volume_ratio": 1.6, "average_volume": 1000,
                                                      "volume_confirmed": True}},
            "entry_exit_analysis": {"entry_price": 102.0, "stop_loss": 94.5,
                                    "target_reference_2r": 117.0, "structural_swing_low": 95.0},
        }
        risk = {"approved_for_sizing": True, "quantity": 50,
                "maximum_trade_risk": 375.0, "risk_budget": 500,
                "investment_value": 5100.0}
        context = build_ai_candidate(technical, risk)
        self.assertEqual(context["python_results"]["entry_price"], 102.0)
        self.assertEqual(context["python_results"]["quantity"], 50)
        self.assertEqual(context["breakout_status"], "CONFIRMED_BREAKOUT")


if __name__ == "__main__":
    unittest.main()
