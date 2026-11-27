"""Historical, cash-only backtest for the existing NSE swing rules.

The runner requires an explicitly complete, sourced point-in-time universe,
daily OHLCV for all members, a Nifty 50 price series for the existing RS rule,
and the official Nifty 50 Total Return Index for performance comparison.
It intentionally refuses to substitute today's constituents or a price index
for those historical inputs.
"""

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
import argparse
from urllib.parse import urlparse
from typing import Mapping

import pandas as pd

from breakout_analyzer import analyse_breakout
from contraction_analyzer import analyse_contractions
from entry_exit_analyzer import analyse_entry_exit
from market_data import calculate_atr
from relative_strength import analyse_relative_strength_from_data
from swing_detector import analyse_swings
from trend_analyzer import analyse_trend_template


OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")
MIN_PRICE = 100.0
MIN_AVG_TRADED_VALUE = 50_000_000.0
LIQUIDITY_LOOKBACK_SESSIONS = 20


def _wilson_win_rate_interval(wins: int, trials: int, z: float = 1.96):
    """Return a two-sided Wilson interval in percent for a binomial win rate."""
    if trials <= 0:
        return None
    p = wins / trials
    z2 = z * z
    denominator = 1 + z2 / trials
    center = (p + z2 / (2 * trials)) / denominator
    margin = z * math.sqrt(p * (1 - p) / trials + z2 / (4 * trials * trials)) / denominator
    return [round(max(0.0, center - margin) * 100, 2),
            round(min(1.0, center + margin) * 100, 2)]


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 100_000.0
    max_deployment: float = 60_000.0
    max_risk_per_trade: float = 500.0
    max_positions: int = 3
    max_position_value: float = 20_000.0
    max_holding_sessions: int = 20
    slippage_bps_per_side: float = 5.0
    brokerage_bps_per_side: float = 0.0
    gst_rate: float = 0.18
    include_statutory_costs: bool = True

    def __post_init__(self):
        if (self.initial_capital != 100_000 or self.max_deployment != 60_000
                or self.max_positions != 3 or self.max_position_value != 20_000
                or self.max_risk_per_trade != 500):
            raise ValueError("Backtest must retain ₹100,000 capital, ₹60,000 deployment, 3 positions, ₹20,000 allocation, and ₹500 risk")
        if not 2 <= self.max_holding_sessions <= 20:
            raise ValueError("Holding period limit must be between 2 and 20 sessions")
        if self.slippage_bps_per_side < 0 or self.brokerage_bps_per_side < 0:
            raise ValueError("Slippage and brokerage cannot be negative")
        if not 0 <= self.gst_rate <= 1:
            raise ValueError("GST rate must be between 0 and 1")


def _normalize_date_index(frame):
    result = frame.copy()
    idx = pd.DatetimeIndex(pd.to_datetime(result.index))
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    result.index = idx.normalize()
    return result.loc[~result.index.duplicated(keep="last")].sort_index()


def _validate_bars(symbol, frame):
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise ValueError(f"{symbol}: historical OHLCV is missing")
    missing = [column for column in OHLCV_COLUMNS if column not in frame]
    if missing:
        raise ValueError(f"{symbol}: missing OHLCV columns {missing}")
    if "Dividends" not in frame.columns:
        raise ValueError(f"{symbol}: dividend cash-action series is required for total-return accounting")
    data = _normalize_date_index(frame.loc[:, list(OHLCV_COLUMNS) + ["Dividends"]])
    for column in OHLCV_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[list(OHLCV_COLUMNS)].isna().any().any():
        raise ValueError(f"{symbol}: OHLCV contains missing/non-numeric values")
    if (data[["Open", "High", "Low", "Close"]] <= 0).any().any():
        raise ValueError(f"{symbol}: prices must be positive")
    if (data["Volume"] < 0).any():
        raise ValueError(f"{symbol}: volume cannot be negative")
    data["Dividends"] = pd.to_numeric(data["Dividends"], errors="coerce")
    if data["Dividends"].isna().any() or (data["Dividends"] < 0).any():
        raise ValueError(f"{symbol}: dividend actions must be complete and non-negative")
    valid = (
        (data["High"] >= data["Low"])
        & (data["High"] >= data["Open"])
        & (data["High"] >= data["Close"])
        & (data["Low"] <= data["Open"])
        & (data["Low"] <= data["Close"])
    )
    if not valid.all():
        raise ValueError(f"{symbol}: invalid OHLC candle relationship")
    return data


