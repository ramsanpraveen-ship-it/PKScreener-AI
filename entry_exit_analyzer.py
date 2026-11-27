
import math


MAX_SWING_AGE = 60
ATR_STOP_BUFFER = 0.25
MIN_REWARD_RISK = 2.0


def reject(reason):
    return {
        "approved_for_entry": False,
        "status": "REJECTED",
        "reason": reason,
        "entry_price": None,
        "stop_loss": None,
        "risk_per_share": None,
        "target_reference_2r": None,
    }


def analyse_entry_exit(
    df,
    swing_analysis,
    breakout_analysis,
    symbol="UNKNOWN",
):

    if df is None or df.empty:
        return reject("Market data unavailable")

    if "ATR" not in df.columns or "Close" not in df.columns:
        return reject("Required price or ATR data unavailable")

    # Require confirmed breakout
    if not breakout_analysis.get("breakout_confirmed", False):
        return reject("Breakout has not been confirmed")

    breakout_level = breakout_analysis.get("breakout_level")

    if breakout_level is None:
        return reject("Breakout level unavailable")

    # Use latest daily close as estimated entry reference.
    # This is NOT a guaranteed execution price.
    entry_price = float(df["Close"].iloc[-1])

    if not math.isfinite(entry_price) or entry_price <= 0:
        return reject("Invalid entry reference price")

    # Validate ATR
    try:
        atr = float(df["ATR"].iloc[-1])
    except (TypeError, ValueError):
        return reject("Invalid ATR")

    if not math.isfinite(atr) or atr <= 0:
        return reject("ATR unavailable or invalid")

    # Find recent confirmed swing lows
    swings = swing_analysis.get("recent_swings", [])

    if not swings:
        return reject("No confirmed swing data")

    latest_index = len(df) - 1
    valid_lows = []

    for swing in swings:

        if swing.get("type") != "LOW":
            continue

        try:
            swing_index = int(swing["index"])
            swing_price = float(swing["price"])
        except (KeyError, TypeError, ValueError):
            continue

        age = latest_index - swing_index

        if age < 0 or age > MAX_SWING_AGE:
            continue

        if not math.isfinite(swing_price):
            continue

        if swing_price <= 0 or swing_price >= entry_price:
            continue

        valid_lows.append({
            "index": swing_index,
            "price": swing_price,
            "date": swing.get("date"),
            "age": age,
        })

    if not valid_lows:
        return reject(
            "No recent structural swing low below entry"
        )

    # Select most recent valid swing low
    structural_low = max(
        valid_lows,
        key=lambda item: item["index"]
    )

    # Stop below structural low with ATR buffer
    stop_loss = (
        structural_low["price"]
        - ATR_STOP_BUFFER * atr
    )

    if stop_loss <= 0 or stop_loss >= entry_price:
        return reject("Invalid structural stop loss")

    risk_per_share = entry_price - stop_loss

    target_2r = (
        entry_price + MIN_REWARD_RISK * risk_per_share
    )

    return {
        "symbol": symbol,
        "approved_for_entry": True,
        "status": "LEVELS_CALCULATED",

        "entry_price": round(entry_price, 2),
        "entry_price_type": "LATEST_DAILY_CLOSE_REFERENCE",

        "breakout_level": round(float(breakout_level), 2),

        "stop_loss": round(stop_loss, 2),

        "structural_swing_low": round(
            structural_low["price"], 2
        ),

        "swing_low_date": str(structural_low["date"]),
        "swing_age_sessions": structural_low["age"],

        "atr": round(atr, 2),
        "atr_stop_buffer": ATR_STOP_BUFFER,

        "risk_per_share": round(risk_per_share, 2),

        "target_reference_2r": round(target_2r, 2),
        "reward_risk_ratio": MIN_REWARD_RISK,

        "notes": [
            "Entry is the latest daily close, not a guaranteed fill.",
            "Actual next-session execution may differ.",
            "Stop is based on a recent confirmed swing low.",
            "2R is a planning reference, not a guaranteed target.",
            "Slippage and transaction costs are excluded.",
            "Manual approval is required.",
            "No order has been placed."
        ],
    }
