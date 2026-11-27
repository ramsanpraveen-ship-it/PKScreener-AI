import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from backtest_engine import (
    BacktestConfig,
    _nse_transaction_bps,
    _summarize,
    generate_signals,
    simulate_signals,
    save_backtest_results,
    validate_point_in_time_universe,
    _wilson_win_rate_interval,
    _period_returns,
    _walk_forward_slices,
)


def bars(dates, rows):
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close", "Volume"],
                        index=pd.to_datetime(dates))


def sample_signal(day, stop=90.0):
    return {
        "signal_date": pd.Timestamp(day),
        "symbol": "TEST",
        "pivot": 99.0,
        "breakout_level": 99.099,
        "stop_loss": stop,
        "relative_strength": 12.0,
    }


class BacktestEngineTests(unittest.TestCase):
    def setUp(self):
        self.days = pd.bdate_range("2026-01-05", periods=5)
        self.tri = pd.Series([100, 101, 102, 103, 104], index=self.days)
        self.config = BacktestConfig(
            slippage_bps_per_side=0,
            include_statutory_costs=False,
            max_holding_sessions=2,
        )

    def test_signal_enters_next_session_open_and_honors_risk_budget(self):
        frame = bars(self.days, [
            [99, 100, 98, 99, 1000],
            [100, 105, 99, 101, 1000],
            [101, 110, 99, 105, 1000],
            [105, 110, 99, 102, 1000],
            [102, 105, 100, 103, 1000],
        ])
        result = simulate_signals(
            {"TEST": frame}, [sample_signal(self.days[0])], self.tri,
            self.days[0], self.days[-1], self.config,
        )
        trade = result["trades"][0]
        self.assertEqual(trade["entry_date"], self.days[1].date().isoformat())
        self.assertEqual(trade["entry_fill"], 100)
        self.assertEqual(trade["quantity"], 50)
        self.assertEqual(trade["planned_risk"], 500)
        self.assertEqual(trade["exit_reason"], "TIME_EXIT")
        self.assertEqual(trade["exit_date"], self.days[2].date().isoformat())
        self.assertEqual(trade["net_pnl"], 250)

    def test_stop_is_assumed_first_when_both_levels_trade(self):
        frame = bars(self.days, [
            [99, 100, 98, 99, 1000],
            [100, 125, 89, 101, 1000],
            [101, 110, 99, 105, 1000],
            [105, 110, 99, 102, 1000],
            [102, 105, 100, 103, 1000],
        ])
        result = simulate_signals(
            {"TEST": frame}, [sample_signal(self.days[0])], self.tri,
            self.days[0], self.days[-1], self.config,
        )
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "STOP")
        self.assertEqual(trade["exit_fill"], 90)
        self.assertEqual(trade["net_pnl"], -500)

    def test_gap_through_stop_fills_at_open(self):
        frame = bars(self.days, [
            [99, 100, 98, 99, 1000],
            [100, 105, 99, 101, 1000],
            [85, 95, 80, 90, 1000],
            [90, 95, 88, 92, 1000],
            [92, 95, 90, 93, 1000],
        ])
        result = simulate_signals(
            {"TEST": frame}, [sample_signal(self.days[0])], self.tri,
            self.days[0], self.days[-1], self.config,
        )
        trade = result["trades"][0]
        self.assertEqual(trade["exit_reason"], "STOP_GAP")
        self.assertEqual(trade["exit_fill"], 85)
        self.assertEqual(trade["net_pnl"], -750)

    def test_end_of_test_liquidates_open_positions(self):
        frame = bars(self.days[:3], [
            [99, 100, 98, 99, 1000],
            [100, 105, 99, 101, 1000],
            [101, 110, 99, 105, 1000],
        ])
        result = simulate_signals(
            {"TEST": frame}, [sample_signal(self.days[0])], self.tri[:3],
            self.days[0], self.days[2],
            BacktestConfig(slippage_bps_per_side=0,
                           include_statutory_costs=False,
                           max_holding_sessions=10),
        )
        self.assertEqual(result["trades"][0]["exit_reason"], "END_OF_TEST")
        self.assertEqual(result["equity_curve"][-1]["open_positions"], 0)

    def test_dividend_is_credited_only_to_a_position_held_from_prior_close(self):
        frame = bars(self.days, [
            [99, 100, 98, 99, 1000],
            [100, 105, 99, 101, 1000],
            [101, 110, 99, 105, 1000],
            [105, 110, 99, 102, 1000],
            [102, 105, 100, 103, 1000],
        ])
        frame["Dividends"] = [0, 0, 2, 0, 0]
        result = simulate_signals(
            {"TEST": frame}, [sample_signal(self.days[0])], self.tri,
            self.days[0], self.days[-1],
            BacktestConfig(slippage_bps_per_side=0,
                           include_statutory_costs=False,
                           max_holding_sessions=10),
        )
        self.assertEqual(result["trades"][0]["dividend_cash"], 100)
        self.assertEqual(result["trades"][0]["net_pnl"], 250)

    def test_current_constituents_are_not_accepted_as_complete_history(self):
        history = pd.DataFrame([{
            "symbol": "TEST", "series": "EQ", "valid_from": "2020-01-01", "valid_to": None,
            "source_url": "https://www.niftyindices.com/test",
        }])
        with self.assertRaisesRegex(ValueError, "SURVIVORSHIP_GUARD"):
            validate_point_in_time_universe(history, complete=False)

    def test_warmup_gap_fails_closed_instead_of_shifting_signal_windows(self):
        days = pd.bdate_range("2024-01-01", periods=300)
        frame = bars(days, [[100, 102, 99, 101, 1000] for _ in days]).drop(days[-100])
        frame["Dividends"] = 0.0
        history = pd.DataFrame([{
            "symbol": "TEST", "series": "EQ", "valid_from": days[0], "valid_to": None,
            "source_url": "https://www.niftyindices.com/test",
        }])
        benchmark = pd.Series(100.0, index=days)
        with patch("backtest_engine._strategy_signal") as strategy:
            with self.assertRaisesRegex(ValueError, "253-session signal window"):
                generate_signals({"TEST": frame}, history, benchmark, [days[-1]], complete_universe=True)
        strategy.assert_not_called()

    def test_new_symbol_waits_for_a_complete_253_session_warmup(self):
        days = pd.bdate_range("2024-01-01", periods=300)
        frame = bars(days[-200:], [[100, 102, 99, 101, 1000] for _ in days[-200:]])
        frame["Dividends"] = 0.0
        history = pd.DataFrame([{
            "symbol": "TEST", "series": "EQ", "valid_from": days[0], "valid_to": None,
            "source_url": "https://www.niftyindices.com/test",
        }])
        benchmark = pd.Series(100.0, index=days)
        with patch("backtest_engine._strategy_signal") as strategy:
            result = generate_signals({"TEST": frame}, history, benchmark, [days[-1]], complete_universe=True)
        self.assertTrue(result.empty)
        strategy.assert_not_called()

    def test_nse_fee_schedule_uses_effective_dates(self):
        self.assertEqual(_nse_transaction_bps("2022-01-01"), 0.345)
        self.assertEqual(_nse_transaction_bps("2023-06-01"), 0.325)
        self.assertEqual(_nse_transaction_bps("2024-06-01"), 0.322)
        self.assertEqual(_nse_transaction_bps("2025-01-01"), 0.297)
        self.assertEqual(_nse_transaction_bps("2026-04-01"), 0.307)

    def test_metrics_report_average_win_loss_ratio_and_trade_counts(self):
        result = _summarize(
            [{"net_pnl": 400.0}, {"net_pnl": -200.0}, {"net_pnl": 100.0}],
            [
                {"date": "2026-01-05", "equity": 100_000.0,
                 "benchmark_equity": 100_000.0, "open_positions": 0},
                {"date": "2026-01-06", "equity": 100_250.0,
                 "benchmark_equity": 100_500.0, "open_positions": 1},
            ],
            self.config,
        )
        metrics = result["metrics"]
        self.assertEqual(metrics["winning_trades"], 2)
        self.assertEqual(metrics["losing_trades"], 1)
        self.assertEqual(metrics["average_win_net_rupees"], 250.0)
        self.assertEqual(metrics["average_loss_net_rupees"], 200.0)
        self.assertEqual(metrics["average_win_loss_ratio"], 1.25)
        self.assertEqual(metrics["profit_factor"], 2.5)
        self.assertEqual(metrics["win_rate_95ci_pct"], [20.77, 93.85])

    def test_wilson_interval_is_unavailable_without_trades(self):
        self.assertIsNone(_wilson_win_rate_interval(0, 0))

    def test_walk_forward_partitions_are_chronological_60_20_20(self):
        sessions = pd.bdate_range("2021-01-01", periods=100)
        parts = _walk_forward_slices(sessions)
        self.assertEqual(parts["development"], (sessions[0], sessions[59]))
        self.assertEqual(parts["validation"], (sessions[60], sessions[79]))
        self.assertEqual(parts["out_of_sample"], (sessions[80], sessions[-1]))

    def test_calendar_returns_use_total_portfolio_capital(self):
        curve = [
            {"date": "2026-01-30", "equity": 101000},
            {"date": "2026-02-27", "equity": 100000},
        ]
        self.assertEqual(_period_returns(curve, "ME", 100000), {"2026-01": 1.0, "2026-02": -0.9901})

    def test_saved_outputs_include_reproducibility_assumptions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = save_backtest_results({
                "metrics": {"trade_count": 0},
                "walk_forward": {"periods": {"out_of_sample": {"trade_count": 2}}},
                "assumptions": {"entry": "next session open"},
                "trades": [],
                "equity_curve": [],
            }, temp_dir)
            self.assertEqual(len(paths), 4)
            saved = json.loads(Path(paths[1]).read_text(encoding="utf-8"))
            self.assertEqual(saved["entry"], "next session open")
            metrics = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
            self.assertEqual(metrics["walk_forward"]["periods"]["out_of_sample"]["trade_count"], 2)


if __name__ == "__main__":
    unittest.main()