def validate_point_in_time_universe(history, complete=False, require_official=True):
    """Validate interval membership plus auditable source references.

    `complete=True` must only be supplied after the source history has been
    independently assembled and checked. The function does not infer
    completeness from the present-day constituent file.
    """
    if not complete:
        raise ValueError(
            "SURVIVORSHIP_GUARD: complete point-in-time constituent history is required"
        )
    required = {"symbol", "series", "valid_from", "valid_to", "source_url"}
    if not isinstance(history, pd.DataFrame) or not required.issubset(history.columns):
        raise ValueError(f"Universe history must contain {sorted(required)}")
    data = history.copy()
    data["symbol"] = data["symbol"].astype(str).str.strip().str.upper()
    data["series"] = data["series"].astype(str).str.strip().str.upper()
    if (data["symbol"] == "").any():
        raise ValueError("Universe history contains an empty symbol")
    if (data["series"] != "EQ").any():
        raise ValueError("Universe history must contain EQ cash-equity securities only")
    data["valid_from"] = pd.to_datetime(data["valid_from"], errors="coerce").dt.normalize()
    data["valid_to"] = pd.to_datetime(data["valid_to"], errors="coerce").dt.normalize()
    if data["valid_from"].isna().any():
        raise ValueError("Universe history contains an invalid valid_from date")
    if (data["valid_to"].notna() & (data["valid_to"] < data["valid_from"])).any():
        raise ValueError("Universe membership interval ends before it starts")
    data["source_url"] = data["source_url"].fillna("").astype(str).str.strip()
    if (data["source_url"] == "").any():
        raise ValueError("Every membership interval needs a source_url")
    if require_official:
        allowed = ("niftyindices.com", "nseindia.com", "nseindia.in")
        def is_official(url):
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            return parsed.scheme == "https" and any(host == domain or host.endswith("." + domain) for domain in allowed)
        if not data["source_url"].map(is_official).all():
            raise ValueError("Universe provenance must point to NSE/NSE Indices sources")
    data = data.sort_values(["symbol", "valid_from"]).reset_index(drop=True)
    for symbol, group in data.groupby("symbol"):
        previous_end = None
        for row in group.itertuples(index=False):
            if previous_end is None:
                previous_end = row.valid_to
                continue
            if pd.isna(previous_end) or row.valid_from <= previous_end:
                raise ValueError(f"Overlapping membership intervals for {symbol}")
            previous_end = row.valid_to
    return data


def _members_on(history, day):
    active = history.loc[
        (history["valid_from"] <= day)
        & (history["valid_to"].isna() | (history["valid_to"] >= day)),
        "symbol",
    ]
    return sorted(set(active.tolist()))


def _strategy_signal(symbol, bars, benchmark_close):
    """Apply the existing deterministic screen to data available through this close."""
    if len(bars) < 253:
        return None
    liquidity_window = bars.tail(LIQUIDITY_LOOKBACK_SESSIONS)
    avg_traded_value = (liquidity_window["Close"] * liquidity_window["Volume"]).mean()
    if (float(bars["Close"].iloc[-1]) <= MIN_PRICE
            or len(liquidity_window) < LIQUIDITY_LOOKBACK_SESSIONS
            or float(avg_traded_value) <= MIN_AVG_TRADED_VALUE):
        return None
    trend = analyse_trend_template(bars, symbol=symbol)
    if not trend["trend_template_pass_without_rs"]:
        return None
    rs = analyse_relative_strength_from_data(
        bars["Close"], benchmark_close, symbol=symbol
    )
    if not rs["relative_strength_pass"]:
        return None
    contraction = analyse_contractions(bars, symbol=symbol)
    if contraction["contraction_sequence"].get("decreasing") is not True:
        return None
    breakout = analyse_breakout(bars, symbol=symbol)
    if not breakout.get("breakout_confirmed"):
        return None
    swings = analyse_swings(bars)
    with_atr = bars.copy()
    with_atr["ATR"] = calculate_atr(with_atr)
    levels = analyse_entry_exit(with_atr, swings, breakout, symbol=symbol)
    if not levels.get("approved_for_entry"):
        return None
    return {
        "signal_date": bars.index[-1],
        "symbol": symbol,
        "signal_close": float(bars["Close"].iloc[-1]),
        "pivot": float(breakout["pivot"]["pivot_price"]),
        "breakout_level": float(breakout["breakout_level"]),
        "stop_loss": float(levels["stop_loss"]),
        "relative_strength": float(rs["weighted_relative_performance"]),
        "trend_conditions_passed": int(trend["conditions_passed"]),
    }


