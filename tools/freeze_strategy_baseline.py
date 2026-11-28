"""Create a first-write-only manifest for the existing strategy baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest_engine import (
    BacktestConfig, LIQUIDITY_LOOKBACK_SESSIONS, MIN_AVG_TRADED_VALUE, MIN_PRICE,
)
from breakout_analyzer import (
    BREAKOUT_BUFFER_PCT, BREAKOUT_VOLUME_THRESHOLD, MAX_EXTENSION_PCT,
    MIN_CLOSE_POSITION, PIVOT_LOOKBACK,
)
from contraction_analyzer import LOOKBACK_CANDLES, MIN_CONTRACTIONS_FOR_PATTERN
from entry_exit_analyzer import ATR_STOP_BUFFER, MAX_SWING_AGE, MIN_REWARD_RISK
from relative_strength import RS_WEIGHTS
from risk_manager import (
    MAX_AGGREGATE_OPEN_RISK, MAX_DEPLOYMENT, MAX_OPEN_POSITIONS,
    MAX_POSITION_VALUE, MAX_RISK_PER_TRADE, TOTAL_CAPITAL,
)
from swing_detector import SWING_WINDOW
from trend_analyzer import SMA_LONG, SMA_MEDIUM, SMA_SHORT, SMA_SLOPE_LOOKBACK, WEEK_52_PERIOD


def build_snapshot(root: Path):
    metrics_path = root / "data/backtest/results/backtest_metrics.json"
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    artifacts = {}
    for name in (
        "backtest_metrics.json", "backtest_assumptions.json",
        "backtest_trades.csv", "backtest_equity_curve.csv",
    ):
        path = metrics_path.parent / name
        artifacts[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    config = BacktestConfig()
    return {
        "baseline_id": "pkscreener-vcp-baseline-2026-11-27",
        "immutable_comparison": True,
        "signal_gates": {
            "trend_sma_days": [SMA_SHORT, SMA_MEDIUM, SMA_LONG],
            "trend_sma_slope_lookback": SMA_SLOPE_LOOKBACK,
            "trend_52week_lookback": WEEK_52_PERIOD,
            "vcp_lookback_sessions": LOOKBACK_CANDLES,
            "vcp_required_contractions": MIN_CONTRACTIONS_FOR_PATTERN,
            "vcp_depths_must_strictly_decrease": True,
            "contraction_volume_is_hard_gate": False,
            "breakout_pivot_lookback": PIVOT_LOOKBACK,
            "breakout_buffer_pct": BREAKOUT_BUFFER_PCT,
            "breakout_volume_min_ratio": BREAKOUT_VOLUME_THRESHOLD,
            "breakout_candle_close_position_min": MIN_CLOSE_POSITION,
            "breakout_max_extension_pct": MAX_EXTENSION_PCT,
            "relative_strength_weights_by_sessions": {str(k): v for k, v in RS_WEIGHTS.items()},
            "relative_strength_horizons_sessions": [63, 126, 189, 252],
            "entry_fill": "next_session_open_with_adverse_slippage",
            "stop_fill": "stop_first_on_same_bar; adverse open on gap-through-stop",
            "reward_risk_target": MIN_REWARD_RISK,
            "max_swing_age_sessions": MAX_SWING_AGE,
            "atr_stop_buffer": ATR_STOP_BUFFER,
            "max_holding_sessions": config.max_holding_sessions,
            "minimum_price": MIN_PRICE,
            "minimum_average_traded_value_20d": MIN_AVG_TRADED_VALUE,
            "liquidity_lookback_sessions": LIQUIDITY_LOOKBACK_SESSIONS,
        },
        "risk_limits": {
            "initial_capital": TOTAL_CAPITAL,
            "max_deployment": MAX_DEPLOYMENT,
            "max_risk_per_trade": MAX_RISK_PER_TRADE,
            "max_aggregate_open_risk": MAX_AGGREGATE_OPEN_RISK,
            "max_positions": MAX_OPEN_POSITIONS,
            "max_position_value": MAX_POSITION_VALUE,
        },
        "backtest_config": config.__dict__,
        "baseline_metrics": metrics,
        "artifact_sha256": artifacts,
        "artifact_policy": "Do not overwrite these source artifacts; all experiments write to a separate directory.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output", default="STRATEGY_BASELINE_SNAPSHOT.json")
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise SystemExit(f"Refusing to overwrite baseline snapshot: {output}")
    snapshot = build_snapshot(Path(args.root))
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
