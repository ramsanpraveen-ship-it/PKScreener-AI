"""Create separate, descriptive diagnostics for the frozen baseline trades."""
import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtest_engine import MIN_AVG_TRADED_VALUE, MIN_PRICE, LIQUIDITY_LOOKBACK_SESSIONS
from contraction_analyzer import analyse_contractions
from breakout_analyzer import analyse_breakout
from market_regime import analyze_market_regime
from strategy_features import measure_breakout_features, measure_relative_strength_features, measure_vcp_features
from backtest_engine import _members_on, validate_point_in_time_universe


BASELINE_FILES = (
    "backtest_metrics.json", "backtest_assumptions.json",
    "backtest_trades.csv", "backtest_equity_curve.csv",
)


def _load_close(path, column="Close"):
    frame = pd.read_csv(path, parse_dates=[0], index_col=0)
    frame.columns = [str(name).strip().title() for name in frame.columns]
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _load_stocks(directory):
    result = {}
    for path in sorted(directory.glob("*.csv")):
        frame = pd.read_csv(path, parse_dates=[0], index_col=0)
        frame.columns = [str(name).strip().title() for name in frame.columns]
        frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index)).normalize()
        result[path.stem.upper()] = frame.sort_index()
    return result


def _assert_baseline_unchanged(root):
    snapshot = json.loads((root / "STRATEGY_BASELINE_SNAPSHOT.json").read_text(encoding="utf-8"))
    for name in BASELINE_FILES:
        relative = f"data/backtest/results/{name}"
        actual = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if snapshot["artifact_sha256"].get(relative) != actual:
            raise ValueError(f"Frozen baseline artifact changed: {relative}")
    return snapshot


def _eligible_on(history, stocks, day):
    members = _members_on(history, day)
    eligible = {}
    for symbol in members:
        frame = stocks.get(symbol)
        if frame is None:
            continue
        bars = frame.loc[frame.index <= day]
        if len(bars) < 253 or float(bars["Close"].iloc[-1]) <= MIN_PRICE:
            continue
        liquidity = (bars["Close"].tail(LIQUIDITY_LOOKBACK_SESSIONS) *
                     bars["Volume"].tail(LIQUIDITY_LOOKBACK_SESSIONS)).mean()
        if len(bars.tail(LIQUIDITY_LOOKBACK_SESSIONS)) == LIQUIDITY_LOOKBACK_SESSIONS and liquidity > MIN_AVG_TRADED_VALUE:
            eligible[symbol] = bars["Close"]
    return members, eligible


def _excursion_diagnostics(trade, bars):
    start, end = pd.Timestamp(trade["entry_date"]), pd.Timestamp(trade["exit_date"])
    held = bars.loc[(bars.index >= start) & (bars.index <= end)]
    entry = float(trade["entry_fill"])
    stop = float(trade["stop_loss"])
    risk = entry - stop
    if held.empty or risk <= 0:
        return {"mfe_per_share": None, "mfe_r": None, "mae_per_share": None, "mae_r": None,
                "reached_1r": None, "reached_2r": None, "stop_touched": None,
                "first_threshold": "UNAVAILABLE", "same_bar_path_ambiguous": None}
    high = float(held["High"].max())
    low = float(held["Low"].min())
    reached1 = bool((held["High"] >= entry + risk).any())
    reached2 = bool((held["High"] >= entry + 2 * risk).any())
    stop_touched = bool((held["Low"] <= stop).any())
    first = "NO_THRESHOLD_TOUCHED"
    ambiguous = False
    for _, bar in held.iterrows():
        stop_today = float(bar["Low"]) <= stop
        one_today = float(bar["High"]) >= entry + risk
        two_today = float(bar["High"]) >= entry + 2 * risk
        if stop_today and (one_today or two_today):
            first = "STOP_FIRST_CONSERVATIVE_SAME_BAR"
            ambiguous = True
            break
        if stop_today:
            first = "STOP"
            break
        if two_today:
            first = "1R_AND_2R_SAME_BAR_PATH_UNKNOWN"
            ambiguous = True
            break
        if one_today:
            first = "1R"
            break
    mfe = high - entry
    mae = low - entry
    return {
        "mfe_per_share": round(mfe, 4), "mfe_r": round(mfe / risk, 4),
        "mae_per_share": round(mae, 4), "mae_r": round(mae / risk, 4),
        "reached_1r": reached1, "reached_2r": reached2,
        "stop_touched": stop_touched, "first_threshold": first,
        "same_bar_path_ambiguous": ambiguous,
        "excursion_sessions": len(held),
    }