def generate_signals(stock_data, history, benchmark_close, sessions, complete_universe=False):
    history = validate_point_in_time_universe(history, complete=complete_universe)
    signals = []
    for day in sessions:
        members = _members_on(history, day)
        if not members:
            raise ValueError(f"SURVIVORSHIP_GUARD: no sourced universe membership on {day.date()}")
        benchmark_asof = benchmark_close.loc[benchmark_close.index <= day]
        for symbol in members:
            frame = stock_data.get(symbol)
            if frame is None:
                raise ValueError(f"MISSING_HISTORY: {symbol} has no OHLCV history")
            if day not in frame.index:
                # Index members that have not listed/traded yet are not eligible
                # signals. Missing rows after the first available candle remain
                # a hard data-integrity failure.
                if frame.index.empty or day < frame.index[0]:
                    continue
                raise ValueError(f"MISSING_HISTORY: {symbol} has no OHLCV row for {day.date()}")
            bars = frame.loc[frame.index <= day]
            if len(bars) < 253:
                continue
            expected_window = benchmark_asof.index[-253:]
            # Newly listed symbols may legitimately have less than a year of
            # history; keep them out until a full indicator window exists.
            if expected_window[0] < frame.index[0]:
                continue
            missing_warmup = expected_window.difference(frame.index)
            if not missing_warmup.empty:
                raise ValueError(
                    f"MISSING_HISTORY: {symbol} is missing warm-up OHLCV for "
                    f"{missing_warmup[0].date()} (253-session signal window)"
                )
            signal = _strategy_signal(symbol, bars, benchmark_asof)
            if signal is not None:
                signals.append(signal)
    return pd.DataFrame(signals)


def _nse_transaction_bps(day):
    """Conservative upper slab, expressed in bps of traded notional."""
    day = pd.Timestamp(day).date()
    if day >= date(2026, 3, 1):
        return 0.307
    if day >= date(2024, 10, 1):
        return 0.297
    if day >= date(2024, 4, 1):
        return 0.322
    if day >= date(2023, 4, 1):
        return 0.325
    if day >= date(2021, 1, 1):
        return 0.345
    return 0.345


def _fee_rate(day, side, config):
    """Estimated delivery charges: statutory levies + conservative NSE tier."""
    if not config.include_statutory_costs:
        brokerage_bps = config.brokerage_bps_per_side
        return brokerage_bps * (1 + config.gst_rate) / 10_000
    exchange_bps = _nse_transaction_bps(day)
    sebi_bps = 0.01
    brokerage_bps = config.brokerage_bps_per_side
    gst_bps = config.gst_rate * (exchange_bps + sebi_bps + brokerage_bps)
    stt_bps = 10.0
    stamp_bps = 1.5 if side == "buy" else 0.0
    return (stt_bps + stamp_bps + exchange_bps + sebi_bps + brokerage_bps + gst_bps) / 10_000


def _close_position(position, day, price, reason, cash, config):
    slip = config.slippage_bps_per_side / 10_000
    fill = price * (1 - slip)
    sell_fee = fill * position["quantity"] * _fee_rate(day, "sell", config)
    proceeds = fill * position["quantity"] - sell_fee
    cash += proceeds
    dividend_cash = float(position.get("dividend_cash", 0.0))
    gross_pnl = (fill - position["entry_fill"]) * position["quantity"] + dividend_cash
    net_pnl = proceeds - position["entry_cash_outlay"] + dividend_cash
    trade = {
        **position,
        "exit_date": pd.Timestamp(day).date().isoformat(),
        "exit_fill": round(fill, 4),
        "exit_reason": reason,
        "sell_cost": round(sell_fee, 2),
        "dividend_cash": round(dividend_cash, 2),
        "gross_pnl": round(gross_pnl, 2),
        "net_pnl": round(net_pnl, 2),
        "holding_sessions": position["holding_sessions"],
    }
    return cash, trade


def simulate_signals(stock_data, signals, benchmark_tri, start_date, end_date, config=None):
    """Simulate next-session-open entries, long cash positions and daily exits.

    If stop and target are both crossed intraday, the stop is assumed first.
    A gap through a stop is filled at the open with adverse slippage.
    """
    config = config or BacktestConfig()
    if not isinstance(signals, pd.DataFrame):
        signals = pd.DataFrame(signals)
    required = {"signal_date", "symbol", "breakout_level", "pivot", "stop_loss", "relative_strength"}
    if not required.issubset(signals.columns):
        raise ValueError(f"Signals must contain {sorted(required)}")
    tri_all = pd.to_numeric(benchmark_tri, errors="coerce")
    tri_all = _normalize_date_index(tri_all.to_frame("TRI"))["TRI"]
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    tri = tri_all.loc[(tri_all.index >= start) & (tri_all.index <= end)]
    if len(tri) < 2 or tri.isna().any() or (tri <= 0).any():
        raise ValueError("Nifty 50 TRI must provide at least two valid benchmark sessions")
    sessions = list(tri.index)
    session_set = set(sessions)
    by_entry_day = {}
    for row in signals.to_dict("records"):
        signal_day = pd.Timestamp(row["signal_date"]).normalize()
        next_sessions = tri_all.index[tri_all.index > signal_day]
        if len(next_sessions) and next_sessions[0] in session_set:
            by_entry_day.setdefault(next_sessions[0], []).append(row)
    cash = config.initial_capital
    positions = {}
    trades = []
    curve = []
    slip = config.slippage_bps_per_side / 10_000

    def stock_row(symbol, day):
        frame = stock_data.get(symbol)
        if frame is None or day not in frame.index:
            raise ValueError(f"MISSING_HISTORY: {symbol} has no OHLCV row for {day.date()}")
        return frame.loc[day]

    for i, day in enumerate(sessions):
        # Credit ex-date distributions only to shares held through the prior close.
        for symbol, pos in list(positions.items()):
            if pd.Timestamp(pos["entry_date"]).normalize() < day:
                dividend_per_share = float(stock_row(symbol, day).get("Dividends", 0.0))
                if dividend_per_share > 0:
                    distribution = dividend_per_share * pos["quantity"]
                    cash += distribution
                    pos["dividend_cash"] += distribution
        # Open-gap exits happen before new entries and can free capacity at the open.
        for symbol in list(positions):
            pos = positions[symbol]
            row = stock_row(symbol, day)
            if float(row["Open"]) <= pos["stop_loss"]:
                cash, trade = _close_position(pos, day, float(row["Open"]), "STOP_GAP", cash, config)
                trades.append(trade)
                del positions[symbol]
            elif float(row["Open"]) >= pos["target"]:
                cash, trade = _close_position(pos, day, float(row["Open"]), "TARGET_GAP", cash, config)
                trades.append(trade)
                del positions[symbol]

        # Signals from yesterday enter at today's open. Rank using the same RS ordering as the screener.
        if i > 0:
            candidates = sorted(by_entry_day.get(day, []),
                                key=lambda r: (-float(r["relative_strength"]),
                                               -float(r.get("trend_conditions_passed", 0)),
                                               r["symbol"]))
            for signal in candidates:
                symbol = str(signal["symbol"]).strip().upper()
                if symbol in positions or len(positions) >= config.max_positions:
                    continue
                row = stock_row(symbol, day)
                open_price = float(row["Open"])
                fill = open_price * (1 + slip)
                stop = float(signal["stop_loss"])
                pivot = float(signal["pivot"])
                breakout_level = float(signal["breakout_level"])
                # Cancel a failed breakout or an opening gap beyond the screen's 5% extension cap.
                if open_price <= breakout_level or fill > pivot * 1.05 or stop <= 0 or stop >= fill:
                    continue
                buy_fee_rate = _fee_rate(day, "buy", config)
                sell_fee_rate = _fee_rate(day, "sell", config)
                expected_stop_fill = stop * (1 - slip)
                expected_risk_per_share = fill * (1 + buy_fee_rate) - expected_stop_fill * (1 - sell_fee_rate)
                if expected_risk_per_share <= 0:
                    continue
                open_risk = sum(float(p["planned_risk"]) for p in positions.values())
                portfolio_risk_limit = config.max_risk_per_trade * config.max_positions
                remaining_portfolio_risk = max(0.0, portfolio_risk_limit - open_risk)
                deployed = sum(p["entry_fill"] * p["quantity"] for p in positions.values())
                allocation = min(config.max_position_value,
                                 config.max_deployment - deployed,
                                 cash / (1 + buy_fee_rate))
                qty = min(math.floor(config.max_risk_per_trade / expected_risk_per_share),
                          math.floor(remaining_portfolio_risk / expected_risk_per_share),
                          math.floor(allocation / fill))
                if qty <= 0:
                    continue
                buy_cost = fill * qty * buy_fee_rate
                outlay = fill * qty + buy_cost
                if outlay > cash + 1e-9:
                    continue
                cash -= outlay
                risk = fill - stop
                positions[symbol] = {
                    "symbol": symbol,
                    "signal_date": pd.Timestamp(signal["signal_date"]).date().isoformat(),
                    "entry_date": day.date().isoformat(),
                    "entry_fill": fill,
                    "quantity": int(qty),
                    "stop_loss": stop,
                    "target": fill + 2 * risk,
                    "entry_cost": buy_cost,
                    "entry_cash_outlay": outlay,
                    "planned_risk": expected_risk_per_share * qty,
                    "holding_sessions": 0,
                    "dividend_cash": 0.0,
                }

        # Intraday exits. A stop wins if both thresholds trade in the same candle.
        for symbol in list(positions):
            pos = positions[symbol]
            row = stock_row(symbol, day)
            pos["holding_sessions"] += 1
            low, high = float(row["Low"]), float(row["High"])
            if low <= pos["stop_loss"]:
                cash, trade = _close_position(pos, day, pos["stop_loss"], "STOP", cash, config)
                trades.append(trade)
                del positions[symbol]
            elif high >= pos["target"]:
                cash, trade = _close_position(pos, day, pos["target"], "TARGET", cash, config)
                trades.append(trade)
                del positions[symbol]
            elif pos["holding_sessions"] >= config.max_holding_sessions:
                cash, trade = _close_position(pos, day, float(row["Close"]), "TIME_EXIT", cash, config)
                trades.append(trade)
                del positions[symbol]

        market_value = 0.0
        deployed_capital = 0.0
        unrealized_pnl = 0.0
        open_position_risk = 0.0
        for symbol, pos in positions.items():
            close = float(stock_row(symbol, day)["Close"])
            net_exit_value = close * (1 - slip) * pos["quantity"]
            net_exit_value *= 1 - _fee_rate(day, "sell", config)
            market_value += net_exit_value
            deployed_capital += pos["entry_fill"] * pos["quantity"]
            unrealized_pnl += net_exit_value - pos["entry_cash_outlay"] + pos["dividend_cash"]
            open_position_risk += max(0.0, pos["entry_fill"] - pos["stop_loss"]) * pos["quantity"]
        equity = cash + market_value
        curve.append({
            "date": day.date().isoformat(),
            "cash": cash,
            "market_value": market_value,
            "equity": equity,
            "deployed_capital": deployed_capital,
            "unrealized_pnl": unrealized_pnl,
            "open_position_risk": open_position_risk,
            "benchmark_equity": config.initial_capital * float(tri.loc[day]) / float(tri.iloc[0]),
            "open_positions": len(positions),
        })

    # Close remaining positions at the final close so end equity includes exit costs.
    last_day = sessions[-1]
    for symbol in list(positions):
        pos = positions.pop(symbol)
        row = stock_row(symbol, last_day)
        cash, trade = _close_position(pos, last_day, float(row["Close"]), "END_OF_TEST", cash, config)
        trades.append(trade)
    if curve:
        curve[-1]["cash"] = cash
        curve[-1]["market_value"] = 0.0
        curve[-1]["deployed_capital"] = 0.0
        curve[-1]["unrealized_pnl"] = 0.0
        curve[-1]["open_position_risk"] = 0.0
        curve[-1]["equity"] = cash
        curve[-1]["open_positions"] = 0

    peak_equity = float(config.initial_capital)
    for row in curve:
        peak_equity = max(peak_equity, float(row["equity"]))
        row["peak_equity"] = peak_equity
        row["drawdown_pct"] = (float(row["equity"]) / peak_equity - 1) * 100

    return _summarize(trades, curve, config)