def build_diagnostics(root):
    snapshot = _assert_baseline_unchanged(root)
    backtest = root / "data/backtest"
    history = pd.read_csv(backtest / "universe_history.csv")
    history["valid_from"] = pd.to_datetime(history["valid_from"])
    history["valid_to"] = pd.to_datetime(history["valid_to"], errors="coerce")
    manifest = json.loads((backtest / "universe_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("complete_point_in_time_history") is not True:
        raise ValueError("Baseline data does not certify point-in-time membership")
    validate_point_in_time_universe(history, complete=True)
    stocks = _load_stocks(backtest / "stocks")
    benchmark = _load_close(backtest / "nifty50_price.csv")
    trades = pd.read_csv(backtest / "results/backtest_trades.csv").to_dict("records")
    cache = {}
    diagnostics = []
    category_counts = Counter()
    for trade in trades:
        day = pd.Timestamp(trade["signal_date"]).normalize()
        symbol = str(trade["symbol"]).upper()
        bars = stocks[symbol].loc[lambda frame: frame.index <= day]
        if day not in bars.index:
            raise ValueError(f"Baseline signal bar missing: {symbol} {day.date()}")
        if day not in cache:
            members, eligible = _eligible_on(history, stocks, day)
            regime = analyze_market_regime(benchmark, list(eligible), eligible, as_of=day)
            cache[day] = (members, eligible, regime)
        members, eligible, regime = cache[day]
        contractions = analyse_contractions(bars, symbol=symbol)
        breakout = analyse_breakout(bars, symbol=symbol)
        pivot = (breakout.get("pivot") or {}).get("pivot_price")
        contraction_rows = contractions.get("contractions", [])
        vcp = measure_vcp_features(bars, contraction_rows, pivot_price=pivot, as_of=day)
        breakout_features = measure_breakout_features(
            bars, pivot, contraction_rows[0]["start_date"] if contraction_rows else None, as_of=day
        )
        rs = measure_relative_strength_features(
            bars["Close"], benchmark, eligible, symbol=symbol, as_of=day
        )
        excursion = _excursion_diagnostics(trade, stocks[symbol])
        net = float(trade["net_pnl"])
        labels = []
        if net < 0:
            if trade["exit_reason"] == "STOP":
                labels.append("STOP_EXIT")
            if trade["exit_reason"] == "TIME_EXIT":
                labels.append("TIME_EXIT_NET_LOSS")
            if excursion.get("mfe_r") is not None and excursion["mfe_r"] < 1:
                labels.append("MFE_BELOW_1R")
            if excursion.get("mae_r") is not None and excursion["mae_r"] <= -0.5:
                labels.append("MAE_AT_LEAST_MINUS_0_5R")
            if regime["classification"] == "BEARISH":
                labels.append("BEARISH_MARKET_CONTEXT")
            percentile = rs.get("internal_cross_sectional_relative_percentile")
            if percentile is not None and percentile < 50:
                labels.append("BELOW_MEDIAN_INTERNAL_RS")
            avg_vol = vcp.get("average_contraction_volume_ratio")
            if avg_vol is not None and avg_vol >= 1:
                labels.append("CONTRACTION_VOLUME_NOT_BELOW_BASELINE")
            if not labels:
                labels.append("NO_PREDEFINED_DESCRIPTIVE_TAG")
        for label in labels:
            category_counts[label] += 1
        diagnostics.append({
            "symbol": symbol, "signal_date": day.date().isoformat(),
            "entry_date": str(trade["entry_date"]), "exit_date": str(trade["exit_date"]),
            "entry_fill": float(trade["entry_fill"]), "stop_loss": float(trade["stop_loss"]),
            "target": float(trade["target"]), "exit_fill": float(trade["exit_fill"]),
            "exit_reason": trade["exit_reason"], "quantity": int(trade["quantity"]),
            "net_pnl": net, "market_regime": regime, "relative_strength": rs,
            "vcp_features": vcp, "breakout_features": breakout_features,
            "excursion": excursion, "descriptive_loss_tags": labels,
            "censored_at_test_end": trade["exit_reason"] == "END_OF_TEST",
        })
    metrics = snapshot["baseline_metrics"]
    by_regime = {}
    for regime in sorted({item["market_regime"]["classification"] for item in diagnostics}):
        group = [item for item in diagnostics if item["market_regime"]["classification"] == regime]
        winners = sum(item["net_pnl"] > 0 for item in group)
        by_regime[regime] = {
            "trade_count": len(group), "wins": winners,
            "win_rate_pct": round(100 * winners / len(group), 2) if group else None,
            "net_pnl": round(sum(item["net_pnl"] for item in group), 2),
        }
    excursions = [item["excursion"] for item in diagnostics if item["excursion"].get("mfe_r") is not None]
    threshold_counts = {
        name: sum(bool(item["excursion"].get(key)) for item in diagnostics)
        for name, key in (("reached_1r", "reached_1r"), ("reached_2r", "reached_2r"), ("stop_touched", "stop_touched"))
    }
    exit_counts = dict(Counter(item["exit_reason"] for item in diagnostics))
    return {
        "report_type": "DESCRIPTIVE_BASELINE_DIAGNOSTICS",
        "baseline_id": snapshot["baseline_id"],
        "generated_at": datetime.now().astimezone().isoformat(),
        "performance_window": {"start": metrics["start_date"], "end": metrics["end_date"]},
        "trade_count": len(diagnostics),
        "baseline_metrics": metrics,
        "diagnostic_summary": {
            "exit_reason_counts": exit_counts,
            "market_regime_groups": by_regime,
            "average_mfe_r": round(sum(item["mfe_r"] for item in excursions) / len(excursions), 4) if excursions else None,
            "average_mae_r": round(sum(item["mae_r"] for item in excursions) / len(excursions), 4) if excursions else None,
            "threshold_touch_counts": threshold_counts,
            "censored_at_test_end": sum(item["censored_at_test_end"] for item in diagnostics),
        },
        "feature_semantics": {
            "all_features_are_non_gating": True,
            "rs_percentile": "Internal percentile of the legacy weighted excess-return score among point-in-time eligible EQ symbols; not a Minervini or vendor rating.",
            "market_regime": "Nifty 50 price-index 50/200-day averages and 20-session slope; breadth uses point-in-time Nifty 500 EQ membership.",
            "loss_tags": "Descriptive co-occurrences, not causal explanations; tags can overlap. Same-day path ambiguity is disclosed.",
            "sector_features": "Unavailable because dated sector classification history is not in the bundle.",
        },
        "loss_tag_counts": dict(category_counts),
        "trades": diagnostics,
        "experiment_status": "BLOCKED_INSUFFICIENT_UNTOUCHED_OUT_OF_SAMPLE_DATA",
        "limitations": [
            "Only 12 trades in the saved six-month baseline.",
            "This diagnostic sample has already been inspected and is not an untouched test set.",
            "Historical bundle coverage starts 2025-04-01; no requested five-year rolling walk-forward can be run.",
            "The forward paper journal contains only one session and no closed-trade observations.",
            "Loss tags are descriptive associations, not causal failure findings.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output_dir) if args.output_dir else root / "data/backtest/experiments" / f"strategy_intelligence_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if output.exists():
        raise SystemExit(f"Refusing to overwrite experiment output: {output}")
    result = build_diagnostics(root)
    output.mkdir(parents=True)
    (output / "diagnostics.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output),
        "trade_count": result["trade_count"],
        "loss_tag_counts": result["loss_tag_counts"],
        "experiment_status": result["experiment_status"],
    }, indent=2))


if __name__ == "__main__":
    main()