def _summarize(trades, curve, config):
    equity = pd.Series([row["equity"] for row in curve], dtype=float)
    benchmark = pd.Series([row["benchmark_equity"] for row in curve], dtype=float)
    initial = float(config.initial_capital)
    equity_with_initial = pd.concat([pd.Series([initial]), equity], ignore_index=True)
    returns = equity_with_initial.pct_change().dropna()
    peak = equity_with_initial.cummax()
    drawdowns = equity_with_initial / peak - 1
    days = max((pd.Timestamp(curve[-1]["date"]) - pd.Timestamp(curve[0]["date"])).days, 1) if curve else 0
    years = days / 365.25 if days else 0
    net = [float(t["net_pnl"]) for t in trades]
    gross = [float(t.get("gross_pnl", t["net_pnl"])) for t in trades]
    wins = [p for p in net if p > 0]
    losses = [p for p in net if p < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    average_win = (gross_profit / len(wins)) if wins else None
    average_loss = (gross_loss / len(losses)) if losses else None
    average_win_loss_ratio = (
        average_win / average_loss if average_win is not None and average_loss else
        ("NO_LOSSES" if average_win is not None else None)
    )
    final_equity = float(equity.iloc[-1]) if len(equity) else config.initial_capital
    cagr = (final_equity / initial) ** (1 / years) - 1 if years and final_equity > 0 else None
    sharpe = (float(returns.mean() / returns.std(ddof=1) * math.sqrt(252))
              if len(returns) > 1 and returns.std(ddof=1) > 0 else None)
    monthly_returns = _period_returns(curve, "ME", initial)
    yearly_returns = _period_returns(curve, "YE", initial)
    holding_periods = [float(t.get("holding_sessions", 0)) for t in trades]
    r_multiples = [float(t["net_pnl"]) / float(t["planned_risk"])
                   for t in trades if float(t.get("planned_risk", 0)) > 0]
    max_consecutive_losses = consecutive_losses = 0
    for pnl in net:
        consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0
        max_consecutive_losses = max(max_consecutive_losses, consecutive_losses)
    average_deployed = (sum(float(row.get("deployed_capital", 0)) for row in curve) / len(curve)
                        if curve else 0.0)
    max_equity = max((float(row["equity"]) for row in curve), default=initial)
    return {
        "metrics": {
            "start_date": curve[0]["date"] if curve else None,
            "end_date": curve[-1]["date"] if curve else None,
            "initial_equity": initial,
            "final_equity": final_equity,
            "total_return_pct": (final_equity / initial - 1) * 100 if initial else None,
            "cagr_pct": cagr * 100 if cagr is not None else None,
            "nifty50_tri_return_pct": (float(benchmark.iloc[-1]) / float(benchmark.iloc[0]) - 1) * 100 if len(benchmark) else None,
            "max_drawdown_pct": float(drawdowns.min() * 100) if len(drawdowns) else None,
            "sharpe_annualized_rf_zero": sharpe,
            "trade_count": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": (len(wins) / len(trades) * 100) if trades else None,
            "win_rate_95ci_pct": _wilson_win_rate_interval(len(wins), len(trades)),
            "gross_profit_net_rupees": round(gross_profit, 2),
            "gross_loss_net_rupees": round(gross_loss, 2),
            "average_win_net_rupees": round(average_win, 2) if average_win is not None else None,
            "average_loss_net_rupees": round(average_loss, 2) if average_loss is not None else None,
            "average_win_loss_ratio": (
                round(average_win_loss_ratio, 4)
                if isinstance(average_win_loss_ratio, (int, float))
                else average_win_loss_ratio
            ),
            "expectancy_net_rupees": (sum(net) / len(net)) if trades else None,
            "profit_factor": (gross_profit / gross_loss) if gross_loss > 0 else (None if not trades else "NO_LOSSES"),
            "max_positions": max((row["open_positions"] for row in curve), default=0),
            "gross_return_pct": (sum(gross) / initial * 100) if initial else None,
            "average_r_multiple": (sum(r_multiples) / len(r_multiples)) if r_multiples else None,
            "largest_winning_trade_net_rupees": max(wins) if wins else None,
            "largest_losing_trade_net_rupees": min(losses) if losses else None,
            "max_consecutive_losses": max_consecutive_losses,
            "average_holding_sessions": (sum(holding_periods) / len(holding_periods)
                                         if holding_periods else None),
            "market_exposure_pct": (sum(1 for row in curve if row["open_positions"] > 0)
                                     / len(curve) * 100 if curve else 0.0),
            "average_deployed_capital": round(average_deployed, 2),
            "average_deployed_capital_pct": average_deployed / initial * 100 if initial else None,
            "max_open_position_risk_rupees": max((float(row.get("open_position_risk", 0)) for row in curve), default=0.0),
            "cash_only_return_pct": 0.0,
            "monthly_returns_pct": monthly_returns,
            "calendar_year_returns_pct": yearly_returns,
        },
        "trades": trades,
        "equity_curve": curve,
        "assumptions": {
            "entry": "Next session open after signal close, with adverse slippage",
            "same_bar_stop_and_target": "Stop is assumed first",
            "gap_stop": "Filled at the open with adverse slippage",
            "holding_period": f"Maximum {config.max_holding_sessions} sessions; stop/target may exit earlier",
            "universe": "Complete point-in-time NSE constituent history required",
            "benchmark": "Nifty 50 Total Return Index, dividends reinvested",
            "costs": "Delivery STT, stamp duty, SEBI/NSE fees, GST proxy and configurable brokerage; see source notes",
        },
    }


def _period_returns(curve, frequency, initial):
    """Return calendar period returns using portfolio capital and prior period equity."""
    if not curve:
        return {}
    frame = pd.DataFrame(curve)
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame.set_index("date").sort_index()
    closes = frame["equity"].resample(frequency).last().dropna()
    result = {}
    previous = float(initial)
    for day, value in closes.items():
        key = day.strftime("%Y-%m" if frequency in ("M", "ME", "MS") else "%Y")
        result[key] = round((float(value) / previous - 1) * 100, 4)
        previous = float(value)
    return result


def _walk_forward_slices(sessions):
    """Split ordered sessions into chronological 60/20/20 partitions."""
    count = len(sessions)
    if count < 5:
        raise ValueError("At least five sessions are required for walk-forward partitions")
    first = max(1, int(count * 0.60))
    second = max(first + 1, int(count * 0.80))
    second = min(second, count - 1)
    return {
        "development": (sessions[0], sessions[first - 1]),
        "validation": (sessions[first], sessions[second - 1]),
        "out_of_sample": (sessions[second], sessions[-1]),
    }


def run_backtest(stock_data: Mapping[str, pd.DataFrame], universe_history,
                 benchmark_close, benchmark_tri, start_date, end_date,
                 config=None, universe_history_complete=False,
                 minimum_window_days=5 * 365):
    """Run the existing rule set with sourced point-in-time membership.

    This fails closed if the membership is not explicitly certified complete,
    the benchmark TRI is incomplete, or a member is missing a daily row.
    """
    config = config or BacktestConfig()
    history = validate_point_in_time_universe(
        universe_history, complete=universe_history_complete, require_official=True
    )
    cleaned = {str(s).upper().strip(): _validate_bars(str(s), frame)
               for s, frame in stock_data.items()}
    price = pd.to_numeric(benchmark_close, errors="coerce")
    price = _normalize_date_index(price.to_frame("Close"))["Close"]
    tri = pd.to_numeric(benchmark_tri, errors="coerce")
    tri = _normalize_date_index(tri.to_frame("TRI"))["TRI"]
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start >= end:
        raise ValueError("Backtest start_date must be before end_date")
    if price.isna().any() or tri.isna().any() or (price <= 0).any() or (tri <= 0).any():
        raise ValueError("Benchmark data must contain positive, complete values")
    sessions = tri.loc[(tri.index >= start) & (tri.index <= end)].index
    if len(sessions) < 2 or not sessions.equals(price.loc[price.index.isin(sessions)].index):
        raise ValueError("Nifty price and TRI benchmarks must cover the same backtest sessions")
    if not isinstance(minimum_window_days, int) or minimum_window_days < 180:
        raise ValueError("minimum_window_days must be an integer of at least 180 days")
    if (end - start).days < minimum_window_days:
        years = minimum_window_days / 365.25
        raise ValueError(f"Backtest requires a minimum {years:.2f}-year test window")
    start_location = price.index.searchsorted(start)
    if start_location < 253:
        raise ValueError("At least 253 benchmark sessions before start_date are required for indicator warm-up")
    for day in sessions:
        members = _members_on(history, day)
        if not members:
            raise ValueError(f"SURVIVORSHIP_GUARD: no sourced membership coverage for {day.date()}")
        for symbol in members:
            frame = cleaned.get(symbol)
            if frame is None:
                raise ValueError(f"MISSING_HISTORY: {symbol} has no OHLCV history")
            if day not in frame.index:
                # A constituent that has not listed yet has no tradable candle.
                # After first listing, any missing member-day still fails closed.
                if frame.index.empty or day < frame.index[0]:
                    continue
                raise ValueError(f"MISSING_HISTORY: {symbol} is missing OHLCV on {day.date()}")
    # The 253 prior bars are warm-up data only. Generate one pre-window close
    # plus in-window closes so no unaccounted earlier positions enter the book.
    first_signal_location = max(0, start_location - 1)
    signal_days = price.index[first_signal_location:price.index.searchsorted(end, side="right")]
    signals = generate_signals(cleaned, history, price, signal_days,
                               complete_universe=True)
    result = simulate_signals(cleaned, signals, tri, start, end, config)
    sessions = tri.loc[(tri.index >= start) & (tri.index <= end)].index
    if (end - start).days >= 5 * 365 and len(sessions) >= 5:
        partitions = {}
        for name, (period_start, period_end) in _walk_forward_slices(sessions).items():
            partitions[name] = simulate_signals(
                cleaned, signals, tri, period_start, period_end, config
            )
        result["walk_forward"] = {
            "method": "Chronological 60% development / 20% validation / 20% untouched out-of-sample",
            "periods": {
                name: {
                    "start_date": period[0].date().isoformat(),
                    "end_date": period[1].date().isoformat(),
                    "metrics": partitions[name]["metrics"],
                    "trades": partitions[name]["trades"],
                    "equity_curve": partitions[name]["equity_curve"],
                }
                for name, period in _walk_forward_slices(sessions).items()
            },
        }
    else:
        result["walk_forward"] = {
            "available": False,
            "reason": "A minimum five-year window is required before reporting 60/20/20 walk-forward results.",
        }
    return result


def load_backtest_bundle(data_dir):
    """Load the documented local CSV bundle and its PIT completeness manifest."""
    root = Path(data_dir)
    manifest_path = root / "universe_manifest.json"
    membership_path = root / "universe_history.csv"
    price_path = root / "nifty50_price.csv"
    tri_path = root / "nifty50_tri.csv"
    stocks_dir = root / "stocks"
    for path in (manifest_path, membership_path, price_path, tri_path):
        if not path.is_file():
            raise FileNotFoundError(f"Required backtest input missing: {path}")
    with manifest_path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    if manifest.get("complete_point_in_time_history") is not True:
        raise ValueError("SURVIVORSHIP_GUARD: universe manifest is not marked complete")
    manifest_url = str(manifest.get("source_url", ""))
    manifest_host = (urlparse(manifest_url).hostname or "").lower()
    if not manifest_url or not urlparse(manifest_url).scheme == "https" or not any(
        manifest_host == host or manifest_host.endswith("." + host)
        for host in ("niftyindices.com", "nseindia.com", "nseindia.in")
    ):
        raise ValueError("Universe manifest must include source_url provenance")
    manifest_start = pd.Timestamp(manifest.get("coverage_start", "NaT"))
    manifest_end = pd.Timestamp(manifest.get("coverage_end", "NaT"))
    if pd.isna(manifest_start) or pd.isna(manifest_end) or manifest_start >= manifest_end:
        raise ValueError("Universe manifest must include valid coverage_start and coverage_end dates")
    membership = pd.read_csv(membership_path)
    price_frame = pd.read_csv(price_path, parse_dates=[0], index_col=0)
    tri_frame = pd.read_csv(tri_path, parse_dates=[0], index_col=0)
    if "Close" not in price_frame.columns:
        raise ValueError("nifty50_price.csv needs a Close column")
    tri_column = "Total Return Index"
    if tri_column not in tri_frame.columns:
        raise ValueError("nifty50_tri.csv needs a 'Total Return Index' column")
    if not stocks_dir.is_dir():
        raise FileNotFoundError(f"Historical stock CSV directory missing: {stocks_dir}")
    stock_data = {}
    for path in sorted(stocks_dir.glob("*.csv")):
        frame = pd.read_csv(path, parse_dates=[0], index_col=0)
        frame.columns = [str(column).strip().title() for column in frame.columns]
        stock_data[path.stem.upper()] = frame
    if not stock_data:
        raise ValueError(f"No stock CSV files found in {stocks_dir}")
    return {
        "manifest": manifest,
        "stock_data": stock_data,
        "universe_history": membership,
        "benchmark_close": price_frame["Close"],
        "benchmark_tri": tri_frame[tri_column],
    }


def save_backtest_results(result, output_dir, run_name="backtest"):
    """Write metrics, trades and equity curve into the selected local folder."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    metrics_path = root / f"{run_name}_metrics.json"
    assumptions_path = root / f"{run_name}_assumptions.json"
    trades_path = root / f"{run_name}_trades.csv"
    curve_path = root / f"{run_name}_equity_curve.csv"
    metrics = dict(result["metrics"])
    if result.get("walk_forward") is not None:
        metrics["walk_forward"] = result["walk_forward"]
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    assumptions_path.write_text(
        json.dumps(result.get("assumptions", {}), indent=2), encoding="utf-8"
    )
    pd.DataFrame(result["trades"]).to_csv(trades_path, index=False)
    pd.DataFrame(result["equity_curve"]).to_csv(curve_path, index=False)
    return metrics_path, assumptions_path, trades_path, curve_path


def main():
    parser = argparse.ArgumentParser(description="Run the local NSE cash-equity swing backtest")
    parser.add_argument("--data-dir", default="data/backtest")
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output-dir", default="data/backtest/results")
    parser.add_argument("--slippage-bps", type=float, default=5.0)
    parser.add_argument("--brokerage-bps", type=float, default=0.0)
    parser.add_argument(
        "--six-month-research", action="store_true",
        help="Allow a six-month exploratory window; all source, membership, dividend, and benchmark guards still apply",
    )
    args = parser.parse_args()
    bundle = load_backtest_bundle(args.data_dir)
    requested_start = pd.Timestamp(args.start_date).normalize()
    requested_end = pd.Timestamp(args.end_date).normalize()
    if pd.Timestamp(bundle["manifest"]["coverage_start"]).normalize() > requested_start - pd.Timedelta(days=400):
        raise ValueError("Universe manifest coverage does not include indicator warm-up")
    if pd.Timestamp(bundle["manifest"]["coverage_end"]).normalize() < requested_end:
        raise ValueError("Universe manifest ends before the requested backtest window")
    result = run_backtest(
        bundle["stock_data"], bundle["universe_history"],
        bundle["benchmark_close"], bundle["benchmark_tri"],
        args.start_date, args.end_date,
        BacktestConfig(slippage_bps_per_side=args.slippage_bps,
                       brokerage_bps_per_side=args.brokerage_bps),
        universe_history_complete=bundle["manifest"]["complete_point_in_time_history"],
        minimum_window_days=180 if args.six_month_research else 5 * 365,
    )
    paths = save_backtest_results(result, args.output_dir)
    print(json.dumps(result["metrics"], indent=2))
    print("Saved:", *[str(path) for path in paths], sep="\n")


if __name__ == "__main__":
    main()
